"""Tests for the pager that long terminal output goes through.

`dsoxlab course` prints a whole README when the lab declares no
`course.yaml`: several hundred lines in the existing catalogs. On a plain
local terminal, with no SSH client and no tmux, the beginning of the course
scrolls out of reach and is simply lost.

The rules pinned here are the ones that keep that fix from becoming a new
problem: never page a pipe, never page what already fits, and never lose
what was rendered.
"""

from __future__ import annotations

import importlib
from pathlib import Path

import pytest

from dsoxlab.reporting.console import _page, _pager_command, console, paged

#: Le module, pas l'objet : `dsoxlab.reporting` réexporte `console`, la
#: Console Rich, qui masque le sous-module du même nom sur l'accès par
#: attribut. `import dsoxlab.reporting.console as x` rendrait donc la Console.
console_module = importlib.import_module("dsoxlab.reporting.console")


# ── choosing the pager ────────────────────────────────────────────────────────

def test_defaults_to_less_with_raw_control_chars(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Without `-R`, Rich's colours land as raw escape sequences.

    A course displayed that way is worse than an unpaged one.
    """
    monkeypatch.delenv("DSOXLAB_PAGER", raising=False)
    monkeypatch.delenv("PAGER", raising=False)
    assert _pager_command() == ["less", "-R"]


def test_pager_env_is_honoured(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("DSOXLAB_PAGER", raising=False)
    monkeypatch.setenv("PAGER", "more")
    assert _pager_command() == ["more"]


def test_dsoxlab_pager_wins_over_pager(monkeypatch: pytest.MonkeyPatch) -> None:
    """So a learner can tune course reading without touching their system pager."""
    monkeypatch.setenv("PAGER", "more")
    monkeypatch.setenv("DSOXLAB_PAGER", "bat --plain")
    assert _pager_command() == ["bat", "--plain"]


def test_raw_flag_is_not_duplicated_when_already_asked_for(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("DSOXLAB_PAGER", "less -R -S")
    assert _pager_command() == ["less", "-R", "-S"]


def test_less_from_an_absolute_path_still_gets_the_flag(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("DSOXLAB_PAGER", "/usr/bin/less")
    assert _pager_command() == ["/usr/bin/less", "-R"]


# ── deciding whether to page at all ───────────────────────────────────────────

@pytest.fixture
def pager_spy(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Path:
    """A pager that records what it received, and a 10-line screen."""
    received = tmp_path / "received.txt"
    monkeypatch.setenv("DSOXLAB_PAGER", f"tee {received}")
    monkeypatch.setenv("LINES", "10")
    monkeypatch.setenv("COLUMNS", "80")
    return received


def test_short_output_is_printed_straight_through(
    pager_spy: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Opening a pager over three lines would be its own annoyance."""
    _page("one\ntwo\nthree\n")

    assert not pager_spy.exists()
    assert capsys.readouterr().out == "one\ntwo\nthree\n"


def test_output_taller_than_the_screen_reaches_the_pager(
    pager_spy: Path
) -> None:
    text = "".join(f"line {i}\n" for i in range(50))
    _page(text)

    assert pager_spy.read_text() == text


def test_pipes_are_never_paged(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Redirections and pipes must keep receiving plain, complete text.

    pytest captures stdout, so the console is not a terminal here: this is
    the same condition as `dsoxlab course > cours.txt`.
    """
    assert not console.is_terminal
    with paged():
        console.print("hello")

    assert "hello" in capsys.readouterr().out


def test_no_pager_flag_bypasses_capture(capsys: pytest.CaptureFixture[str]) -> None:
    with paged(enabled=False):
        console.print("hello")

    assert "hello" in capsys.readouterr().out


def test_rendered_output_survives_an_exception(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """A failure after printing must not swallow what was already rendered.

    Without this, an error raised at the end of a section would discard the
    whole section along with it.
    """
    monkeypatch.setattr(type(console), "is_terminal", property(lambda self: True))
    monkeypatch.setattr(console_module, "_page", lambda text: print(text, end=""))

    with pytest.raises(RuntimeError), paged():
        console.print("printed before the failure")
        raise RuntimeError("boom")

    assert "printed before the failure" in capsys.readouterr().out
