"""Toute clé passée à ``_()`` doit exister dans les deux langues.

Ce garde-fou est né d'une clé posée dans le code et jamais dans les
dictionnaires : ``_()`` rend alors **la clé elle-même**, si bien que
l'utilisateur voyait `catalog_git_absent` s'afficher là où une phrase était
attendue. Rien ne l'attrapait, et le test qui aurait dû le faire passait au
vert : il vérifiait que le message contenait « git », or la chaîne
`catalog_git_absent` en contient.

Un garde-fou existait déjà (`test_i18n_validators.py`), mais son périmètre
s'arrêtait à `validators/` et `models/`, et aux clés passées en `key=`. Les
appels `_("…")` du reste du paquet — la CLI, les services, les runtimes —
n'étaient vérifiés nulle part.

Les clés construites dynamiquement (`_(f"check_{key}")`) sont hors de portée
d'une lecture statique et sont ignorées : elles sont couvertes par les tests
qui exercent réellement les commandes.
"""

from __future__ import annotations

import ast
from pathlib import Path

import dsoxlab
from dsoxlab.i18n.strings.en import STRINGS as EN
from dsoxlab.i18n.strings.fr import STRINGS as FR

RACINE = Path(dsoxlab.__file__).parent


def _cles_litterales() -> dict[str, list[str]]:
    """Chaque clé littérale passée à ``_()``, avec les fichiers qui l'emploient."""
    trouvees: dict[str, list[str]] = {}
    for chemin in sorted(RACINE.rglob("*.py")):
        if chemin.is_relative_to(RACINE / "i18n"):
            continue
        arbre = ast.parse(chemin.read_text(encoding="utf-8"))
        for noeud in ast.walk(arbre):
            if not isinstance(noeud, ast.Call):
                continue
            if getattr(noeud.func, "id", "") != "_" or not noeud.args:
                continue
            premier = noeud.args[0]
            if isinstance(premier, ast.Constant) and isinstance(premier.value, str):
                trouvees.setdefault(premier.value, []).append(
                    str(chemin.relative_to(RACINE))
                )
    return trouvees


def test_la_lecture_des_sources_est_representative() -> None:
    """Sans ce contrôle, une lecture cassée rendrait le test suivant toujours vert.

    C'est le défaut que ce module corrige : un contrôle qui, faute de pouvoir
    mesurer, conclut que tout va bien.
    """
    assert len(_cles_litterales()) > 200


def test_chaque_cle_du_paquet_existe_en_anglais() -> None:
    manquantes = {
        cle: fichiers for cle, fichiers in _cles_litterales().items() if cle not in EN
    }
    assert manquantes == {}, f"clés absentes de strings/en.py : {manquantes}"


def test_chaque_cle_du_paquet_existe_en_francais() -> None:
    manquantes = {
        cle: fichiers for cle, fichiers in _cles_litterales().items() if cle not in FR
    }
    assert manquantes == {}, f"clés absentes de strings/fr.py : {manquantes}"


def test_les_deux_dictionnaires_portent_les_memes_cles() -> None:
    """Une clé traduite d'un seul côté s'affiche en anglais dans une session FR.

    Écrire un libellé en anglais n'est pas plus neutre que l'écrire en français.
    """
    assert sorted(set(EN) - set(FR)) == [], "présentes en EN, absentes en FR"
    assert sorted(set(FR) - set(EN)) == [], "présentes en FR, absentes en EN"
