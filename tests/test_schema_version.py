"""La version du contrat d'entrée : `schema_version` dans meta.yml et lab.yaml.

Le contrat que dsoxlab lit (`meta.yml` et `lab.yaml`) est son interface
publique. Sans numéro de version, un champ qui change de sens ne peut être ni
annoncé, ni détecté, ni refusé : il se manifeste par un lab qui disparaît du
catalogue, sans message. C'est le symptôme le plus coûteux à diagnostiquer de
tout le projet.

Ce module tient les trois promesses du champ :

1. **son absence vaut 1**, sans quoi les 284 labs des catalogues existants
   cesseraient d'exister du jour au lendemain, et aucun ne le déclare ;
2. **une version trop récente se dit**, et se dit différemment selon le
   fichier : un `meta.yml` illisible arrête tout, un `lab.yaml` isolé est
   écarté avec un avertissement pendant que le reste du catalogue continue ;
3. **une valeur qui n'est pas un entier est refusée**, plutôt qu'arrondie en
   silence, qui est justement ce que ce champ existe pour supprimer.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest
from typer.testing import CliRunner

from dsoxlab.cli import app
from dsoxlab.discovery.scanner import scan_catalog
from dsoxlab.models.lab import LabDefinition
from dsoxlab.models.repo import RepoMetadata
from dsoxlab.models.schema_version import (
    DEFAULT_SCHEMA_VERSION,
    SUPPORTED_SCHEMA_VERSION,
    UnsupportedSchemaVersion,
    read_schema_version,
)
from dsoxlab.validators.contract import validate_schema_versions

runner = CliRunner()

_ANSI = re.compile(r"\x1b\[[0-9;]*m")

LAB_VALIDE = """\
id: demo-lab
title: Demo lab
level: beginner
skills: [demo]
distros: [any]
doc_url: https://example.org/docs/demo/
runtime:
  type: shell
  workdir: challenge/work
"""

META_VALIDE = """\
repo:
  id: demo-training
  category: demo
"""


def _plain(sortie: str) -> str:
    return _ANSI.sub("", sortie)


def _catalogue(racine: Path, lab: str = LAB_VALIDE, meta: str = META_VALIDE) -> Path:
    """Un dépôt de labs minimal mais complet, à un seul lab."""
    (racine / "meta.yml").write_text(meta, encoding="utf-8")
    dossier = racine / "labs" / "demo" / "premiers-pas"
    tests = dossier / "challenge" / "tests"
    tests.mkdir(parents=True)
    (dossier / "lab.yaml").write_text(lab, encoding="utf-8")
    (dossier / "README.md").write_text("# Demo\n", encoding="utf-8")
    (dossier / "scenario.md").write_text("# Scenario\n", encoding="utf-8")
    (tests / "test_functional.py").write_text("def test_ok():\n    assert True\n", encoding="utf-8")
    return dossier


# ── 1. l'absence vaut 1 ──────────────────────────────────────────────────────

def test_un_lab_sans_schema_version_vaut_la_v1(tmp_path: Path) -> None:
    """Le cas de TOUS les catalogues existants : aucun ne déclare le champ."""
    dossier = _catalogue(tmp_path)
    lab = LabDefinition.from_yaml(dossier / "lab.yaml")

    assert lab.schema_version == DEFAULT_SCHEMA_VERSION == 1


def test_un_meta_sans_schema_version_vaut_la_v1(tmp_path: Path) -> None:
    _catalogue(tmp_path)
    meta = RepoMetadata.from_yaml(tmp_path / "meta.yml")

    assert meta.schema_version == 1


@pytest.mark.parametrize("declaration", ["schema_version: 1\n", "schema_version:\n"])
def test_la_v1_explicite_et_le_champ_laisse_vide_sont_lus_pareil(
    tmp_path: Path, declaration: str
) -> None:
    """`schema_version:` en blanc rend None en YAML : c'est une absence, pas une faute."""
    dossier = _catalogue(tmp_path, lab=declaration + LAB_VALIDE)
    assert LabDefinition.from_yaml(dossier / "lab.yaml").schema_version == 1


def test_le_defaut_ne_suit_pas_la_version_supportee() -> None:
    """Le jour où la v2 existera, un fichier muet devra rester un fichier v1.

    Les faire évoluer ensemble promouvrait en silence tous les catalogues du
    monde vers une version qu'ils n'ont jamais déclarée.
    """
    assert DEFAULT_SCHEMA_VERSION == 1


# ── 2. une version trop récente se dit ───────────────────────────────────────

def test_une_version_trop_recente_leve_une_exception_qui_se_nomme(tmp_path: Path) -> None:
    source = tmp_path / "lab.yaml"
    with pytest.raises(UnsupportedSchemaVersion) as capture:
        read_schema_version({"schema_version": SUPPORTED_SCHEMA_VERSION + 1}, source)

    assert capture.value.found == SUPPORTED_SCHEMA_VERSION + 1
    assert capture.value.supported == SUPPORTED_SCHEMA_VERSION
    assert capture.value.source == source


def test_un_lab_trop_recent_est_ecarte_mais_le_reste_du_catalogue_survit(
    tmp_path: Path,
) -> None:
    """Un lab venu du futur ne doit pas rendre les autres injouables.

    Sans cela, aucun auteur ne pourrait jamais publier un lab v2 : il rendrait
    son catalogue entier inutilisable pour tout apprenant pas encore à jour.
    """
    _catalogue(tmp_path)
    futur = tmp_path / "labs" / "demo" / "futur"
    futur.mkdir(parents=True)
    (futur / "lab.yaml").write_text(
        "schema_version: 99\n" + LAB_VALIDE.replace("demo-lab", "lab-du-futur"),
        encoding="utf-8",
    )

    scan = scan_catalog(tmp_path)

    assert [lab.id for lab in scan.labs] == ["demo-lab"]
    assert len(scan.unsupported) == 1
    assert scan.unsupported[0].found == 99
    assert scan.unsupported[0].source == futur / "lab.yaml"


def test_un_meta_trop_recent_arrete_tout(tmp_path: Path) -> None:
    """Il décrit tout le catalogue : ne pas savoir le lire ne laisse rien de fiable."""
    _catalogue(tmp_path, meta="schema_version: 99\n" + META_VALIDE)

    with pytest.raises(UnsupportedSchemaVersion):
        scan_catalog(tmp_path)


def test_la_cli_nomme_le_lab_ecarte_au_lieu_de_le_taire(tmp_path: Path) -> None:
    _catalogue(tmp_path)
    futur = tmp_path / "labs" / "demo" / "futur"
    futur.mkdir(parents=True)
    (futur / "lab.yaml").write_text(
        "schema_version: 99\n" + LAB_VALIDE.replace("demo-lab", "lab-du-futur"),
        encoding="utf-8",
    )

    resultat = runner.invoke(app, ["list-labs", "--lab-home", str(tmp_path)])
    sortie = _plain(resultat.stdout)

    assert resultat.exit_code == 0
    assert "demo-lab" in sortie, "le reste du catalogue doit rester listé"
    assert "99" in sortie and "schema_version" in sortie, sortie


def test_le_mode_machine_ne_dit_rien_hors_du_document_json(tmp_path: Path) -> None:
    """Un avertissement sur stdout casserait tout consommateur de `--json`."""
    _catalogue(tmp_path)
    futur = tmp_path / "labs" / "demo" / "futur"
    futur.mkdir(parents=True)
    (futur / "lab.yaml").write_text(
        "schema_version: 99\n" + LAB_VALIDE.replace("demo-lab", "lab-du-futur"),
        encoding="utf-8",
    )

    resultat = runner.invoke(app, ["list-labs", "--json", "--lab-home", str(tmp_path)])

    document = json.loads(resultat.stdout)
    assert document["count"] == 1


def test_la_cli_refuse_un_meta_trop_recent_avec_une_phrase(tmp_path: Path) -> None:
    _catalogue(tmp_path, meta="schema_version: 99\n" + META_VALIDE)

    resultat = runner.invoke(app, ["list-labs", "--lab-home", str(tmp_path)])

    assert resultat.exit_code == 1
    assert "99" in _plain(resultat.output)


@pytest.mark.parametrize("langue", ["en", "fr"])
def test_le_message_suit_la_langue_demandee(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, langue: str
) -> None:
    """Un message neuf écrit dans une seule langue est le défaut qu'on corrige ici."""
    from dsoxlab.i18n import set_lang
    from dsoxlab.i18n.strings.en import STRINGS as EN
    from dsoxlab.i18n.strings.fr import STRINGS as FR

    _catalogue(tmp_path, meta="schema_version: 99\n" + META_VALIDE)
    monkeypatch.setenv("DSOXLAB_LANG", langue)
    set_lang(langue)
    try:
        resultat = runner.invoke(app, ["list-labs", "--lab-home", str(tmp_path)])
    finally:
        set_lang("en")

    catalogue = EN if langue == "en" else FR
    debut = catalogue["schema_version_meta_too_new"].split("{")[0].strip()
    assert debut and debut in _plain(resultat.output), _plain(resultat.output)


# ── 3. une valeur qui n'est pas un entier est refusée ────────────────────────

@pytest.mark.parametrize(
    ("etiquette", "valeur"),
    [
        ("chaîne", "1"),
        ("flottant", 1.5),
        ("booléen", True),
        ("liste", [1]),
        ("mapping", {"v": 1}),
        ("zéro", 0),
        ("négatif", -1),
    ],
)
def test_une_valeur_qui_n_est_pas_une_version_est_refusee(
    tmp_path: Path, etiquette: str, valeur: object
) -> None:
    """Strict là où le reste du contrat est tolérant : `1.5` deviendrait `1`."""
    with pytest.raises(ValueError) as capture:
        read_schema_version({"schema_version": valeur}, tmp_path / "lab.yaml")

    assert not isinstance(capture.value, UnsupportedSchemaVersion), (
        f"{etiquette} n'est pas une version « trop récente », c'est une valeur invalide"
    )


def test_une_valeur_invalide_reste_dans_le_contrat_d_exceptions(tmp_path: Path) -> None:
    """`discovery/scanner.py` ne rattrape que KeyError, ValueError et YAMLError.

    Une TypeError sur `schema_version: [1]` remonterait en traceback brut, sur
    une commande sans rapport.
    """
    dossier = _catalogue(tmp_path, lab="schema_version: [1]\n" + LAB_VALIDE)

    with pytest.raises(ValueError):
        LabDefinition.from_yaml(dossier / "lab.yaml")

    # Et le scanner l'absorbe : le catalogue reste utilisable.
    assert scan_catalog(tmp_path).labs == []


# ── 4. validate-structure voit ce que la découverte ne peut pas voir ─────────

def test_le_validator_signale_une_valeur_non_entiere(tmp_path: Path) -> None:
    """Le lab n'est plus découvert : aucun autre validator ne peut le voir."""
    _catalogue(tmp_path, lab='schema_version: "un"\n' + LAB_VALIDE)

    rapport = validate_schema_versions(tmp_path)

    assert not rapport.ok
    assert [i.key for i in rapport.issues] == ["schema_version_invalid"]
    assert rapport.issues[0].path.name == "lab.yaml"
    assert not rapport.meta_is_unreadable


def test_le_validator_signale_une_version_inconnue(tmp_path: Path) -> None:
    _catalogue(tmp_path, lab="schema_version: 42\n" + LAB_VALIDE)

    rapport = validate_schema_versions(tmp_path)

    assert [i.key for i in rapport.issues] == ["schema_version_too_new"]
    assert rapport.issues[0].params["found"] == 42


def test_le_validator_distingue_le_meta_d_un_lab(tmp_path: Path) -> None:
    _catalogue(tmp_path, meta="schema_version: 42\n" + META_VALIDE)

    rapport = validate_schema_versions(tmp_path)

    assert rapport.meta_is_unreadable


def test_un_catalogue_sans_schema_version_passe_le_validator(tmp_path: Path) -> None:
    """Le cas des 284 labs existants : rien à signaler."""
    _catalogue(tmp_path)

    assert validate_schema_versions(tmp_path).ok


def test_validate_structure_echoue_et_nomme_le_fichier(tmp_path: Path) -> None:
    _catalogue(tmp_path, lab="schema_version: 42\n" + LAB_VALIDE)

    resultat = runner.invoke(app, ["validate-structure", "--lab-home", str(tmp_path)])
    sortie = _plain(resultat.output)

    assert resultat.exit_code == 1
    assert "lab.yaml" in sortie
    assert "42" in sortie


def test_validate_structure_reste_vert_sans_schema_version(tmp_path: Path) -> None:
    """Le défaut « absence = 1 » doit laisser passer un catalogue conforme."""
    _catalogue(tmp_path)

    resultat = runner.invoke(app, ["validate-structure", "--lab-home", str(tmp_path)])

    assert resultat.exit_code == 0, _plain(resultat.output)


# ── 5. deux contrats distincts, jamais couplés ───────────────────────────────

def test_la_version_du_contrat_d_entree_n_est_pas_celle_de_la_sortie_json(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`reporting/machine.py: SCHEMA` versionne ce que dsoxlab ÉCRIT.

    Les deux valent 1 aujourd'hui, et c'est précisément ce qui rendrait la
    confusion facile : elles n'ont ni le même public, ni les mêmes raisons de
    bouger. On fait donc bouger l'une, et on exige que l'autre ne suive pas.
    """
    import dsoxlab.models.schema_version as entree
    import dsoxlab.reporting.machine as sortie

    _catalogue(tmp_path)
    monkeypatch.setattr(entree, "SUPPORTED_SCHEMA_VERSION", 7)

    resultat = runner.invoke(app, ["list-labs", "--json", "--lab-home", str(tmp_path)])
    document = json.loads(resultat.stdout)

    assert document["schema"] == sortie.SCHEMA == 1
    assert "schema_version" not in document["labs"][0], (
        "la version du contrat d'entrée n'a rien à faire dans le document de sortie"
    )
