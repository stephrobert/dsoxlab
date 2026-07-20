"""Smoke tests for the dsoxlab CLI.

These tests do not require any lab repository: they exercise the entry point,
the version flag and the i18n catalogs in isolation.
"""

from __future__ import annotations

import re
from typing import Any

import typer.main
from typer.testing import CliRunner

from dsoxlab import __version__
from dsoxlab.cli import app
from dsoxlab.i18n.strings import en, fr

runner = CliRunner()

_ANSI = re.compile(r"\x1b\[[0-9;]*m")


def _plain(output: str) -> str:
    """Terminal output with Rich's escape sequences stripped.

    Rich styles fragments of a token, so a literal substring can be absent from
    coloured output while being perfectly visible on screen: `0.1.16` is emitted
    as `ESC[1;36m0.1ESC[0m.ESC[1;36m16ESC[0m`. Whether colour is enabled depends
    on the environment, so asserting on raw output passes locally and fails in
    CI. Strip the styling and assert on what the user actually reads.
    """
    return _ANSI.sub("", output)


def test_version_flag_prints_version() -> None:
    result = runner.invoke(app, ["--version"])
    assert result.exit_code == 0
    assert __version__ in _plain(result.stdout)


def test_help_lists_core_commands() -> None:
    result = runner.invoke(app, ["--help"])
    assert result.exit_code == 0
    for command in ("list-labs", "run", "check", "doctor"):
        assert command in _plain(result.stdout)


def test_i18n_catalogs_share_the_same_keys() -> None:
    assert set(en.STRINGS) == set(fr.STRINGS)


def _params(command: str) -> dict[str | None, Any]:
    """Parameters the parser really registered for a command, keyed by name.

    This asserts the *contract* rather than the `--help` output. Rich styles the
    help text, and under colour it splits a flag across escape sequences
    (`--print` comes out as `ESC[1;36m-ESC[0mESC[1;36m-printESC[0m`), so a literal
    substring search passes locally and fails in CI; terminal width truncates it
    too. Nor can we lean on click's class hierarchy: `TyperGroup` does not
    subclass `click.Group` in every version. The parser's own data is the only
    stable thing here.
    """
    group = typer.main.get_command(app)
    return {param.name: param for param in group.commands[command].params}


def test_guide_command_is_registered() -> None:
    group = typer.main.get_command(app)

    assert "guide" in group.commands


def test_guide_declares_a_print_option() -> None:
    flags = {flag for param in _params("guide").values() for flag in param.opts}

    assert "--print" in flags


def test_guide_takes_an_optional_lab_id() -> None:
    """`dsoxlab guide` with no argument must fall back to the active lab."""
    assert _params("guide")["lab_id"].required is False


def test_fullhelp_documents_guide_in_both_languages() -> None:
    """fullhelp must never omit a command that exists."""
    for catalog in (en, fr):
        assert "guide" in catalog.STRINGS["fullhelp_commands"]
