"""`draft: true` au manifeste : un catalogue vide n'est pas proposé (#369).

Depuis la 0.9.2, `catalog list` proposait `certificats`, dont le dépôt ne publiait
aucun lab : un apprenant qui l'installait obtenait un catalogue sans rien à jouer.
Une entrée en brouillon reste installable (`catalog add <url>`, ou par son id),
mais n'est plus proposée, ni par `catalog list` ni par l'accueil.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
import yaml
from typer.testing import CliRunner

from dsoxlab.cli import app
from dsoxlab.services import catalog

runner = CliRunner()

RACINE = Path(__file__).resolve().parents[1]

_MANIFESTE = """\
schema_version: 1
catalogues:
  - id: publie
    depot: https://exemple.test/proprio/publie
    description_en: Published
    description_fr: Publié
  - id: en-cours
    depot: https://exemple.test/proprio/en-cours
    draft: true
    description_en: In progress
    description_fr: En cours
  - id: chaine
    depot: https://exemple.test/proprio/chaine
    draft: "true"
"""


@pytest.fixture
def manifeste(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    chemin = tmp_path / "catalogues.yml"
    chemin.write_text(_MANIFESTE, encoding="utf-8")
    monkeypatch.setattr(catalog, "catalogues_manifeste", lambda: chemin)
    for variable in ("XDG_STATE_HOME", "XDG_DATA_HOME", "XDG_CACHE_HOME"):
        monkeypatch.setenv(variable, str(tmp_path / variable.lower()))
    monkeypatch.setenv("DSOXLAB_LANG", "en")
    return chemin


def test_le_drapeau_est_lu(manifeste: Path) -> None:
    brouillons = {c.id: c.draft for c in catalog.lire_manifeste()}
    assert brouillons == {"publie": False, "en-cours": True, "chaine": False}


def test_seul_un_booleen_vrai_cache_une_entree(manifeste: Path) -> None:
    """`draft: "true"` (une chaîne) ne cache pas un catalogue publié."""
    assert [c.id for c in catalog.proposes(catalog.lire_manifeste())] == ["publie", "chaine"]


def test_catalog_list_ne_propose_pas_un_brouillon(manifeste: Path) -> None:
    resultat = runner.invoke(app, ["catalog", "list", "--json"])
    assert resultat.exit_code == 0, resultat.stdout
    connus = json.loads(resultat.stdout)["known"]
    assert [c["id"] for c in connus] == ["publie", "chaine"]
    assert all(c["draft"] is False for c in connus)


def test_catalog_list_drafts_les_montre(manifeste: Path) -> None:
    resultat = runner.invoke(app, ["catalog", "list", "--json", "--drafts"])
    connus = {c["id"]: c["draft"] for c in json.loads(resultat.stdout)["known"]}
    assert connus == {"publie": False, "en-cours": True, "chaine": False}


def test_un_brouillon_reste_installable_par_son_id(manifeste: Path) -> None:
    """Le manifeste facilite la découverte, il ne restreint rien."""
    assert catalog.resoudre("en-cours") == ("en-cours", "https://exemple.test/proprio/en-cours")


def test_l_accueil_ne_propose_pas_un_brouillon(
    manifeste: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import importlib

    from dsoxlab.cli import _amorcage

    # Par son nom complet : `dsoxlab.reporting.console` désigne aussi l'objet
    # Console que le paquet réexporte, qui masque le module.
    console = importlib.import_module("dsoxlab.reporting.console")
    vus: dict[str, object] = {}
    monkeypatch.setattr(console, "afficher_accueil", lambda **kw: vus.update(kw))
    _amorcage._accueil()
    assert [c[0] for c in vus["connus"]] == ["publie", "chaine"]  # type: ignore[union-attr]


def test_le_manifeste_package_met_certificats_en_brouillon() -> None:
    """Critère de l'issue : tant qu'il ne publie aucun lab."""
    donnees = yaml.safe_load(
        (RACINE / "src/dsoxlab/templates/catalogues.yml").read_text(encoding="utf-8")
    )
    entree = next(c for c in donnees["catalogues"] if c["id"] == "certificats")
    assert entree["draft"] is True
