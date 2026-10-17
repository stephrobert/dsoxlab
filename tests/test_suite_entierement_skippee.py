"""Une suite entièrement skippée n'a rien mesuré, et ne conclut donc rien.

Trouvé le 2026-10-17 par la session qui réatteste les labs du site, sur un
`dsoxlab check` dont les cinq tests avaient skippé. Le moteur concluait TROIS
fois, et dans deux directions opposées :

    "ok": true, "passed": 0, "total": 5, "score": 0, "recorded": true
    ✔ Tous les tests sont passés.

Il annonçait le succès, parce que `ok` reprenait le code de retour de pytest,
qui sort en 0 quand tout skippe. Il notait 0. Et il INSCRIVAIT ce 0 dans
l'historique de l'apprenant. Un lecteur automatisé devait choisir entre
`ok: true` et `score: 0`, qui se contredisent ; un apprenant lisait « tous les
tests sont passés » sous un « 0 / 100 ».

La notion existait pourtant, `a_mesure()`, et un seul endroit décidait. C'est
son implémentation qui était fausse : `total > 0` est vrai pour cinq tests
skippés, puisque le total les compte. Mesurer, c'est EXÉCUTER.
"""

from __future__ import annotations

import pathlib

import pytest
from typer.testing import CliRunner

from dsoxlab.cli import app
from dsoxlab.services.lab_service import CheckResult, a_mesure, compute_score

RESUME_TOUT_SKIPPE = """\
============================= test session starts ==============================
collecting ... collected 5 items

labs/x/challenge/tests/test_functional.py::test_un SKIPPED [ 20%]
labs/x/challenge/tests/test_functional.py::test_deux SKIPPED [ 40%]
labs/x/challenge/tests/test_functional.py::test_trois SKIPPED [ 60%]
labs/x/challenge/tests/test_functional.py::test_quatre SKIPPED [ 80%]
labs/x/challenge/tests/test_functional.py::test_cinq SKIPPED [100%]

============================== 5 skipped in 0.01s ==============================
"""

RESUME_MELANGE = """\
============================= test session starts ==============================
collected 4 items

============================= 3 passed, 1 skipped in 0.42s =====================
"""


def _resultat(sortie: str, *, ok: bool) -> CheckResult:
    """Un CheckResult construit comme `check_lab` le fait, parseur compris."""
    from dsoxlab.services.lab_service import _parse_counts

    passed, total, skipped = _parse_counts(sortie)
    return CheckResult(ok=ok, output=sortie, passed=passed, total=total,
                       skipped=skipped)


def test_cinq_tests_skippes_ne_sont_pas_une_mesure() -> None:
    """Le cas exact du terrain : pytest sort en 0, et rien n'a tourné."""
    resultat = _resultat(RESUME_TOUT_SKIPPE, ok=True)

    assert (resultat.passed, resultat.total, resultat.skipped) == (0, 5, 5)
    assert not a_mesure(resultat), (
        "cinq tests collectés puis skippés n'ont rien mesuré ; l'ancien "
        "`total > 0` répondait oui, et le 0 était inscrit dans l'historique"
    )


def test_un_seul_test_execute_suffit_a_mesurer() -> None:
    """La frontière est l'exécution, pas la perfection de la suite.

    Un lab dont un test skippe légitimement (une distribution qui n'a pas le
    composant) reste mesuré par les autres : le refuser aurait transformé la
    correction en régression, et aurait cessé de noter des labs qui tournent.
    """
    resultat = _resultat(RESUME_MELANGE, ok=True)

    assert (resultat.passed, resultat.total, resultat.skipped) == (3, 4, 1)
    assert a_mesure(resultat)


def test_aucun_test_collecte_reste_une_non_mesure() -> None:
    """L'autre cause, antérieure : pytest n'a RIEN pu collecter."""
    resultat = CheckResult(ok=False, output="", passed=0, total=0)

    assert not a_mesure(resultat)


def test_le_score_d_une_suite_skippee_ne_vaut_pas_zero_sur_le_fond() -> None:
    """Le score reste 0, et c'est `a_mesure` qui dit qu'il ne veut rien dire.

    On ne fabrique pas une note pour une exécution qui n'a rien mesuré : le 0
    existe, mais l'appelant doit le présenter comme une absence et non comme un
    exercice raté. C'est la raison d'être de `enregistre` dans `ScoreResult`.
    """
    assert compute_score(passed=0, total=5, max_score=100, hints_cost=0) == 0


# ── Le code de sortie, qui doit dire la même chose que le JSON ───────────────


def _depot_minimal(racine: pathlib.Path) -> pathlib.Path:
    """Un dépôt de labs réel, le plus petit possible : un meta.yml, un lab shell."""
    racine.mkdir(parents=True, exist_ok=True)
    (racine / "meta.yml").write_text(
        "repo:\n  id: skip-demo\n  category: demo\n", encoding="utf-8",
    )
    lab = racine / "labs" / "demo" / "premier"
    lab.mkdir(parents=True)
    (lab / "lab.yaml").write_text(
        "id: premier\n"
        "title: Premier\n"
        "level: l1\n"
        "skills: [rien]\n"
        "distros: [alma10]\n"
        "doc_url: https://example.test/doc\n"
        "runtime:\n"
        "  type: shell\n"
        "  workdir: challenge/work\n",
        encoding="utf-8",
    )
    return racine


def _check(
    racine: pathlib.Path,
    monkeypatch: pytest.MonkeyPatch,
    *,
    json: bool,
) -> int:
    """`dsoxlab check` sur une exécution entièrement skippée, et son code de retour.

    Seul `_run_check` est remplacé : tout le reste du chemin de la commande
    joue, puisque c'est lui qui décide, et c'est ce qu'on mesure.
    """
    from dsoxlab.cli import progression

    resultat = _resultat(RESUME_TOUT_SKIPPE, ok=True)
    monkeypatch.setattr(
        progression, "_run_check",
        lambda root, lab, target, quiet=False: (resultat, 0, 100),
    )

    args = ["check", "premier", "--lab-home", str(racine)]
    return CliRunner().invoke(app, [*args, "--json"] if json else args).exit_code


def test_une_suite_skippee_sort_en_code_non_nul(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Un appelant qui lit le code de retour ne doit pas lire un succès."""
    racine = _depot_minimal(tmp_path / "depot")

    assert _check(racine, monkeypatch, json=False) != 0


def test_le_mode_json_rend_le_meme_code_que_le_mode_humain(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    """La 0.4.1 n'avait fermé que le chemin humain.

    Le chemin machine retourne AVANT lui, et sa condition de sortie était
    `not result.ok` : vraie d'un échec, fausse d'une suite entièrement skippée,
    puisque pytest sort en 0 quand tout skippe. La même situation rendait donc
    0 en `--json` et 1 sans. C'est `ok` qui ne peut pas servir de verdict, et
    le chemin machine l'écrivait pourtant dans son propre commentaire.
    """
    racine = _depot_minimal(tmp_path / "depot")

    humain = _check(racine, monkeypatch, json=False)
    machine = _check(racine, monkeypatch, json=True)

    assert machine == humain != 0, (
        f"--json rend {machine}, le mode humain {humain} : deux conclusions "
        "opposées sur la même exécution"
    )
