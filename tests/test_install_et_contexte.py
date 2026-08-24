"""Trois défauts de l'installation et de l'état local, chacun reproduit.

Ils ont en commun de ne se manifester que chez l'utilisateur : une complétion
qui ne complète pas, un lanceur qui ne lance pas, une CLI qui refuse de démarrer
à cause d'un fichier d'état. Aucun ne se voit depuis le dépôt.
"""

from __future__ import annotations

import json
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
    monkeypatch.setattr(cli.diagnostic.Path, "home", classmethod(lambda cls: tmp_path))

    resultat = runner.invoke(cli.app, ["install"])
    assert resultat.exit_code == 0, resultat.output

    assert (tmp_path / ".zfunc" / "_dsoxlab").is_file()
    assert not (tmp_path / ".zfunc" / "_dsoxl").exists()


# ── le wrapper n'est plus écrit du tout ───────────────────────────────────────

def test_install_n_ecrit_plus_de_wrapper(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Deux défauts vécus tenaient à ce fichier, et le retirer les clôt.

    `dsoxlab install` posait un `exec` dans `~/.local/bin`, exactement où
    `uv tool install` et `pipx` posent leur lanceur. Le remplacer ne faisait que
    défaire ce que leur prochaine mise à jour remettrait, et le danger était pire
    qu'un écrasement : `write_text()` sur un lien symbolique écrit dans **la
    cible**, donc on remplaçait le binaire réel de uv par un script pointant sur
    lui-même. Il a fallu une mutation pour le voir (#68).

    Un chemin contenant une espace cassait par ailleurs le `exec`, faute de
    quoting, et le shell répondait « not found ».

    Les deux disparaissent en n'écrivant plus rien, et c'est ce que ce test
    vérifie. Il remplace les deux tests d'exécution du wrapper, devenus sans
    objet : garder un test sur un fichier qui n'existe plus le rendrait vert
    sans rien mesurer.
    """
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("SHELL", "/bin/bash")
    monkeypatch.setattr(cli.diagnostic.Path, "home", classmethod(lambda cls: tmp_path))

    resultat = runner.invoke(cli.app, ["install"])
    assert resultat.exit_code == 0, resultat.output

    assert not (tmp_path / ".local" / "bin" / "dsoxlab").exists()
    # La complétion, elle, est bien posée : la commande n'est pas devenue vide.
    assert (tmp_path / ".bash_completion.d" / "dsoxlab").is_file()


def test_install_annonce_sa_depreciation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Le nom promettait d'installer l'outil, déjà installé.

    Il reste un cycle de version, mais il doit dire par quoi il est remplacé :
    une dépréciation muette ne déplace personne.
    """
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("SHELL", "/bin/bash")
    monkeypatch.setattr(cli.diagnostic.Path, "home", classmethod(lambda cls: tmp_path))

    resultat = runner.invoke(cli.app, ["install"])

    assert resultat.exit_code == 0, resultat.output
    sortie = " ".join(resultat.output.split())
    assert "completion install" in sortie, sortie
    assert "0.3.0" in sortie, "la version de retrait doit être annoncée"


def test_completion_install_fait_le_meme_travail(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Le nouveau nom doit poser exactement ce que l'ancien posait."""
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("SHELL", "/usr/bin/zsh")
    monkeypatch.setattr(cli.diagnostic.Path, "home", classmethod(lambda cls: tmp_path))

    resultat = runner.invoke(cli.app, ["completion", "install"])

    assert resultat.exit_code == 0, resultat.output
    assert (tmp_path / ".zfunc" / "_dsoxlab").is_file()


def test_completion_show_n_ecrit_rien_sur_le_disque(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`show` sert à rediriger : il ne doit poser aucun script ni toucher un rc.

    Le contrôle ne peut pas être « le HOME reste vide » : toute commande dsoxlab
    ouvre son journal au démarrage et crée donc `~/.local/state/dsoxlab/`, ce qui
    n'a rien à voir avec `show`. On vise les fichiers que `show` pourrait écrire
    et ne doit pas écrire.
    """
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setattr(cli.diagnostic.Path, "home", classmethod(lambda cls: tmp_path))

    resultat = runner.invoke(cli.app, ["completion", "show", "--shell", "zsh"])

    assert resultat.exit_code == 0, resultat.output
    assert "#compdef dsoxlab" in resultat.output
    assert not (tmp_path / ".zfunc").exists(), "aucun script de complétion posé"
    assert not (tmp_path / ".bash_completion.d").exists()
    assert not (tmp_path / ".zshrc").exists(), "aucun rc touché"
    assert not (tmp_path / ".bashrc").exists()


def test_completion_show_refuse_un_shell_inconnu() -> None:
    """Le contre-cas : sans lui, `show` rendrait un script vide en silence."""
    resultat = runner.invoke(cli.app, ["completion", "show", "--shell", "csh"])

    assert resultat.exit_code == 2, resultat.output


# ── le premier Tab d'une session ne proposait rien ────────────────────────────

def test_le_script_zsh_repond_des_la_premiere_tabulation() -> None:
    """Reproduit dans un zsh réel : tabulation 1 muette, tabulation 2 correcte.

    zsh autoload le fichier `#compdef` au PREMIER Tab et attend qu'il produise
    les propositions de cette invocation-là. Le script amont se contente de
    définir la fonction puis de l'enregistrer pour la suite. L'appel final est
    donc la correction, et il est **après** l'enregistrement : les deux chemins,
    première tabulation et suivantes, doivent marcher.

    Ce test ne remplace pas la vérification sous pseudo-terminal, qui est la
    seule à traverser la couche en cause ; il empêche que la ligne disparaisse
    d'un coup d'éditeur, ce qu'aucun test unitaire de complétion ne verrait.
    """
    script = cli._script_completion("zsh")

    assert script.rstrip().endswith('_dsoxlab_completion "$@"'), script
    assert script.index("compdef _dsoxlab_completion") < script.index(
        '_dsoxlab_completion "$@"'
    ), "l'appel doit suivre l'enregistrement"
    # La raison part dans le fichier installé : sans elle, la ligne ressemble à
    # une scorie, et le défaut revient.
    assert "typer" in script.lower()


def test_les_autres_shells_restent_ceux_de_typer() -> None:
    """La divergence ne vaut que pour zsh, et il faut que ça reste vrai.

    bash source son script au démarrage, fish le charge par fichier de
    complétion : ni l'un ni l'autre ne passe par l'autoload en cause. Y ajouter
    la ligne n'aurait aucun effet utile et nous éloignerait de l'amont sans
    raison.
    """
    from typer.completion import get_completion_script

    for shell in ("bash", "fish"):
        attendu = get_completion_script(
            prog_name=cli._PROG_NAME, complete_var=cli._COMPLETE_VAR, shell=shell
        )
        assert cli._script_completion(shell) == attendu


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
