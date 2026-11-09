"""Ce que `push` transporte de la tentative (lot E de #336, 0.8.0).

La preuve poussée gagne `attempt_id`, `lab_digest`, `not_evaluated`,
`hints_seen` et `criteria` réduit à `{id, state}`. Le portail relit son magasin
en TOUT OU RIEN : une ligne qu'il écarterait vide l'historique de l'apprenant.
Tout ce fichier tient donc deux promesses :

- **aucun champ nouveau ne fait refuser une ligne** : mal formé, il devient
  `None` (inconnu), et une liste trop longue aussi, jamais tronquée ;
- **`fusionner` enrichit sans jamais appauvrir** : une ligne qui porte un
  `attempt_id` remplace la même tentative sans identifiant, jamais l'inverse.
"""

from __future__ import annotations

import json
import random
import uuid
from datetime import UTC, datetime
from typing import Any

import pytest

from dsoxlab.sync import magasin as m
from dsoxlab.sync.protocole import BRUT_PAR_SECTION, mesurer_charge

MAINTENANT = datetime(2026, 10, 28, 12, 0, 0, tzinfo=UTC)
UUID_A = "135b6e1e-bc72-49ca-8d45-35ed9c311436"
UUID_B = "9f1c2d3e-4a5b-4c6d-8e7f-0a1b2c3d4e5f"


def _ligne(**surcharges: Any) -> dict[str, Any]:
    base: dict[str, Any] = {
        "catalog": "cat",
        "lab_id": "lab-un",
        "lab_type": "challenge",
        "section": "s",
        "validated": False,
        "score": 40,
        "max_score": 100,
        "passed_tests": 2,
        "total_tests": 5,
        "hints_used": 1,
        "failed_checks": ["test_a", "test_b"],
        "blocking_failed": [],
        "attempted_at": "2026-10-27T11:06:54.708357+00:00",
        "exam": None,
        "attempt_id": UUID_A,
        "lab_digest": "250710ce5dd68756",
        "catalog_revision": "abc1234",
        "not_evaluated": ["test_b"],
        "hints_seen": [{"index": 0, "id": "indice-un", "criterion": None}],
        "criteria": [
            {"id": "test_a", "state": "unsatisfied", "phase": "call",
             "mention": None, "observation": "Une phrase de l'auteur."},
            {"id": "test_b", "state": "not_evaluated", "phase": "setup",
             "mention": "teardown_error", "observation": None},
            {"id": "test_c", "state": "satisfied", "phase": "call",
             "mention": None, "observation": None},
            {"id": "test_d", "state": "skipped", "phase": "setup",
             "mention": None, "observation": None},
        ],
    }
    base.update(surcharges)
    return base


def _document(*lignes: dict[str, Any]) -> dict[str, Any]:
    return {
        "schema": "dsoxlab-evidence-v1",
        "producer": {"name": "dsoxlab", "version": "dsoxlab 0.8.0"},
        "catalog": {"id": "cat", "version": "abc1234"},
        "results": list(lignes),
        "count": len(lignes),
    }


def _preuve(**surcharges: Any) -> m.Preuve:
    issue = m.convertir(_document(_ligne(**surcharges)), maintenant=MAINTENANT)
    assert issue["ecartees"] == {}, issue["ecartees"]
    return issue["preuves"][0]


# ── la forme poussée ──────────────────────────────────────────────────────


def test_la_preuve_porte_les_cinq_champs_de_tentative() -> None:
    preuve = _preuve()

    assert preuve["attempt_id"] == UUID_A
    assert preuve["lab_digest"] == "250710ce5dd68756"
    assert preuve["not_evaluated"] == ["test_b"]
    assert preuve["hints_seen"] == [{"index": 0, "id": "indice-un", "criterion": None}]


def test_les_criteres_sont_reduits_a_id_et_etat() -> None:
    criteres = _preuve()["criteria"]

    assert criteres == [
        {"id": "test_a", "state": "unsatisfied"},
        {"id": "test_b", "state": "not_evaluated"},
        {"id": "test_c", "state": "satisfied"},
        {"id": "test_d", "state": "skipped"},
    ]
    brut = json.dumps(criteres)
    for absent in ("observation", "phase", "mention", "Une phrase", "teardown_error"):
        assert absent not in brut


def test_une_ligne_d_avant_0_8_0_porte_null_partout() -> None:
    ancienne = {
        k: v for k, v in _ligne().items()
        if k not in ("attempt_id", "lab_digest", "not_evaluated", "hints_seen", "criteria")
    }
    issue = m.convertir(_document(ancienne), maintenant=MAINTENANT)

    assert issue["ecartees"] == {}
    preuve = issue["preuves"][0]
    assert {k: preuve[k] for k in (  # type: ignore[literal-required]
        "attempt_id", "lab_digest", "not_evaluated", "hints_seen", "criteria",
    )} == dict.fromkeys(
        ("attempt_id", "lab_digest", "not_evaluated", "hints_seen", "criteria")
    )


@pytest.mark.parametrize(
    ("champ", "mauvais"),
    [
        ("attempt_id", "pas-un-uuid"),
        ("attempt_id", 42),
        ("attempt_id", UUID_A.upper()),
        ("lab_digest", "../../etc/passwd"),
        ("lab_digest", "250710ce5dd6875"),
        ("lab_digest", None),
        ("not_evaluated", "test_b"),
        ("not_evaluated", {"a": 1}),
        ("hints_seen", "oui"),
        ("hints_seen", [{"index": "zéro"}]),
        ("hints_seen", ["pas un objet"]),
        ("hints_seen", [{"index": True}]),
        ("criteria", {"id": "x"}),
        ("criteria", ["x"]),
        ("criteria", [{"id": "a b", "state": "satisfied"}]),
        ("criteria", [{"id": "ok", "state": "invente"}]),
        ("criteria", [{"id": "/home/marie/x.py::t", "state": "satisfied"}]),
        ("criteria", [{"state": "satisfied"}]),
    ],
)
def test_un_champ_mal_forme_devient_null_sans_refuser_la_ligne(
    champ: str, mauvais: Any
) -> None:
    issue = m.convertir(_document(_ligne(**{champ: mauvais})), maintenant=MAINTENANT)

    assert issue["ecartees"] == {}, "aucun motif d'écart nouveau : une ligne écartée vide le magasin"
    assert len(issue["preuves"]) == 1
    valeur = issue["preuves"][0][champ]  # type: ignore[literal-required]
    if champ == "not_evaluated" and isinstance(mauvais, (str, dict)):
        assert valeur is None
    else:
        assert valeur is None


def test_les_quarante_criteres_passent_le_quarante_et_unieme_vaut_inconnu() -> None:
    def liste(n: int) -> list[dict[str, Any]]:
        return [{"id": f"test_{i}", "state": "satisfied", "phase": "call",
                 "mention": None, "observation": None} for i in range(n)]

    assert len(_preuve(criteria=liste(m.MAX_CRITERES_POUSSES))["criteria"] or []) == 40
    # Au-delà : inconnu, JAMAIS une liste tronquée qui mentirait.
    assert _preuve(criteria=liste(41))["criteria"] is None


def test_les_vingt_indices_passent_le_vingt_et_unieme_vaut_inconnu() -> None:
    def indices(n: int) -> list[dict[str, Any]]:
        return [{"index": i, "id": None, "criterion": None} for i in range(n)]

    assert len(_preuve(hints_seen=indices(20))["hints_seen"] or []) == 20
    assert _preuve(hints_seen=indices(21))["hints_seen"] is None


def test_les_noms_non_evalues_sont_bornes_comme_les_controles_rates() -> None:
    noms = [f"test_{i}" for i in range(50)]
    assert _preuve(not_evaluated=noms)["not_evaluated"] == noms[: m.MAX_CONTROLES_NOMMES]
    assert _preuve(not_evaluated=[])["not_evaluated"] == []


# ── la fusion ─────────────────────────────────────────────────────────────


def _magasin(*preuves: Any) -> m.Magasin:
    return m.lire(json.dumps({"v": 1, "preuves": list(preuves), "dernierImport": "2026-10-01T00:00:00+00:00"}))


def _ancienne() -> dict[str, Any]:
    """La même tentative, telle que 0.7.x l'a poussée : sans identifiant."""
    preuve = dict(_preuve())
    for cle in ("attempt_id", "lab_digest", "not_evaluated", "hints_seen", "criteria"):
        del preuve[cle]
    return preuve


def test_une_ligne_avec_identifiant_remplace_la_meme_tentative_sans_identifiant() -> None:
    fusion, ajoutees, doublons = m.fusionner(_magasin(_ancienne()), [_preuve()])

    assert len(fusion["preuves"]) == 1
    assert fusion["preuves"][0]["attempt_id"] == UUID_A
    assert fusion["preuves"][0]["criteria"] is not None
    # Une tentative déjà connue : pas un ajout, et `dernierImport` ne bouge pas.
    assert (ajoutees, doublons) == (0, 1)
    assert fusion["dernierImport"] == "2026-10-01T00:00:00+00:00"


def test_jamais_l_inverse_une_ligne_sans_identifiant_n_appauvrit_pas_le_portail() -> None:
    enrichie = _preuve()
    fusion, ajoutees, doublons = m.fusionner(_magasin(enrichie), [_ancienne()])  # type: ignore[list-item]

    assert fusion["preuves"] == [enrichie]
    assert (ajoutees, doublons) == (0, 1)


def test_la_meme_tentative_enrichie_deux_fois_ne_change_plus_rien() -> None:
    premiere, _, _ = m.fusionner(_magasin(_ancienne()), [_preuve()])
    seconde, ajoutees, doublons = m.fusionner(premiere, [_preuve()])

    assert seconde["preuves"] == premiere["preuves"]
    assert (ajoutees, doublons) == (0, 1)
    assert m.serialiser(seconde) == m.serialiser(premiere)


def test_deux_lignes_de_meme_identifiant_et_de_dates_differentes_restent_deux() -> None:
    """La clé de repli est le triplet : l'identifiant seul ne dédoublonne pas."""
    a = _preuve()
    b = _preuve(attempted_at="2026-10-27T12:06:54.000000+00:00")
    assert a["attempt_id"] == b["attempt_id"]

    fusion, ajoutees, _ = m.fusionner(m.lire(None), [a, b])

    assert len(fusion["preuves"]) == 2
    assert ajoutees == 2


def test_deux_identifiants_pour_un_meme_triplet_gardent_la_ligne_du_portail() -> None:
    distante = _preuve()
    autre = _preuve(attempt_id=UUID_B)

    fusion, ajoutees, doublons = m.fusionner(_magasin(distante), [autre])

    assert fusion["preuves"][0]["attempt_id"] == UUID_A
    assert (ajoutees, doublons) == (0, 1)


def test_une_preuve_que_seul_le_portail_porte_reste_et_les_anciennes_lignes_sans_cle_aussi() -> None:
    etrangere = {"lab_id": "ailleurs", "catalogue_id": "cat", "attempted_at": "2026-10-20T08:00:00.000000+00:00"}
    fusion, ajoutees, _ = m.fusionner(_magasin(etrangere), [_preuve()])
    assert ajoutees == 1
    assert {p["lab_id"] for p in fusion["preuves"]} == {"ailleurs", "lab-un"}


# ── le plafond d'octets ───────────────────────────────────────────────────


def _uuid(i: int) -> str:
    """Un uuid4 déterministe mais sans régularité : la compression n'y gagne rien."""
    return str(uuid.UUID(int=random.Random(i).getrandbits(128), version=4))  # noqa: S311


def _ligne_typique(i: int) -> dict[str, Any]:
    """Un `challenge` ordinaire : douze critères, quatre ratés, deux indices."""
    criteres = [
        {"id": f"test_le_critere_numero_{k:02d}", "state": "unsatisfied" if k < 4 else "satisfied",
         "phase": "call", "mention": None, "observation": "x" * 100}
        for k in range(12)
    ]
    return _ligne(
        lab_id=f"lab-{i % 200}",
        attempted_at=f"2026-10-{1 + i % 27:02d}T{i % 24:02d}:{i % 60:02d}:{(i * 7) % 60:02d}.{i:06d}+00:00",
        attempt_id=_uuid(i),
        failed_checks=[f"test_le_critere_numero_{k:02d}" for k in range(4)],
        criteria=criteres,
        hints_seen=[{"index": 0, "id": "indice-un", "criterion": None},
                    {"index": 1, "id": "indice-deux", "criterion": None}],
    )


def _ligne_maximale(i: int) -> dict[str, Any]:
    """Toutes les listes au plafond, avec des identifiants de 40 caractères."""
    nom = "test_" + "n" * 35
    return _ligne(
        attempted_at=f"2026-10-{1 + i % 27:02d}T{i % 24:02d}:{i % 60:02d}:{(i * 7) % 60:02d}.{i:06d}+00:00",
        attempt_id=_uuid(i),
        failed_checks=[f"{nom}{k:02d}" for k in range(20)],
        blocking_failed=[f"{nom}{k:02d}" for k in range(20)],
        not_evaluated=[f"{nom}{k:02d}" for k in range(20)],
        hints_seen=[{"index": k, "id": f"indice-{k}", "criterion": None} for k in range(20)],
        criteria=[{"id": f"{nom}{k:02d}", "state": "unsatisfied", "phase": "call",
                   "mention": None, "observation": None} for k in range(40)],
    )


def _mesure(ligne_fabrique: Any, n: int) -> tuple[int, int]:
    """(octets bruts, octets compressés) de n lignes, comme le portail les mesure."""
    document = _document(*(ligne_fabrique(i) for i in range(n)))
    issue = m.convertir(document, maintenant=MAINTENANT)
    assert issue["ecartees"] == {}
    assert len(issue["preuves"]) == n
    return mesurer_charge(
        m.serialiser({"v": 1, "preuves": issue["preuves"], "dernierImport": None})
    )


def _sans_enrichissement(fabrique: Any) -> Any:
    def ligne(i: int) -> dict[str, Any]:
        brut = fabrique(i)
        for cle in ("attempt_id", "lab_digest", "not_evaluated", "hints_seen", "criteria"):
            brut.pop(cle, None)
        return brut

    return ligne


def test_le_plafond_d_octets_se_mesure_et_se_dit(capsys: pytest.CaptureFixture[str]) -> None:
    """Les limites du portail, mesurées comme il les mesure (`mesurer_charge`).

    Le magasin voyage comme une CHAÎNE dans la charge : il est échappé une
    seconde fois, ce qui alourdit chaque ligne d'environ 25 %. La limite qui
    mord est la brute (1,5 Mo) ; la compressée (350 Ko) ne mord pas sur des
    lignes ordinaires, mais mord sur des identifiants aléatoires (voir
    `test_allegement_push.py`).
    """
    avant = _mesure(_sans_enrichissement(_ligne_typique), 500)[0] / 500
    apres = _mesure(_ligne_typique, 500)[0] / 500
    maximale = _mesure(_ligne_maximale, 50)[0] / 50
    with capsys.disabled():
        print(
            f"\nligne typique avant 0.8.0 : {avant:.0f} octets -> {int(BRUT_PAR_SECTION // avant)} lignes"
            f"\nligne typique enrichie    : {apres:.0f} octets -> {int(BRUT_PAR_SECTION // apres)} lignes"
            f"\nligne maximale            : {maximale:.0f} octets -> {int(BRUT_PAR_SECTION // maximale)} lignes"
        )
    assert BRUT_PAR_SECTION // apres >= 900, "neuf cents tentatives enrichies doivent tenir sans allègement"
    assert BRUT_PAR_SECTION // maximale >= 150
    assert m.LIGNES_MAX == 5000
