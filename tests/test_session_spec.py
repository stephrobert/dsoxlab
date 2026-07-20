"""Tests for SessionSpec: describing an interactive session without opening it.

`open_session` calls `subprocess.call`, which seizes the current TTY. That made
two things impossible: showing the learner the command instead of running it,
and letting an interface that cannot yield its terminal decide how to attach.
Runtimes now describe the session; only the base class executes it.
"""

from __future__ import annotations

import os
from pathlib import Path

from dsoxlab.models.lab import LabDefinition, ValidationConfig
from dsoxlab.models.runtime import RuntimeConfig, RuntimeType
from dsoxlab.runtimes.base import SessionSpec
from dsoxlab.runtimes.shell import ShellRuntime


def _shell_lab(tmp_path: Path) -> LabDefinition:
    return LabDefinition(
        id="demo-lab",
        title="Demo",
        level="l1",
        skills=["s"],
        runtime=RuntimeConfig(type=RuntimeType.SHELL, workdir="challenge/work"),
        distros=["alma10"],
        doc_url="https://example.test/doc",
        validation=ValidationConfig(),
        path=tmp_path,
    )


def test_display_quotes_what_needs_quoting() -> None:
    """The rendered command must be safe to copy, paste and type."""
    spec = SessionSpec(command=["ssh", "-o", "ProxyCommand=ssh -W %h:%p jump", "user@host"])

    assert spec.display() == "ssh -o 'ProxyCommand=ssh -W %h:%p jump' user@host"


def test_shell_session_targets_the_lab_workdir(tmp_path: Path) -> None:
    spec = ShellRuntime().session_spec(_shell_lab(tmp_path))

    assert spec.cwd == (tmp_path / "challenge" / "work").resolve()
    assert spec.command == [os.environ.get("SHELL", "bash")]


def test_shell_session_marks_the_subshell(tmp_path: Path) -> None:
    """`dsoxlab submit` reads this to know it runs inside a session subshell."""
    spec = ShellRuntime().session_spec(_shell_lab(tmp_path))

    assert spec.env == {"DSOXLAB_LAB_SESSION": "demo-lab"}


def test_env_holds_only_additions_never_a_full_environment(tmp_path: Path) -> None:
    """A subshell stripped of PATH would be useless: env must be an overlay."""
    spec = ShellRuntime().session_spec(_shell_lab(tmp_path))

    assert "PATH" not in spec.env


def test_describing_a_session_does_not_create_the_workdir(tmp_path: Path) -> None:
    """Describing must have no side effect; only opening may create things."""
    ShellRuntime().session_spec(_shell_lab(tmp_path))

    assert not (tmp_path / "challenge" / "work").exists()
