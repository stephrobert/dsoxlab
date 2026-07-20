"""Tests for the scoring and progression services.

These functions used to live inside `cli.py` and `reporting/console.py`, where
they could only be exercised by invoking a command and parsing terminal output.
Extracted, they are plain functions over plain data, so the rules they encode
(how a lab is scored, what counts as "next") can be asserted directly.
"""

from __future__ import annotations

from dsoxlab.models.lab import LabDefinition, ValidationConfig
from dsoxlab.models.runtime import RuntimeConfig, RuntimeType
from dsoxlab.services import build_progress, compute_score, next_pending_lab


def _lab(
    lab_id: str,
    *,
    bloc: int = 1,
    bloc_order: int = 0,
    lab_type: str = "lab",
    bloc_name: str = "",
) -> LabDefinition:
    """A LabDefinition carrying only what the progression logic reads."""
    return LabDefinition(
        id=lab_id,
        title=lab_id,
        level="l1",
        skills=["s"],
        runtime=RuntimeConfig(type=RuntimeType.SHELL),
        distros=["alma10"],
        doc_url="https://example.test/doc",
        validation=ValidationConfig(),
        lab_type=lab_type,
        bloc=bloc,
        bloc_order=bloc_order,
        bloc_name=bloc_name,
    )


# ── compute_score ─────────────────────────────────────────────────────────────

def test_score_is_proportional_to_passing_tests() -> None:
    assert compute_score(passed=5, total=5, max_score=100, hints_cost=0) == 100
    assert compute_score(passed=3, total=4, max_score=100, hints_cost=0) == 75


def test_hints_lower_the_ceiling_not_the_final_score() -> None:
    """A hint caps what can be earned; it is not subtracted afterwards.

    All tests passing with 20 points of hints yields 80, not 100 minus 20
    applied to a partial result.
    """
    assert compute_score(passed=4, total=4, max_score=100, hints_cost=20) == 80
    assert compute_score(passed=2, total=4, max_score=100, hints_cost=20) == 40


def test_score_never_goes_negative_when_hints_exceed_the_scale() -> None:
    assert compute_score(passed=4, total=4, max_score=100, hints_cost=150) == 0


def test_no_collected_test_scores_zero_rather_than_dividing_by_zero() -> None:
    """pytest collected nothing: we do not guess a score from a non-measurement."""
    assert compute_score(passed=0, total=0, max_score=100, hints_cost=0) == 0


# ── build_progress ────────────────────────────────────────────────────────────

def test_progress_counts_only_plain_labs_in_the_ratio() -> None:
    labs = [
        _lab("a"),
        _lab("b"),
        _lab("c", lab_type="challenge"),
    ]
    scores = {"a": (100, 100)}

    (bloc,) = build_progress(labs, scores)

    assert (bloc.validated, bloc.total) == (1, 2)
    assert bloc.started is True
    assert bloc.complete is False
    assert bloc.challenge_validated is False


def test_absent_challenge_and_capstone_are_none_not_false() -> None:
    """Nothing to do must not read as something failed."""
    (bloc,) = build_progress([_lab("a")], {})

    assert bloc.challenge_validated is None
    assert bloc.capstone_validated is None


def test_untouched_bloc_has_no_average() -> None:
    (bloc,) = build_progress([_lab("a")], {})

    assert bloc.average_pct is None
    assert bloc.started is False


def test_average_covers_validated_labs_only() -> None:
    labs = [_lab("a"), _lab("b"), _lab("c")]
    scores = {"a": (100, 100), "b": (50, 100)}

    (bloc,) = build_progress(labs, scores)

    assert bloc.average_pct == 75
    assert bloc.complete is False


def test_bloc_label_falls_back_to_the_number_when_unnamed() -> None:
    named, unnamed = build_progress(
        [_lab("a", bloc=1, bloc_name="Fondamentaux"), _lab("b", bloc=2)],
        {},
    )

    assert named.label == "Fondamentaux"
    assert unnamed.label == "2"


def test_a_lab_with_a_zero_scale_does_not_crash_the_average() -> None:
    (bloc,) = build_progress([_lab("a")], {"a": (0, 0)})

    assert bloc.average_pct == 0


# ── next_pending_lab ──────────────────────────────────────────────────────────

def test_next_follows_the_teaching_order_not_the_input_order() -> None:
    """Labs come before challenges, challenges before capstones."""
    labs = [
        _lab("capstone", lab_type="capstone"),
        _lab("challenge", lab_type="challenge"),
        _lab("second", bloc_order=2),
        _lab("first", bloc_order=1),
    ]

    upcoming = next_pending_lab(labs, {})

    assert upcoming is not None
    assert upcoming.id == "first"


def test_next_skips_what_is_already_scored() -> None:
    labs = [_lab("first", bloc_order=1), _lab("second", bloc_order=2)]

    upcoming = next_pending_lab(labs, {"first": (100, 100)})

    assert upcoming is not None
    assert upcoming.id == "second"


def test_next_returns_none_when_everything_is_done() -> None:
    labs = [_lab("a"), _lab("b")]
    scores = {"a": (100, 100), "b": (40, 100)}

    assert next_pending_lab(labs, scores) is None


def test_earlier_bloc_wins_over_lower_order() -> None:
    labs = [_lab("late", bloc=2, bloc_order=1), _lab("early", bloc=1, bloc_order=9)]

    upcoming = next_pending_lab(labs, {})

    assert upcoming is not None
    assert upcoming.id == "early"
