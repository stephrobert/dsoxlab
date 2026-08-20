"""Les schémas JSON publiés disent-ils la vérité sur le contrat ?

`schemas/lab.schema.json` et `schemas/meta.schema.json` existent pour qu'un
auteur de catalogue soit corrigé par son éditeur plutôt que par un lab qui
disparaît de `list-labs`. Ils ne valent donc que ce que vaut leur exactitude :
un schéma qui ment fait autorité à tort, ce qui est pire que pas de schéma du
tout.

Or rien ne les relie mécaniquement au code. Recopiés à la main, ils auront
dérivé en trois versions : un champ ajouté à `models/` et oublié dans le
schéma sera signalé comme une faute chez l'auteur qui l'emploie ; un champ
inventé dans le schéma sera écrit par des catalogues et ignoré en silence par
le moteur.

Ce module ferme les deux sens. Il **lit `models/lab.py` et `models/repo.py`**
et en extrait, par analyse syntaxique, les clés que le parseur va réellement
chercher dans le YAML : `data["id"]`, `runtime_data.get("workdir")`,
`"name" not in t`. Il confronte ensuite cet ensemble aux `properties` du nœud
correspondant du schéma, et exige l'**égalité**, pas l'inclusion :

* une clé lue par `models/` et absente du schéma → échec ;
* une clé du schéma que `models/` ne lit nulle part → échec.

Il exige aussi qu'aucun niveau de mapping n'échappe au contrôle : un nouveau
bloc imbriqué dans le parseur fait échouer le test tant qu'il n'est pas
rattaché à un nœud du schéma. Sans cela, la couverture se dégraderait sans que
rien ne le dise.
"""

from __future__ import annotations

import ast
import json
from collections import defaultdict
from pathlib import Path
from typing import Any

import pytest

import dsoxlab
from dsoxlab.models.runtime import RuntimeType
from dsoxlab.models.schema_version import (
    SCHEMA_VERSION_FIELD,
    SUPPORTED_SCHEMA_VERSION,
)
from dsoxlab.validators.metadata import _VALID_LAB_TYPES

RACINE = Path(__file__).resolve().parent.parent
SCHEMAS = RACINE / "schemas"
MODELS = Path(dsoxlab.__file__).parent / "models"

#: Où vit, dans le schéma, chaque mapping que le parseur ouvre. La clé est le
#: nom de la variable Python qui porte ce mapping dans `from_yaml` ; la valeur
#: est le chemin du nœud correspondant dans le document JSON.
#:
#: Une variable trouvée par l'analyse et absente de cette table fait échouer le
#: test : c'est le signal qu'un niveau du contrat vient d'apparaître et n'est
#: décrit nulle part.
NOEUDS_LAB: dict[str, tuple[str, ...]] = {
    "data": (),
    "runtime_data": ("properties", "runtime"),
    "t": ("properties", "runtime", "properties", "targets", "items"),
    "s": ("properties", "runtime", "properties", "services", "items"),
    "validation_data": ("properties", "validation"),
}

NOEUDS_META: dict[str, tuple[str, ...]] = {
    "data": (),
    "repo": ("properties", "repo"),
    "infra_data": ("properties", "infra"),
    "h": ("properties", "infra", "properties", "hosts", "items"),
    "s": ("properties", "sections", "items"),
}

#: `schema_version` n'est pas lu par un littéral de `from_yaml` : il passe par
#: `read_schema_version()`, que l'analyse syntaxique ne suit pas. On l'ajoute
#: donc à la main, mais **depuis la constante**, pour qu'un renommage du champ
#: reste détecté au lieu de figer une chaîne de plus.
LUES_EN_PLUS = {"data": {SCHEMA_VERSION_FIELD}}


# ── extraction : ce que le parseur va réellement chercher ────────────────────

def _corps_de_methode(module: ast.Module, classe: str, methode: str) -> ast.AST:
    for noeud in ast.walk(module):
        if isinstance(noeud, ast.ClassDef) and noeud.name == classe:
            for membre in noeud.body:
                if (
                    isinstance(membre, (ast.FunctionDef, ast.AsyncFunctionDef))
                    and membre.name == methode
                ):
                    return membre
    raise AssertionError(f"{classe}.{methode} introuvable")


def cles_lues(chemin: Path, classe: str, methode: str) -> dict[str, set[str]]:
    """Les clés littérales que ``classe.methode`` lit, groupées par variable.

    Trois écritures comptent, et ce sont les trois qu'emploie le contrat :
    ``var["cle"]``, ``var.get("cle")`` et ``"cle" in var``.
    """
    module = ast.parse(chemin.read_text(encoding="utf-8"), filename=str(chemin))
    corps = _corps_de_methode(module, classe, methode)

    lues: dict[str, set[str]] = defaultdict(set)
    for noeud in ast.walk(corps):
        if isinstance(noeud, ast.Subscript) and isinstance(noeud.value, ast.Name):
            cle = noeud.slice
            if isinstance(cle, ast.Constant) and isinstance(cle.value, str):
                lues[noeud.value.id].add(cle.value)
        elif (
            isinstance(noeud, ast.Call)
            and isinstance(noeud.func, ast.Attribute)
            and noeud.func.attr == "get"
            and isinstance(noeud.func.value, ast.Name)
            and noeud.args
            and isinstance(noeud.args[0], ast.Constant)
            and isinstance(noeud.args[0].value, str)
        ):
            lues[noeud.func.value.id].add(noeud.args[0].value)
        elif (
            isinstance(noeud, ast.Compare)
            and isinstance(noeud.left, ast.Constant)
            and isinstance(noeud.left.value, str)
        ):
            for operateur, compare in zip(noeud.ops, noeud.comparators, strict=True):
                if isinstance(operateur, (ast.In, ast.NotIn)) and isinstance(
                    compare, ast.Name
                ):
                    lues[compare.id].add(noeud.left.value)
    return dict(lues)


def _noeud(schema: dict[str, Any], chemin: tuple[str, ...]) -> dict[str, Any]:
    courant: Any = schema
    for segment in chemin:
        courant = courant[segment]
    assert isinstance(courant, dict), f"nœud {chemin} inattendu"
    return courant


def _charger(nom: str) -> dict[str, Any]:
    donnees = json.loads((SCHEMAS / nom).read_text(encoding="utf-8"))
    assert isinstance(donnees, dict)
    return donnees


@pytest.fixture(scope="module")
def lab_schema() -> dict[str, Any]:
    return _charger("lab.schema.json")


@pytest.fixture(scope="module")
def meta_schema() -> dict[str, Any]:
    return _charger("meta.schema.json")


# ── le contrôle bidirectionnel ───────────────────────────────────────────────

def _confronter(
    schema: dict[str, Any],
    noeuds: dict[str, tuple[str, ...]],
    lues: dict[str, set[str]],
    origine: str,
) -> None:
    inconnues = sorted(set(lues) - set(noeuds))
    assert not inconnues, (
        f"{origine} ouvre des mappings qu'aucun nœud du schéma ne décrit : "
        f"{inconnues}. Rattache-les dans ce test, ou décris-les dans le schéma."
    )

    ecarts: list[str] = []
    for variable, chemin in noeuds.items():
        attendues = lues.get(variable, set()) | LUES_EN_PLUS.get(variable, set())
        declarees = set(_noeud(schema, chemin).get("properties", {}))

        manquantes = sorted(attendues - declarees)
        inventees = sorted(declarees - attendues)
        if manquantes:
            ecarts.append(
                f"  [{variable}] lues par {origine}, absentes du schéma : {manquantes}"
            )
        if inventees:
            ecarts.append(
                f"  [{variable}] décrites par le schéma, jamais lues par {origine} : "
                f"{inventees}"
            )

    assert not ecarts, "Le schéma a dérivé du parseur :\n" + "\n".join(ecarts)


def test_lab_schema_decrit_exactement_ce_que_le_parseur_lit(
    lab_schema: dict[str, Any],
) -> None:
    _confronter(
        lab_schema,
        NOEUDS_LAB,
        cles_lues(MODELS / "lab.py", "LabDefinition", "from_yaml"),
        "models/lab.py",
    )


def test_meta_schema_decrit_exactement_ce_que_le_parseur_lit(
    meta_schema: dict[str, Any],
) -> None:
    _confronter(
        meta_schema,
        NOEUDS_META,
        cles_lues(MODELS / "repo.py", "RepoMetadata", "from_yaml"),
        "models/repo.py",
    )


# ── garde-fou du garde-fou ───────────────────────────────────────────────────

def test_l_extraction_trouve_bien_les_trois_ecritures(tmp_path: Path) -> None:
    """Une extraction cassée rendrait tout ce module vert à vide."""
    source = tmp_path / "faux.py"
    source.write_text(
        "class M:\n"
        "    @classmethod\n"
        "    def from_yaml(cls, p):\n"
        '        a = data["indexe"]\n'
        '        b = data.get("appele", 1)\n'
        '        if "teste" in data:\n'
        "            pass\n"
        '        c = autre.get("ailleurs")\n'
        "        return a, b, c\n",
        encoding="utf-8",
    )
    lues = cles_lues(source, "M", "from_yaml")
    assert lues["data"] == {"indexe", "appele", "teste"}
    assert lues["autre"] == {"ailleurs"}


def test_la_confrontation_echoue_dans_les_deux_sens() -> None:
    """Le test doit virer au rouge sur un champ oublié ET sur un champ inventé."""
    schema = {"properties": {"connu": {}}}
    noeuds = {"data": ()}

    with pytest.raises(AssertionError, match="absentes du schéma"):
        _confronter(schema, noeuds, {"data": {"connu", "oublie"}}, "faux")

    with pytest.raises(AssertionError, match="jamais lues"):
        _confronter(schema, noeuds, {"data": set()}, "faux")

    with pytest.raises(AssertionError, match="aucun nœud du schéma ne décrit"):
        _confronter(schema, noeuds, {"data": {"connu"}, "surprise": {"x"}}, "faux")


# ── énumérés, versions, identité ─────────────────────────────────────────────

def test_les_enumeres_suivent_les_constantes_du_code(
    lab_schema: dict[str, Any],
) -> None:
    """Un énuméré recopié à la main dérive dès qu'on ajoute une valeur."""
    runtime = _noeud(lab_schema, ("properties", "runtime", "properties", "type"))
    assert set(runtime["enum"]) == {t.value for t in RuntimeType}

    lab_type = _noeud(lab_schema, ("properties", "lab_type"))
    assert set(lab_type["enum"]) == set(_VALID_LAB_TYPES)


@pytest.mark.parametrize("nom", ["lab.schema.json", "meta.schema.json"])
def test_schema_version_est_decrit_et_borne_par_la_version_supportee(nom: str) -> None:
    """Le champ de l'issue #76 figure dans les deux schémas, borné par le code.

    Le `maximum` est ce qui fait qu'un éditeur refuse `schema_version: 2` tant
    que l'outil ne sait pas le lire, donc il doit suivre la constante, pas une
    valeur recopiée.
    """
    champ = _charger(nom)["properties"][SCHEMA_VERSION_FIELD]
    assert champ["type"] == "integer"
    assert champ["minimum"] == 1
    assert champ["maximum"] == SUPPORTED_SCHEMA_VERSION
    assert champ["default"] == 1, "l'absence du champ vaut 1, pas la version courante"


@pytest.mark.parametrize("nom", ["lab.schema.json", "meta.schema.json"])
def test_le_schema_porte_son_identite_et_son_dialecte(nom: str) -> None:
    """Un `$id` copié-collé d'un schéma à l'autre les rendrait indiscernables."""
    schema = _charger(nom)
    assert schema["$schema"] == "https://json-schema.org/draft/2020-12/schema"
    assert schema["$id"].endswith(f"/schemas/{nom}")
    assert schema["$id"].startswith("https://")
    assert schema["title"]
    assert schema["description"]


@pytest.mark.parametrize("nom", ["lab.schema.json", "meta.schema.json"])
def test_les_champs_requis_existent_dans_le_schema(nom: str) -> None:
    """Un `required` qui nomme un champ absent des `properties` est inapplicable."""
    orphelins: list[str] = []

    def parcourir(noeud: Any, chemin: str) -> None:
        if not isinstance(noeud, dict):
            return
        proprietes = noeud.get("properties")
        if isinstance(proprietes, dict):
            for requis in noeud.get("required", []):
                if requis not in proprietes:
                    orphelins.append(f"{chemin}: {requis}")
            for cle, valeur in proprietes.items():
                parcourir(valeur, f"{chemin}/{cle}")
        for cle in ("items", "additionalProperties"):
            parcourir(noeud.get(cle), f"{chemin}/{cle}")
        for variante in noeud.get("oneOf", []):
            parcourir(variante, f"{chemin}/oneOf")

    parcourir(_charger(nom), nom)
    assert not orphelins, f"required sans propriété correspondante : {orphelins}"
