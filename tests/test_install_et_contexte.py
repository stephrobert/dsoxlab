"""Trois défauts de l'installation et de l'état local, chacun reproduit.

Ils ont en commun de ne se manifester que chez l'utilisateur : une complétion
qui ne complète pas, un lanceur qui ne lance pas, une CLI qui refuse de démarrer
à cause d'un fichier d'état. Aucun ne se voit depuis le dépôt.
"""

from __future__ import annotations

import json
import stat
import subprocess
from pathlib import Path

import pytest
from typer.testing import CliRunner

from dsoxlab import cli
from dsoxlab.config import read_context

runner = CliRunner()


# ── la complétion interrogeait la CLI avec une variable qu'elle n'écoute pas ──

def test_la_variable_de_completion_est_celle_que_click_attend() -> None:
    """Click dérive le nom de la variable du prog_name, il ne l'invente pas.

    La valeur codée en dur était `_DSOXL_COMPLETE`. Le script généré
    interrogeait donc dsoxlab avec une variable ignorée : la CLI répondait par
    sa page d'aide, que le shell tentait ensuite d'évaluer à chaque tabulation.
    """
    attendu = "_" + cli._PROG_NAME.replace("-", "_").upper() + "_COMPLETE"
    assert cli._COMPLETE_VAR == attendu == "_DSOXLAB_COMPLETE"


@pytest.mark.parametrize("shell", ["bash", "zsh"])
def test_le_script_genere_porte_la_bonne_variable(shell: str) -> None:
    from typer.completion import get_completion_script

    script = get_completion_script(  # `shell` = nom du shell Typer, pas shell=True
        prog_name=cli._PROG_NAME, complete_var=cli._COMPLETE_VAR, shell=shell
    )
    assert "_DSOXLAB_COMPLETE" in script
    assert "_DSOXL_COMPLETE" not in script, (
        "l'ancienne variable ne doit plus apparaître : elle est ignorée par la CLI"
    )


def test_le_fichier_zsh_porte_le_nom_que_zsh_cherche(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """zsh autoload la fonction `_dsoxlab` pour compléter `dsoxlab`.

    Le fichier s'appelait `_dsoxl` : jamais chargé, quel que soit son contenu.
    """
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("SHELL", "/usr/bin/zsh")
    monkeypatch.setattr(cli.Path, "home", classmethod(lambda cls: tmp_path))

    resultat = runner.invoke(cli.app, ["install"])
    assert resultat.exit_code == 0, resultat.output

    assert (tmp_path / ".zfunc" / "_dsoxlab").is_file()
    assert not (tmp_path / ".zfunc" / "_dsoxl").exists()


# ── le wrapper cassait sur un chemin contenant une espace ─────────────────────

def _ecrire_faux_binaire(chemin: Path) -> None:
    """Un exécutable qui prouve, en s'exécutant, qu'il a bien été appelé."""
    chemin.parent.mkdir(parents=True, exist_ok=True)
    chemin.write_text('#!/bin/sh\necho "APPELE:$*"\n', encoding="utf-8")
    chemin.chmod(chemin.stat().st_mode | stat.S_IEXEC | stat.S_IXGRP | stat.S_IXOTH)


def test_le_wrapper_fonctionne_avec_une_espace_dans_le_chemin(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Le seul test qui prouve quelque chose ici : on EXÉCUTE le wrapper.

    Sans quoting, `exec /home/moi/My Tools/dsoxlab "$@"` se découpe en deux
    arguments et le shell répond « not found ». Vérifier le contenu du fichier
    ne l'aurait pas montré.
    """
    binaire = tmp_path / "My Tools" / "dsoxlab-reel"
    _ecrire_faux_binaire(binaire)

    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("SHELL", "/bin/bash")
    monkeypatch.setattr(cli.Path, "home", classmethod(lambda cls: tmp_path))
    monkeypatch.setattr(cli.sys, "argv", [str(binaire)])

    resultat = runner.invoke(cli.app, ["install"])
    assert resultat.exit_code == 0, resultat.output

    wrapper = tmp_path / ".local" / "bin" / "dsoxlab"
    assert wrapper.is_file()

    # check=False : si le wrapper ne s'exécute pas, l'assertion doit pouvoir
    # afficher son contenu — c'est ce qui rend le diagnostic possible.
    joue = subprocess.run(
        [str(wrapper), "check", "un-lab"], capture_output=True, text=True, check=False,
    )
    assert joue.returncode == 0, (
        f"le wrapper ne s'exécute pas : {joue.stderr.strip()}\n"
        f"contenu : {wrapper.read_text(encoding='utf-8')!r}"
    )
    assert "APPELE:check un-lab" in joue.stdout, (
        "les arguments doivent parvenir au binaire réel"
    )


def test_un_lanceur_existant_n_est_pas_ecrase(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`uv tool install` pose son lanceur exactement là, et c'est un lien.

    Le danger est plus grave qu'un simple écrasement, et il a fallu une
    mutation pour le voir : `write_text()` sur un lien symbolique écrit dans
    **la cible**. Sans garde, on ne remplace donc pas le lien, on remplace le
    binaire réel de uv par un script `exec` qui pointe sur lui-même. Le lien
    survit, `resolve()` ne bouge pas, et la commande boucle à l'infini.

    Ce test compare donc le CONTENU du binaire réel, seule chose qui change.
    """
    reel = tmp_path / "outils" / "dsoxlab"
    _ecrire_faux_binaire(reel)
    contenu_avant = reel.read_text(encoding="utf-8")

    lanceur = tmp_path / ".local" / "bin" / "dsoxlab"
    lanceur.parent.mkdir(parents=True, exist_ok=True)
    lanceur.symlink_to(reel)

    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("SHELL", "/bin/bash")
    monkeypatch.setattr(cli.Path, "home", classmethod(lambda cls: tmp_path))
    monkeypatch.setattr(cli.sys, "argv", [str(lanceur)])

    resultat = runner.invoke(cli.app, ["install"])
    assert resultat.exit_code == 0, resultat.output

    assert lanceur.is_symlink(), "le lien de uv/pipx doit rester un lien"
    assert reel.read_text(encoding="utf-8") == contenu_avant, (
        "le binaire réel a été réécrit à travers le lien : il s'exec désormais "
        "lui-même, donc il boucle"
    )
    assert "exec" not in reel.read_text(encoding="utf-8").split("\n")[1], (
        "le binaire ne doit pas être devenu un wrapper vers lui-même"
    )


# ── un fichier d'état corrompu ne doit pas emporter la CLI ────────────────────

CONTEXTES_INVALIDES = [
    ("racine liste", "[1, 2]"),
    ("racine chaîne", '"texte"'),
    ("racine nombre", "42"),
    ("racine nulle", "null"),
    ("position nulle", '{"course_pos": null}'),
    ("position non numérique", '{"course_pos": "foo"}'),
    ("position négative", '{"course_pos": -5}'),
    ("position booléenne", '{"course_pos": true}'),
    ("position flottante", '{"course_pos": 2.7}'),
    ("section numérique", '{"section": 42}'),
    ("section liste", '{"section": ["l1"]}'),
    ("json invalide", "pas du json"),
    ("fichier vide", ""),
]


@pytest.mark.parametrize(
    ("nom", "contenu"),
    CONTEXTES_INVALIDES,
    ids=[nom for nom, _ in CONTEXTES_INVALIDES],
)
def test_un_contexte_corrompu_rend_un_contexte_vide(
    tmp_path: Path, nom: str, contenu: str
) -> None:
    """Perdre le contexte coûte un `dsoxlab use` ; lever coûte toute la CLI.

    Le `except` ne couvrait que JSONDecodeError et OSError : `null` levait un
    TypeError, `"foo"` un ValueError, et une racine non-objet un AttributeError.
    """
    (tmp_path / ".dsoxlab-context.json").write_text(contenu, encoding="utf-8")

    ctx = read_context(tmp_path)

    assert ctx.course_pos == 0
    assert ctx.section is None
    assert isinstance(ctx.course_pos, int)


def test_des_octets_illisibles_ne_font_pas_lever(tmp_path: Path) -> None:
    """UnicodeDecodeError descend de ValueError, pas d'OSError.

    Un fichier d'octets arbitraires passait donc à travers l'ancien filet.
    """
    (tmp_path / ".dsoxlab-context.json").write_bytes(b"\xff\xfe\x00rubbish")

    assert read_context(tmp_path).course_pos == 0


def test_un_contexte_valide_est_toujours_lu(tmp_path: Path) -> None:
    """Le durcissement ne doit pas avaler le cas nominal."""
    (tmp_path / ".dsoxlab-context.json").write_text(
        json.dumps({
            "section": "linux",
            "level": "l2",
            "lang": "fr",
            "active_lab": "l2-acl-posix",
            "active_target": "rhel",
            "active_provider": "kvm",
            "course_pos": 3,
        }),
        encoding="utf-8",
    )

    ctx = read_context(tmp_path)

    assert ctx.section == "linux"
    assert ctx.level == "l2"
    assert ctx.lang == "fr"
    assert ctx.active_lab == "l2-acl-posix"
    assert ctx.active_target == "rhel"
    assert ctx.active_provider == "kvm"
    assert ctx.course_pos == 3


def test_une_position_en_chaine_reste_lue(tmp_path: Path) -> None:
    """« 3 » écrit à la main par un formateur vaut la position 3.

    Refuser une chaîne numérique perdrait une position parfaitement lisible.
    """
    (tmp_path / ".dsoxlab-context.json").write_text(
        '{"course_pos": " 3 "}', encoding="utf-8"
    )

    assert read_context(tmp_path).course_pos == 3


def test_la_cli_demarre_sur_un_contexte_corrompu(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Le vrai symptôme : la commande la plus banale devenait impossible."""
    (tmp_path / "meta.yml").write_text(
        "repo:\n  id: demo\n  category: demo\n", encoding="utf-8"
    )
    (tmp_path / ".dsoxlab-context.json").write_text(
        '{"course_pos": null}', encoding="utf-8"
    )
    monkeypatch.setenv("LAB_HOME", str(tmp_path))
    monkeypatch.chdir(tmp_path)

    resultat = runner.invoke(cli.app, ["list-labs"])

    assert resultat.exit_code == 0, resultat.output
    assert "TypeError" not in resultat.output
