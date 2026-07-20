"""Smoke tests for the dsoxlab CLI.

These tests do not require any lab repository: they exercise the entry point,
the version flag and the i18n catalogs in isolation.
"""

from __future__ import annotations

from typer.testing import CliRunner

from dsoxlab import __version__
from dsoxlab.cli import app
from dsoxlab.i18n.strings import en, fr

runner = CliRunner()


def test_version_flag_prints_version() -> None:
    result = runner.invoke(app, ["--version"])
    assert result.exit_code == 0
    assert __version__ in result.stdout


def test_help_lists_core_commands() -> None:
    result = runner.invoke(app, ["--help"])
    assert result.exit_code == 0
    for command in ("list-labs", "run", "check", "doctor"):
        assert command in result.stdout


def test_i18n_catalogs_share_the_same_keys() -> None:
    assert set(en.STRINGS) == set(fr.STRINGS)


def test_guide_is_listed_in_help() -> None:
    result = runner.invoke(app, ["--help"])
    assert result.exit_code == 0
    assert "guide" in result.stdout


def test_guide_help_mentions_the_print_option() -> None:
    result = runner.invoke(app, ["guide", "--help"])
    assert result.exit_code == 0
    assert "--print" in result.stdout


def test_fullhelp_documents_guide_in_both_languages() -> None:
    """fullhelp must never omit a command that exists."""
    for catalog in (en, fr):
        assert "guide" in catalog.STRINGS["fullhelp_commands"]
