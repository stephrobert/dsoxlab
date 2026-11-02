"""La preuve poussée nomme les contrôles ratés, sans jamais écarter la ligne."""
from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import pytest

from dsoxlab.sync.magasin import MAX_CONTROLES_NOMMES, _reduire_une_ligne

QUAND = datetime(2026, 11, 2, tzinfo=UTC)
ENTETE = {"catalogue": "conteneurs", "revision": "abc123",
          "version_producteur": "0.7.0"}
BASE: dict[str, Any] = {
    "catalog": "conteneurs", "lab_id": "epreuve", "lab_type": "challenge",
    "validated": False, "score": 80, "max_score": 100,
    "passed_tests": 4, "total_tests": 5, "hints_used": 0,
    "attempted_at": "2026-11-02T10:00:00Z",
}


@pytest.mark.parametrize("valeur,attendu", [
    (["test_a", "test_b"], ["test_a", "test_b"]),
    ([], []),
    (None, []),
    ("pas une liste", []),
    (42, []),
    ({"a": 1}, []),
])
def test_aucune_forme_n_ecarte_la_ligne(valeur: object, attendu: list[str]) -> None:
    """LA RÈGLE DU MODULE : ne jamais émettre une ligne que le portail écarte.

    Une seule ligne écartée lui fait rendre un magasin VIDE, donc effacer
    l'historique affiché de l'apprenant, sans message et sans retour possible.
    Un champ nouveau ne doit donc jamais pouvoir faire écarter une ligne,
    quelle que soit sa forme, y compris celle d'un export d'une autre version.
    """
    ligne = dict(BASE)
    if valeur is not None:
        ligne["failed_checks"] = valeur
    rendu = _reduire_une_ligne(ligne, ENTETE, QUAND)
    assert not isinstance(rendu, str), f"ligne écartée : {rendu}"
    assert rendu["failed_checks"] == attendu


def test_une_liste_trop_longue_est_tronquee() -> None:
    """Ces noms viennent d'une sortie pytest, donc leur nombre n'est pas borné.

    Le portail a besoin de quoi orienter une révision, pas d'un journal : une
    suite inattendue en rendrait des centaines, et le magasin grossirait sans
    fin pour une information que personne ne lirait.
    """
    ligne = {**BASE, "failed_checks": [f"test_{n}" for n in range(100)]}
    rendu = _reduire_une_ligne(ligne, ENTETE, QUAND)
    assert not isinstance(rendu, str)
    assert len(rendu["failed_checks"]) == MAX_CONTROLES_NOMMES


def test_le_schema_de_la_preuve_reste_a_un() -> None:
    """Le champ est ADDITIF, et le numéro de schéma ne bouge pas.

    Le monter garantirait le refus par un portail qui ne connaît que 1,
    c'est-à-dire exactement le cas destructeur. Un champ de plus est ignoré par
    un lecteur tolérant ; un numéro de schéma inconnu ne l'est jamais.
    """
    rendu = _reduire_une_ligne({**BASE, "failed_checks": ["test_a"]}, ENTETE, QUAND)
    assert not isinstance(rendu, str)
    assert rendu["schema"] == 1
