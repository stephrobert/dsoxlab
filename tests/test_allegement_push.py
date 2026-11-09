"""Faire tenir les preuves sous les limites du portail, sans rien perdre d'essentiel.

Décision du lot E (#336) : avant de refuser pour taille, `push` allège la charge
ENVOYÉE, des lignes les plus anciennes aux plus récentes, en abandonnant
`criteria`, puis `hints_seen`, puis `not_evaluated`. Jamais de liste tronquée,
jamais une ligne retirée, jamais un champ v1 touché, jamais la base locale.

Les mesures sont celles du portail (`mesurer_charge` : charge échappée, puis
gzip), pas une estimation.
"""

from __future__ import annotations

import copy
import json
import random
from types import SimpleNamespace
from typing import Any

import pytest

from dsoxlab.cli.compte import _dire_l_envoi
from dsoxlab.i18n import set_lang
from dsoxlab.services import sync_service
from dsoxlab.services.sync_service import Envoi
from dsoxlab.sync import ChargeRefusee
from dsoxlab.sync import magasin as m
from dsoxlab.sync.allegement import CHAMPS_ALLEGEABLES, alleger
from dsoxlab.sync.protocole import (
    BRUT_PAR_SECTION,
    COMPRESSE_PAR_SECTION,
    ClientPortail,
    mesurer_charge,
)

from .test_push_tentative import (
    MAINTENANT,
    UUID_A,
    _document,
    _ligne,
    _ligne_typique,
    _preuve,
)

DETAIL = CHAMPS_ALLEGEABLES


def _hasard(graine: int) -> str:
    """Un jeton sans régularité, déterministe : la compression n'y gagne rien."""
    return f"indice-{random.Random(graine).getrandbits(60):x}"  # noqa: S311


def _magasin(*preuves: Any) -> m.Magasin:
    return {"v": 1, "preuves": list(preuves), "dernierImport": None}


def _preuves(n: int, fabrique: Any = _ligne_typique) -> list[m.Preuve]:
    issue = m.convertir(_document(*(fabrique(i) for i in range(n))), maintenant=MAINTENANT)
    assert issue["ecartees"] == {}
    return issue["preuves"]


def _tient(magasin: m.Magasin) -> bool:
    brut, compresse = mesurer_charge(m.serialiser(magasin))
    return brut <= BRUT_PAR_SECTION and compresse <= COMPRESSE_PAR_SECTION


# ── ce qui tient déjà n'est pas touché ────────────────────────────────────


def test_ce_qui_tient_deja_n_est_pas_touche() -> None:
    magasin = _magasin(*_preuves(50))

    allege, degradees = alleger(magasin)

    assert allege is magasin and degradees == 0


# ── l'allègement ──────────────────────────────────────────────────────────


@pytest.fixture(scope="module")
def deux_mille() -> list[m.Preuve]:
    return _preuves(2000)


def test_deux_mille_lignes_typiques_ne_tiennent_pas_telles_quelles_et_tiennent_allegees(
    deux_mille: list[m.Preuve], capsys: pytest.CaptureFixture[str]
) -> None:
    magasin = _magasin(*deux_mille)
    assert not _tient(magasin), "sans allègement, ces 2 000 lignes seraient refusées"

    allege, degradees = alleger(magasin)

    brut, compresse = mesurer_charge(m.serialiser(allege))
    with capsys.disabled():
        print(f"\n2000 lignes typiques : {mesurer_charge(m.serialiser(magasin))[0]} octets bruts "
              f"-> {brut} après allègement de {degradees} lignes (compressé {compresse})")
    assert _tient(allege)
    assert 0 < degradees < 2000, "on n'allège que ce qu'il faut"
    assert len(allege["preuves"]) == 2000, "aucune ligne n'est retirée"


def test_l_allegement_ne_touche_que_le_detail_et_ne_tronque_rien(
    deux_mille: list[m.Preuve],
) -> None:
    allege, _ = alleger(_magasin(*deux_mille))

    for avant, apres in zip(deux_mille, allege["preuves"], strict=True):
        for cle, valeur in avant.items():
            if cle in DETAIL:
                # Soit intact, soit inconnu : JAMAIS une liste tronquée.
                assert apres[cle] == valeur or apres[cle] is None, cle
            else:
                assert apres[cle] == valeur, f"le champ v1 {cle} ne doit pas bouger"


def test_les_lignes_les_plus_anciennes_perdent_leur_detail_d_abord(
    deux_mille: list[m.Preuve],
) -> None:
    allege, degradees = alleger(_magasin(*deux_mille))
    chronologie = sorted(
        zip(deux_mille, allege["preuves"], strict=True),
        key=lambda paire: paire[0]["attempted_at"],
    )

    touchees = [
        any(apres[c] != avant[c] for c in DETAIL) for avant, apres in chronologie
    ]
    # Une ligne dégradée est plus ancienne que toute ligne intacte : les
    # lignes touchées forment un PRÉFIXE de la chronologie.
    assert touchees == sorted(touchees, reverse=True)
    assert sum(touchees) == degradees
    # La plus récente garde tout son détail.
    avant, apres = chronologie[-1]
    assert apres == avant


def test_l_ordre_dans_une_ligne_est_criteria_puis_hints_puis_not_evaluated(
    deux_mille: list[m.Preuve],
) -> None:
    allege, _ = alleger(_magasin(*deux_mille))

    for ligne in allege["preuves"]:
        if ligne["hints_seen"] is None and deux_mille[0]["hints_seen"] is not None:
            assert ligne["criteria"] is None
        if ligne["not_evaluated"] is None:
            assert ligne["criteria"] is None and ligne["hints_seen"] is None


def test_l_allegement_va_jusqu_aux_champs_suivants_si_besoin() -> None:
    """Des lignes dont le seul poids est `hints_seen` : `criteria` n'y suffit pas."""
    def lourde(i: int) -> dict[str, Any]:
        ligne = _ligne_typique(i)
        ligne["criteria"] = None
        ligne["not_evaluated"] = None
        ligne["hints_seen"] = [
            {"index": k, "id": _hasard(i * 100 + k) * 3, "criterion": None}
            for k in range(20)
        ]
        return ligne

    preuves = _preuves(1500, lourde)
    magasin = _magasin(*preuves)
    assert not _tient(magasin)

    allege, degradees = alleger(magasin)

    assert _tient(allege) and degradees > 0
    assert any(p["hints_seen"] is None for p in allege["preuves"])
    assert all(p["criteria"] is None for p in allege["preuves"])


def test_la_limite_compressee_mord_aussi() -> None:
    """Des identifiants aléatoires se compressent mal : le gzip décide, pas le brut."""
    def aleatoire(i: int) -> dict[str, Any]:
        ligne = _ligne_typique(i)
        generateur = random.Random(i)  # noqa: S311
        ligne["criteria"] = [
            {"id": "c" + f"{generateur.getrandbits(252):063x}", "state": "satisfied",
             "phase": "call", "mention": None, "observation": None}
            for _ in range(40)
        ]
        return ligne

    magasin = _magasin(*_preuves(300, aleatoire))
    brut, compresse = mesurer_charge(m.serialiser(magasin))
    assert brut <= BRUT_PAR_SECTION < brut * 2, "le brut tient"
    assert compresse > COMPRESSE_PAR_SECTION, "mais le compressé ne tient pas"

    allege, degradees = alleger(magasin)

    assert degradees > 0 and _tient(allege)


def test_l_allegement_ne_touche_pas_ses_entrees(deux_mille: list[m.Preuve]) -> None:
    magasin = _magasin(*deux_mille)
    avant = copy.deepcopy(magasin)

    alleger(magasin)

    assert magasin == avant, "la charge envoyée est allégée, jamais la source"


def test_trois_mille_lignes_ne_tiennent_pas_meme_allegees_et_le_refus_s_applique() -> None:
    """Le plancher est le format v1 : environ 630 octets par ligne, donc 2 378 lignes.

    Au-delà, on rend la charge allégée au maximum et le refus habituel
    (`sync_charge_trop_grosse`) s'applique : on ne cache pas une limite atteinte.
    """
    allege, degradees = alleger(_magasin(*_preuves(3000)))

    assert degradees == 3000
    assert all(p[c] is None for p in allege["preuves"] for c in DETAIL)
    assert len(allege["preuves"]) == 3000
    with pytest.raises(ChargeRefusee) as refus:
        ClientPortail._verifier_taille(m.serialiser(allege))
    assert refus.value.cle == "sync_charge_trop_grosse"


# ── la fusion : la plus riche gagne ───────────────────────────────────────


def _pauvre(preuve: m.Preuve) -> m.Preuve:
    """La même ligne, allégée comme `alleger` le fait."""
    copie = dict(preuve)
    for champ in DETAIL:
        copie[champ] = None
    return copie  # type: ignore[return-value]


def test_une_ligne_locale_plus_pauvre_n_ecrase_pas_le_detail_du_portail() -> None:
    riche = _preuve()
    fusion, ajoutees, doublons = m.fusionner(_magasin(riche), [_pauvre(riche)])

    assert fusion["preuves"] == [riche]
    assert (ajoutees, doublons) == (0, 1)


def test_une_ligne_locale_plus_riche_retablit_le_detail_allege_du_portail() -> None:
    riche = _preuve()
    fusion, _, _ = m.fusionner(_magasin(_pauvre(riche)), [riche])
    assert fusion["preuves"] == [riche]


def test_a_richesse_egale_la_ligne_du_portail_reste() -> None:
    distante = _preuve()
    locale = dict(distante, hints_seen=[{"index": 9, "id": None, "criterion": None}])
    fusion, _, _ = m.fusionner(_magasin(distante), [locale])  # type: ignore[list-item]
    assert fusion["preuves"] == [distante]


def test_une_ligne_riche_d_un_autre_identifiant_ne_remplace_pas() -> None:
    distante = _pauvre(_preuve())
    autre = _preuve(attempt_id="9f1c2d3e-4a5b-4c6d-8e7f-0a1b2c3d4e5f")
    fusion, _, doublons = m.fusionner(_magasin(distante), [autre])
    assert fusion["preuves"] == [distante] and doublons == 1


def test_un_identifiant_ajoute_vaut_de_la_richesse() -> None:
    """Une ligne d'avant 0.8.0 n'a ni identifiant ni détail : la nôtre la remplace."""
    ancienne = {k: v for k, v in _preuve().items()
                if k not in ("attempt_id", "lab_digest", "not_evaluated", "hints_seen", "criteria")}
    fusion, _, _ = m.fusionner(_magasin(ancienne), [_pauvre(_preuve())])
    assert fusion["preuves"][0]["attempt_id"] == UUID_A


# ── l'idempotence ─────────────────────────────────────────────────────────


def test_pousser_deux_fois_donne_deux_fois_la_meme_charge(
    deux_mille: list[m.Preuve],
) -> None:
    """Le portail porte des lignes allégées ; le local les redonne riches ; la
    charge finale est la même, donc rien n'est réécrit."""
    premiere, _ = alleger(m.fusionner(m.lire(None), deux_mille)[0])
    fusion2, _, _ = m.fusionner(premiere, deux_mille)
    seconde, _ = alleger(fusion2)

    assert m.serialiser(seconde) == m.serialiser(premiere)


def test_un_nouvel_ajout_n_allege_que_les_plus_anciennes_de_plus(
    deux_mille: list[m.Preuve],
) -> None:
    premiere, d1 = alleger(m.fusionner(m.lire(None), deux_mille)[0])
    nouvelles = _preuves(2100)[2000:]
    seconde, d2 = alleger(m.fusionner(premiere, [*deux_mille, *nouvelles])[0])

    assert len(seconde["preuves"]) == 2100
    assert _tient(seconde)
    assert d2 >= d1


# ── de bout en bout : `pousser`, la base locale, le message ───────────────


class _FauxClient:
    ecritures: list[str]
    distant: str | None

    def __init__(self, _api: str, _jeton: Any) -> None:
        pass

    def lire(self) -> tuple[dict[str, Any], str | None]:
        return {"revision": len(self.ecritures), "empreinte": ""}, self.distant

    def ecrire(self, revision: int, charge: str) -> dict[str, Any]:
        ClientPortail._verifier_taille(charge)  # les vraies limites du portail
        self.ecritures.append(charge)
        type(self).distant = charge
        return {"revision": revision + 1, "empreinte": "", "rejoue": False}


@pytest.fixture
def faux_portail(monkeypatch: pytest.MonkeyPatch) -> Any:
    _FauxClient.ecritures = []
    _FauxClient.distant = None
    monkeypatch.setattr(sync_service, "ClientPortail", _FauxClient)
    return SimpleNamespace(api="https://api.example.test", identite=None)


def _document_de(n: int) -> dict[str, Any]:
    return _document(*(_ligne_typique(i) for i in range(n)))


def test_pousser_allege_ecrit_sous_les_limites_et_le_dit(faux_portail: Any) -> None:
    document = _document_de(2000)
    avant = copy.deepcopy(document)

    envoi = sync_service.pousser(faux_portail, document)

    assert envoi.ecrit and envoi.degradees > 0
    (charge,) = _FauxClient.ecritures
    brut, compresse = mesurer_charge(charge)
    assert brut <= BRUT_PAR_SECTION and compresse <= COMPRESSE_PAR_SECTION
    assert len(json.loads(charge)["preuves"]) == 2000
    assert document == avant, "le document local (donc la base) n'est pas modifié"


def test_la_base_locale_n_est_pas_modifiee_par_l_allegement(
    tmp_path: Any, faux_portail: Any
) -> None:
    from dsoxlab.sessions.store import get_all_results, record_result

    for i in range(5):
        record_result(
            tmp_path, lab_id="lab-un", section="s", score=40, max_score=100,
            passed_tests=2, total_tests=5, hints_used=0,
            attempt_id=_ligne_typique(i)["attempt_id"], lab_digest="250710ce5dd68756",
            criteria=json.dumps([{"id": "test_a", "state": "unsatisfied", "phase": "call",
                                  "mention": None, "origin": None, "author_message": None}]),
            hints_seen="[]",
        )
    avant = get_all_results(tmp_path)

    sync_service.pousser(faux_portail, _document_de(2000))

    assert get_all_results(tmp_path) == avant


def test_un_second_push_n_ecrit_rien(faux_portail: Any) -> None:
    document = _document_de(2000)
    sync_service.pousser(faux_portail, document)

    seconde = sync_service.pousser(faux_portail, document)

    assert not seconde.ecrit
    assert len(_FauxClient.ecritures) == 1, "aucune révision brûlée pour rien"


def test_le_message_dit_combien_de_tentatives_sont_parties_sans_detail(
    capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    envoi = Envoi(ajoutees=2000, doublons=0, ecartees={}, revision=1, rejoue=False,
                  total=2000, degradees=1713)
    for langue, attendu in (("en", "1713 older attempt(s) were sent without"),
                            ("fr", "1713 tentative(s) ancienne(s) sont parties sans")):
        monkeypatch.setenv("DSOXLAB_LANG", langue)
        set_lang(langue)
        _dire_l_envoi(envoi)
        assert attendu in " ".join(capsys.readouterr().out.split())
    set_lang("en")


def test_sans_allegement_le_message_ne_s_affiche_pas(
    capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("DSOXLAB_LANG", "en")
    set_lang("en")
    _dire_l_envoi(Envoi(ajoutees=1, doublons=0, ecartees={}, revision=1, rejoue=False, total=1))
    assert "older attempt" not in capsys.readouterr().out


def test_les_lignes_de_depart_ne_sont_pas_vides() -> None:
    """Garde-fou du garde-fou : `_ligne` produit bien du détail à alléger."""
    ligne = m.convertir(_document(_ligne()), maintenant=MAINTENANT)["preuves"][0]
    assert all(ligne[c] for c in DETAIL)
