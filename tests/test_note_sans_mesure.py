"""Une exécution qui n'a rien mesuré ne devient pas une note (issue #168).

Quand pytest ne peut pas collecter — un `conftest.py` qui lève à l'import, une
machine injoignable, une dépendance absente — le résultat porte `total == 0`.
`compute_score` refusait déjà de deviner un score dans ce cas, mais ce refus
n'allait pas jusqu'à la base : le 0 était enregistré comme une note.

La suite en dépendait, et chaque maillon était correct pris isolément :

- `get_best_scores` voyait le lab, puisqu'il avait une ligne ;
- `lab_state.calculer` le rendait `validated`, puisqu'une note existait ;
- `next` le sautait, puisqu'« un lab noté, même 0, n'est plus l'étape suivante ».

L'apprenant croyait donc avoir raté un exercice qu'il n'avait jamais pu jouer, et
son parcours avançait sans lui. Ce module éprouve la correction **et la cascade
entière**, parce que c'est elle qui faisait le dégât.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from dsoxlab.models.lab import LabDefinition
from dsoxlab.services import lab_state
from dsoxlab.services.lab_service import CheckResult, a_mesure, evaluate_lab
from dsoxlab.services.progress_service import next_pending_lab
from dsoxlab.sessions import store

_BASE = """\
id: l1-demo
title: Demo lab
level: beginner
skills: [demo]
distros: [any]
doc_url: https://example.org/docs/demo/
runtime:
  type: shell
  workdir: challenge/work
"""


@pytest.fixture(autouse=True)
def xdg_jetable(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "state"))
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "data"))


def _depot(tmp_path: Path) -> Path:
    racine = tmp_path / "catalogue"
    (racine / "labs").mkdir(parents=True, exist_ok=True)
    (racine / "meta.yml").write_text(
        "repo:\n  id: essai\n  category: essai\n", encoding="utf-8")
    return racine


def _lab(tmp_path: Path) -> LabDefinition:
    base = _depot(tmp_path) / "labs" / "l1-demo"
    base.mkdir(parents=True, exist_ok=True)
    (base / "lab.yaml").write_text(_BASE, encoding="utf-8")
    return LabDefinition.from_yaml(base / "lab.yaml")


def _rien_mesure() -> CheckResult:
    """Ce que pytest rend quand il n'a pas pu collecter."""
    return CheckResult(ok=False, output="ERROR collecting …", passed=0, total=0)


def _echec_reel() -> CheckResult:
    """Un vrai échec : des tests ont tourné, et ils ont échoué."""
    return CheckResult(ok=False, output="2 failed, 1 passed", passed=1, total=3)


# ── Le prédicat, à un seul endroit ──────────────────────────────────────────

def test_le_predicat_distingue_les_deux_situations() -> None:
    assert not a_mesure(_rien_mesure())
    assert a_mesure(_echec_reel())


# ── L'enregistrement ────────────────────────────────────────────────────────

def test_une_execution_sans_mesure_n_est_pas_enregistree(tmp_path: Path) -> None:
    racine = _depot(tmp_path)
    lab = _lab(tmp_path)

    evaluation = evaluate_lab(racine, lab, _rien_mesure())

    assert evaluation.enregistre is False
    assert store.get_best_scores(racine, [lab.id]) == {}, (
        "rien ne doit entrer en base : c'est cette ligne qui contaminait la suite"
    )


def test_un_echec_reel_reste_enregistre(tmp_path: Path) -> None:
    """Le garde-fou du garde-fou : on ne cesse pas d'enregistrer les vrais échecs.

    Un apprenant qui tente et rate doit voir sa tentative comptée ; c'est
    précisément ce qui distingue son cas de celui d'un environnement cassé.
    """
    racine = _depot(tmp_path)
    lab = _lab(tmp_path)

    evaluation = evaluate_lab(racine, lab, _echec_reel())

    assert evaluation.enregistre is True
    assert lab.id in store.get_best_scores(racine, [lab.id])


# ── La cascade, maillon par maillon ─────────────────────────────────────────

def test_le_lab_n_est_pas_declare_valide(tmp_path: Path) -> None:
    """`status` annonçait « validé » sur un lab jamais joué."""
    racine = _depot(tmp_path)
    lab = _lab(tmp_path)
    evaluate_lab(racine, lab, _rien_mesure())

    etat = lab_state.calculer(racine, lab, "essai")

    assert etat.state != lab_state.VALIDATED


def test_le_lab_reste_l_etape_suivante(tmp_path: Path) -> None:
    """`next` sautait le lab, et le parcours avançait sans l'apprenant."""
    racine = _depot(tmp_path)
    lab = _lab(tmp_path)
    evaluate_lab(racine, lab, _rien_mesure())

    suivant = next_pending_lab([lab], store.get_best_scores(racine, [lab.id]))

    assert suivant is not None, "un lab qu'aucune exécution n'a mesuré reste à faire"
    assert suivant.id == lab.id


def test_un_lab_reellement_rate_n_est_plus_l_etape_suivante(tmp_path: Path) -> None:
    """L'autre bout : le comportement d'origine ne doit pas se perdre."""
    racine = _depot(tmp_path)
    lab = _lab(tmp_path)
    evaluate_lab(racine, lab, _echec_reel())

    suivant = next_pending_lab([lab], store.get_best_scores(racine, [lab.id]))

    assert suivant is None, "un lab tenté et raté n'est plus l'étape suivante"
