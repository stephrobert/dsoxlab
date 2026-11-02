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


# ── le refus, et ce que le compte ne dit pas ──────────────────────────────

class TestLaPreuveDitLeRefus:
    """Le portail doit pouvoir dire qu'une épreuve est refusée, et pourquoi.

    `push` transmettait `failed_checks` mais ni `blocking_failed` ni le
    verdict : un apprenant qui passait par son compte ne voyait jamais qu'une
    épreuve était refusée sur son exigence critique, alors que `submit` et
    l'export le savaient. C'était une moitié de chaînon.
    """

    @staticmethod
    def _preuve(**extra: object) -> dict:
        rendu = _reduire_une_ligne({**BASE, **extra}, ENTETE, QUAND)
        assert not isinstance(rendu, str), f"ligne écartée : {rendu}"
        return rendu

    def test_une_epreuve_refusee_dit_pourquoi(self) -> None:
        p = self._preuve(
            failed_checks=["test_critique"],
            blocking_failed=["test_critique"],
            exam={"passing_score": 75, "percentage": 80, "passed": False})
        assert p["blocking_failed"] == ["test_critique"]
        assert p["exam_passed"] is False

    def test_une_epreuve_recue_le_dit_aussi(self) -> None:
        p = self._preuve(
            failed_checks=[], blocking_failed=[],
            exam={"passing_score": 75, "percentage": 100, "passed": True})
        assert p["blocking_failed"] == []
        assert p["exam_passed"] is True

    def test_un_lab_ordinaire_ne_porte_pas_de_verdict(self) -> None:
        """`None` et non `False` : un lab sans seuil n'est pas recalé."""
        p = self._preuve(lab_type="lab", failed_checks=["test_x"],
                         blocking_failed=[], exam=None)
        assert p["exam_passed"] is None

    def test_une_tentative_d_avant_0_7_0_est_INCONNUE_et_non_vide(self) -> None:
        """LA DISTINCTION QUI COMPTE, et que `[]` effacerait.

        Une tentative enregistrée avant 0.7.0 n'a pas ces colonnes. Envoyer
        `[]` affirmerait qu'aucun contrôle bloquant n'a échoué, et `False`
        qu'elle est recalée : deux affirmations qu'on ne peut pas faire.
        """
        p = self._preuve()
        assert p["blocking_failed"] is None
        assert p["exam_passed"] is None

    @pytest.mark.parametrize("bl,ex", [
        ("pas une liste", "pas un objet"),
        (42, 42),
        ({"a": 1}, {"passed": "oui"}),
        (None, None),
    ])
    def test_aucune_forme_malformee_n_ecarte_la_ligne(
        self, bl: object, ex: object
    ) -> None:
        """Une ligne écartée vide le magasin de l'apprenant : jamais ça."""
        p = self._preuve(blocking_failed=bl, exam=ex)
        assert p["blocking_failed"] is None
        assert p["exam_passed"] is None

    def test_la_borne_vaut_pour_les_deux_listes(self) -> None:
        p = self._preuve(blocking_failed=[f"t{n}" for n in range(100)])
        assert len(p["blocking_failed"]) == MAX_CONTROLES_NOMMES

    def test_le_schema_ne_bouge_toujours_pas(self) -> None:
        """Deux champs de plus, et le numéro reste à 1.

        Le monter garantirait le refus par un portail qui ne connaît que 1,
        c'est-à-dire le cas destructeur que ce module existe pour éviter.
        """
        assert self._preuve()["schema"] == 1
