"""Les schémas publiés sont-ils justes sur des documents réels ? (#133)

`tests/test_json_schemas.py` ferme déjà un sens : il compare, par analyse
syntaxique de `models/`, **les clés** que le parseur lit aux `properties` du
schéma. Une clé oubliée ou inventée y échoue.

Il ne voit rien, en revanche, de ce qui se trouve **à l'intérieur** d'une
propriété : un `type` faux, un `enum` incomplet, un `pattern` trop lâche, une
borne à côté. Or ces défauts-là ne dérangent jamais dsoxlab, qui ne lit pas ses
propres schémas : ils dérangent l'auteur de catalogue, dans son éditeur et dans
sa CI. Un schéma faux fait donc autorité à tort, ce qui est la position la moins
confortable possible.

Ce module confronte les schémas à des documents, dans les deux sens.

* **Le valide passe** : le catalogue de démonstration packagé, celui que
  `dsoxlab demo` dépose et qu'un nouveau venu joue en premier, est validé
  fichier par fichier.
* **L'invalide échoue** : chaque cas fautif est le document valide **plus une
  faute**, et une seule. C'est ce qui rend la preuve solide : si la base passe
  et que la variante échoue, c'est bien la faute qui a été refusée, et pas une
  autre. Un schéma qui n'a jamais rien refusé ne prouve rien.

Chaque cas exige aussi que l'erreur **désigne le bon endroit**. Sans cela, un
schéma refusant le bon document pour la mauvaise raison passerait pour correct.

Note de périmètre : les deux schémas posent `additionalProperties: false`, plus
strict que le parseur, qui reste tolérant par garantie de la v1. C'est
délibéré : l'éditeur signale la clé morte à l'écriture, et le moteur continue de
charger le lab. `validate-structure` tient la même position, en lint.
"""

from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path
from typing import Any

import pytest
import yaml
from jsonschema import Draft202012Validator

RACINE = Path(__file__).resolve().parent.parent
SCHEMAS = RACINE / "schemas"

#: Le catalogue que `dsoxlab demo` dépose : packagé, versionné, et joué par la
#: suite E2E. Confronter les schémas à lui, c'est les confronter au seul
#: catalogue dont ce dépôt réponde.
DEMO = RACINE / "src" / "dsoxlab" / "templates" / "demo"


def _validateur(nom: str) -> Draft202012Validator:
    schema = json.loads((SCHEMAS / f"{nom}.schema.json").read_text(encoding="utf-8"))
    # `check_schema` d'abord : un schéma syntaxiquement faux validerait tout
    # sans broncher, et le module entier passerait au vert en ne mesurant rien.
    Draft202012Validator.check_schema(schema)
    return Draft202012Validator(schema)


def _document(chemin: Path) -> Any:
    return yaml.safe_load(chemin.read_text(encoding="utf-8"))


def _chemins_lab() -> list[Path]:
    return sorted(DEMO.glob("labs/**/lab.yaml"))


# ── le valide passe ───────────────────────────────────────────────────────────


def test_le_catalogue_de_demonstration_a_bien_ete_trouve() -> None:
    """Le contre-test du paramétrage : sans lui, zéro fichier = zéro échec.

    Un `glob` qui ne trouve rien rend une liste vide, pytest ne joue aucun cas,
    et la suite reste verte en n'ayant rien validé. C'est le mode de panne le
    plus discret d'un test paramétré.
    """
    assert (DEMO / "meta.yml").is_file()
    assert _chemins_lab(), f"aucun lab.yaml sous {DEMO}"


def test_le_meta_du_catalogue_package_passe_son_schema() -> None:
    erreurs = list(_validateur("meta").iter_errors(_document(DEMO / "meta.yml")))

    assert not erreurs, [f"{e.json_path} : {e.message}" for e in erreurs]


@pytest.mark.parametrize("chemin", _chemins_lab(), ids=lambda p: p.parent.name)
def test_chaque_lab_du_catalogue_package_passe_son_schema(chemin: Path) -> None:
    erreurs = list(_validateur("lab").iter_errors(_document(chemin)))

    assert not erreurs, [f"{e.json_path} : {e.message}" for e in erreurs]


# ── l'invalide échoue, et pour la bonne raison ────────────────────────────────


def _avec(document: Any, chemin: tuple[str, ...], valeur: Any) -> Any:
    """Le document, une seule valeur changée. `valeur is ...` retire la clé."""
    copie = deepcopy(document)
    noeud = copie
    for cle in chemin[:-1]:
        noeud = noeud[cle]
    if valeur is ...:
        del noeud[chemin[-1]]
    else:
        noeud[chemin[-1]] = valeur
    return copie


#: (nom du cas, chemin de la clé, valeur fautive, où l'erreur doit pointer).
#: Une faute par cas, et une classe d'erreur différente à chaque fois : type,
#: énuméré, requis absent, borne, motif, clé hors contrat.
FAUTES_LAB = [
    ("skills en chaîne au lieu d'une liste", ("skills",), "shell", "$.skills"),
    ("lab_type hors de l'énuméré", ("lab_type",), "examen", "$.lab_type"),
    ("id absent, alors qu'il est requis", ("id",), ..., "$"),
    ("schema_version au-delà de ce que l'outil lit", ("schema_version",), 2, "$.schema_version"),
    ("doc_url sans schéma http", ("doc_url",), "ftp://exemple.invalide/doc", "$.doc_url"),
    ("exam_passing_score hors du barème", ("exam_passing_score",), 300, "$.exam_passing_score"),
    ("clé que le contrat ne connaît pas", ("sesion",), "linux", "$"),
    ("runtime.type inventé", ("runtime", "type"), "podman", "$.runtime.type"),
    ("runtime.session hors de l'énuméré", ("runtime", "session"), "distant", "$.runtime.session"),
    ("snapshot_required en chaîne", ("runtime", "snapshot_required"), "oui", "$.runtime.snapshot_required"),
]

FAUTES_META = [
    ("repo absent, alors qu'il est requis", ("repo",), ..., "$"),
    ("repo.id absent", ("repo", "id"), ..., "$.repo"),
    ("repo.category en liste", ("repo", "category"), ["linux"], "$.repo.category"),
    ("schema_version sous la borne", ("schema_version",), 0, "$.schema_version"),
    ("infra.hosts en chaîne", ("infra", "hosts"), "web1.lab", "$.infra.hosts"),
    ("clé que le contrat ne connaît pas", ("infrastructure",), {}, "$"),
]


@pytest.mark.parametrize(
    ("nom", "chemin", "valeur", "attendu"), FAUTES_LAB, ids=[c[0] for c in FAUTES_LAB]
)
def test_le_schema_du_lab_refuse_ce_qu_il_doit_refuser(
    nom: str, chemin: tuple[str, ...], valeur: Any, attendu: str
) -> None:
    validateur = _validateur("lab")
    base = _document(_chemins_lab()[0])
    base.setdefault("schema_version", 1)
    base.setdefault("exam_passing_score", 70)
    base.setdefault("runtime", {}).setdefault("session", "local")
    base["runtime"].setdefault("snapshot_required", False)

    assert not list(validateur.iter_errors(base)), f"la base doit passer, sinon {nom} ne prouve rien"

    erreurs = list(validateur.iter_errors(_avec(base, chemin, valeur)))

    assert erreurs, f"le schéma accepte : {nom}"
    assert attendu in {e.json_path for e in erreurs}, [f"{e.json_path} : {e.message}" for e in erreurs]


@pytest.mark.parametrize(
    ("nom", "chemin", "valeur", "attendu"), FAUTES_META, ids=[c[0] for c in FAUTES_META]
)
def test_le_schema_du_meta_refuse_ce_qu_il_doit_refuser(
    nom: str, chemin: tuple[str, ...], valeur: Any, attendu: str
) -> None:
    validateur = _validateur("meta")
    base = _document(DEMO / "meta.yml")
    base.setdefault("schema_version", 1)
    base.setdefault("infra", {}).setdefault("hosts", [])

    assert not list(validateur.iter_errors(base)), f"la base doit passer, sinon {nom} ne prouve rien"

    erreurs = list(validateur.iter_errors(_avec(base, chemin, valeur)))

    assert erreurs, f"le schéma accepte : {nom}"
    assert attendu in {e.json_path for e in erreurs}, [f"{e.json_path} : {e.message}" for e in erreurs]
