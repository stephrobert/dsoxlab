"""``list-labs`` et le contexte actif (issue #308).

Deux défauts mesurés sur un catalogue réel :

1. l'aide de ``--section`` citait « linux, ansible, terraform, docker », des
   valeurs qu'aucun catalogue ne porte (une section vaut le champ ``section``
   du ``lab.yaml``, ``repo.category`` à défaut), et le moteur est neutre vis-à-vis du domaine ;
2. un filtre qui s'excluait du contexte (``--level`` hors de la section active)
   rendait un 0 muet, et rien ne permettait de lister sans le contexte.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
import typer
from typer.testing import CliRunner

from dsoxlab.cli import app
from dsoxlab.config import write_context

runner = CliRunner()

_META = """\
repo:
  id: deux-sections
  category: domaine
sections:
  - id: s1
    title: Premiere
    labs: [domaine/lab-a]
  - id: s2
    title: Seconde
    labs: [domaine/lab-b]
"""


def _lab(identifiant: str, section: str, niveau: str) -> str:
    return (
        f"id: {identifiant}\ntitle: {identifiant}\nlevel: {niveau}\n"
        f"section: {section}\n"
        "skills: [demo]\ndistros: [any]\ndoc_url: https://example.test/d/\n"
        "runtime:\n  type: shell\n  workdir: challenge/work\n"
    )


@pytest.fixture
def catalogue(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    (tmp_path / "meta.yml").write_text(_META, encoding="utf-8")
    for nom, section, niveau in (("lab-a", "s1", "debutant"), ("lab-b", "s2", "avance")):
        dossier = tmp_path / "labs" / "domaine" / nom
        (dossier / "challenge" / "tests").mkdir(parents=True)
        (dossier / "lab.yaml").write_text(_lab(nom, section, niveau), encoding="utf-8")
    monkeypatch.setenv("HOME", str(tmp_path / "maison"))
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "etat"))
    monkeypatch.setenv("DSOXLAB_LANG", "en")
    monkeypatch.setenv("DSOXLAB_NO_UPDATE_CHECK", "1")
    write_context(tmp_path, section="s1", level=None)
    return tmp_path


def _ids(catalogue: Path, *options: str) -> list[str]:
    resultat = runner.invoke(
        app, ["list-labs", "--json", *options, "--lab-home", str(catalogue)]
    )
    assert resultat.exit_code == 0, resultat.output
    return [lab["id"] for lab in json.loads(resultat.stdout)["labs"]]


def test_le_contexte_filtre_toujours_par_defaut(catalogue: Path) -> None:
    assert _ids(catalogue) == ["lab-a"]


def test_all_ignore_le_contexte_sans_le_modifier(catalogue: Path) -> None:
    assert sorted(_ids(catalogue, "--all")) == ["lab-a", "lab-b"]
    assert _ids(catalogue, "--all", "--level", "avance") == ["lab-b"]
    assert _ids(catalogue) == ["lab-a"]


def test_un_vide_du_au_contexte_le_dit(catalogue: Path) -> None:
    resultat = runner.invoke(
        app, ["list-labs", "--level", "avance", "--lab-home", str(catalogue)]
    )
    assert resultat.exit_code == 0, resultat.output
    assert "--all" in resultat.output and "1 lab(s)" in resultat.output


def test_un_vide_reel_ne_blame_pas_le_contexte(catalogue: Path) -> None:
    resultat = runner.invoke(
        app, ["list-labs", "--level", "inexistant", "--lab-home", str(catalogue)]
    )
    assert "--all" not in resultat.output


def test_l_aide_des_filtres_ne_cite_aucun_domaine() -> None:
    commande = typer.main.get_command(app).commands["list-labs"]  # type: ignore[attr-defined]
    aides = " ".join(p.help or "" for p in commande.params if hasattr(p, "help")).lower()
    for domaine in ("linux", "ansible", "terraform", "docker", "lfcs", "rhcsa"):
        assert domaine not in aides, domaine
    assert "lab.yaml" in aides
