"""Les badges du README d'un catalogue neuf, et les workflows qui les remplissent.

Les catalogues de la collection portent cinq badges sous la ligne de langue :
CI, OpenSSF Scorecard, Plumber, SLSA 3 et licence. `new catalog` n'en écrivait
aucun, et ne posait pas les deux workflows sans lesquels les badges Scorecard
et Plumber restent vides.

Ce que ces tests tiennent :

- avec `--github`, les cinq badges visent `<propriétaire>/<id>` ;
- sans lui, ils visent l'emplacement `<owner>`, et la CLI dit de le remplacer ;
- aucun propriétaire réel n'est codé dans le moteur ;
- les workflows Scorecard et Plumber sont écrits, et leur YAML se charge.

Aucun test ne lit le rendu Rich : on lit les fichiers produits, et l'appel au
message, intercepté avant d'être affiché.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest
import yaml
from typer.testing import CliRunner

from dsoxlab.cli import app
from dsoxlab.i18n import _
from dsoxlab.services.scaffold import ScaffoldError, creer_catalogue
from dsoxlab.services.scaffold_socle import PROPRIETAIRE_PAR_DEFAUT

runner = CliRunner()

#: Le texte alternatif de chaque badge, par langue. Seuls Plumber et la licence
#: se traduisent.
ALT_EN = ("CI", "OpenSSF Scorecard", "Plumber compliance", "SLSA 3",
          "License: CC BY 4.0")
ALT_FR = ("CI", "OpenSSF Scorecard", "Conformité Plumber", "SLSA 3",
          "Licence : CC BY 4.0")


def _badges(readme: Path) -> list[str]:
    """Les lignes de badges, juste sous la ligne de langue."""
    return [ligne for ligne in readme.read_text(encoding="utf-8").splitlines()
            if ligne.startswith("[![")]


def _verifier_badges(racine: Path, depot: str) -> None:
    for nom, alts in (("README.md", ALT_EN), ("README.fr.md", ALT_FR)):
        lignes = _badges(racine / nom)
        assert [re.match(r"\[!\[([^\]]+)\]", ligne).group(1)  # type: ignore[union-attr]
                for ligne in lignes] == list(alts), f"{nom} : badges {lignes}"
        # CI, Scorecard et Plumber visent le dépôt ; SLSA et la licence non.
        for ligne in lignes[:3]:
            assert ligne.count(depot) == 2, (
                f"{nom} : l'image et le lien de {ligne} ne visent pas tous deux {depot}"
            )
        assert lignes[4].endswith("(./LICENSE)")


def test_avec_github_les_cinq_badges_visent_le_depot(tmp_path: Path) -> None:
    racine = creer_catalogue("demo", tmp_path, proprietaire="exemple").racine

    _verifier_badges(racine, "exemple/demo")
    assert PROPRIETAIRE_PAR_DEFAUT not in (racine / "README.md").read_text(
        encoding="utf-8")


def test_les_badges_sont_sous_la_ligne_de_langue(tmp_path: Path) -> None:
    """La place est celle des catalogues : la ligne de langue, puis les badges."""
    racine = creer_catalogue("demo", tmp_path, proprietaire="exemple").racine
    for nom, langue in (("README.md", "**Language:**"), ("README.fr.md", "**Langue :**")):
        lignes = (racine / nom).read_text(encoding="utf-8").splitlines()
        rang = next(i for i, ligne in enumerate(lignes) if ligne.startswith(langue))
        assert lignes[rang + 1] == ""
        assert lignes[rang + 2].startswith("[![CI]"), f"{nom} : {lignes[rang + 2]}"


def test_sans_github_les_badges_portent_l_emplacement(tmp_path: Path) -> None:
    racine = creer_catalogue("demo", tmp_path).racine

    _verifier_badges(racine, "<owner>/demo")


def test_le_proprietaire_sert_aussi_dans_releasing(tmp_path: Path) -> None:
    """Les commandes de vérification visent le même dépôt que les badges."""
    racine = creer_catalogue("demo", tmp_path, proprietaire="exemple").racine
    for nom in ("RELEASING.md", "RELEASING.fr.md", ".github/workflows/attester.yml"):
        texte = (racine / nom).read_text(encoding="utf-8")
        assert "--repo exemple/demo" in texte, f"{nom} ne vise pas exemple/demo"
        assert "<owner>" not in texte, f"{nom} garde l'emplacement <owner>"


def test_aucun_proprietaire_reel_n_est_code_dans_le_socle(tmp_path: Path) -> None:
    """Partout où le dépôt du catalogue est nommé, c'est sous le propriétaire donné.

    Avant ce test, RELEASING portait un propriétaire réel en dur : un catalogue
    créé par quelqu'un d'autre aurait vérifié ses releases contre le dépôt d'un
    tiers.
    """
    racine = creer_catalogue("demo", tmp_path, proprietaire="exemple").racine
    vus = 0
    for chemin in racine.rglob("*"):
        if not chemin.is_file():
            continue
        texte = chemin.read_text(encoding="utf-8")
        for proprietaire in re.findall(r"([\w.<>-]+)/demo(?![\w-])", texte):
            vus += 1
            assert proprietaire.endswith("exemple"), (
                f"{chemin.relative_to(racine)} nomme {proprietaire}/demo"
            )
    assert vus > 10, "le dépôt du catalogue n'est presque nommé nulle part"


@pytest.mark.parametrize("mauvais", ["", "-exemple", "exemple-", "ex--emple",
                                     "ex/emple", "a" * 40, "ex emple", "<owner>"])
def test_un_proprietaire_invalide_est_refuse_avant_d_ecrire(
    tmp_path: Path, mauvais: str
) -> None:
    with pytest.raises(ScaffoldError):
        creer_catalogue("demo", tmp_path, proprietaire=mauvais)
    assert not (tmp_path / "demo").exists(), "un squelette à moitié écrit est resté"


def _messages_avertis(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    """Intercepte les avertissements de `new catalog` avant leur affichage."""
    from dsoxlab.cli import auteur

    recus: list[str] = []
    monkeypatch.setattr(auteur, "warn", lambda message, *a, **k: recus.append(message))
    return recus


def test_la_cli_sans_github_dit_de_remplacer_l_emplacement(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    recus = _messages_avertis(monkeypatch)

    resultat = runner.invoke(app, ["new", "catalog", "demo", "--in", str(tmp_path)])

    assert resultat.exit_code == 0, resultat.output
    assert _("scaffold_github_a_remplacer", name="demo") in recus
    _verifier_badges(tmp_path / "demo", "<owner>/demo")


def test_la_cli_avec_github_ne_dit_rien(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    recus = _messages_avertis(monkeypatch)

    resultat = runner.invoke(
        app, ["new", "catalog", "demo", "--in", str(tmp_path), "--github", "exemple"]
    )

    assert resultat.exit_code == 0, resultat.output
    assert recus == []
    _verifier_badges(tmp_path / "demo", "exemple/demo")


def test_la_cli_refuse_un_proprietaire_invalide(tmp_path: Path) -> None:
    resultat = runner.invoke(
        app, ["new", "catalog", "demo", "--in", str(tmp_path), "--github", "a/b"]
    )

    assert resultat.exit_code == 1
    assert not (tmp_path / "demo").exists()


def test_l_option_github_existe() -> None:
    """L'option est déclarée sur `new catalog`, avec une aide traduite."""
    import typer.main

    groupe = typer.main.get_command(app)
    commande = groupe.commands["new"].commands["catalog"]  # type: ignore[attr-defined]
    options = {nom for param in commande.params for nom in param.opts}
    assert "--github" in options
    aide = next(p.help for p in commande.params if "--github" in p.opts)  # type: ignore[attr-defined]
    assert aide == _("opt_new_github")


# ── Les workflows qui remplissent les badges ────────────────────────────────


def test_les_workflows_des_badges_sont_ecrits_et_se_chargent(tmp_path: Path) -> None:
    racine = creer_catalogue("demo", tmp_path).racine
    workflows = racine / ".github" / "workflows"

    scorecard = yaml.safe_load((workflows / "scorecard.yml").read_text(encoding="utf-8"))
    plumber = yaml.safe_load((workflows / "plumber.yml").read_text(encoding="utf-8"))

    for nom, workflow in (("scorecard", scorecard), ("plumber", plumber)):
        # Deny-by-default au niveau du workflow, permissions par job.
        assert workflow["permissions"] == {}, f"{nom} : permissions globales"
        for job in workflow["jobs"].values():
            assert job["permissions"]["contents"] == "read"
            # Les accolades de str.format ont bien été dédoublées puis rendues.
            assert job["if"] == "${{ !github.event.repository.private }}"
    actions = [s.get("uses", "") for s in scorecard["jobs"]["analysis"]["steps"]]
    assert any(a.startswith("ossf/scorecard-action@") for a in actions)
    actions = [s.get("uses", "") for s in plumber["jobs"]["plumber"]["steps"]]
    assert any(a.startswith("getplumber/plumber@") for a in actions)


def test_le_workflow_plumber_trouve_sa_configuration(tmp_path: Path) -> None:
    """L'action Plumber refuse de tourner sans `.plumber.yaml`."""
    racine = creer_catalogue("demo", tmp_path).racine

    config = yaml.safe_load((racine / ".plumber.yaml").read_text(encoding="utf-8"))
    assert config["version"] == "2.0"
    assert "github" in config
