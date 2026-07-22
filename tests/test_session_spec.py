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


def _vm_lab(tmp_path: Path, session: str) -> LabDefinition:
    """Un lab VM dont la session est déclarée `target` ou `local`."""
    from dsoxlab.models.runtime import Target

    return LabDefinition(
        id="demo-vm",
        title="Demo VM",
        level="l1",
        skills=["s"],
        runtime=RuntimeConfig(
            type=RuntimeType.VM,
            targets=[Target(name="t", host="node1.lab")],
            session=session,
        ),
        distros=["alma9"],
        doc_url="https://example.test/doc",
        validation=ValidationConfig(),
        path=tmp_path / "labs" / "demo",
    )


def test_vm_session_local_stays_on_the_workstation(tmp_path: Path, monkeypatch) -> None:
    """`session: local` ouvre un sous-shell ici, jamais un SSH.

    Sans ce mode, un lab piloté depuis le poste déposait l'apprenant sur un
    hôte dépourvu du dépôt et de ses outils : la session s'ouvrait, mais il n'y
    avait rien à y faire.
    """
    from dsoxlab.runtimes.vm import VmRuntime

    repo = tmp_path
    (repo / "labs" / "demo").mkdir(parents=True)
    runtime = VmRuntime()
    monkeypatch.setattr(
        runtime, "_repo_meta", lambda lab: type("M", (), {"path": repo})()
    )

    spec = runtime.session_spec(_vm_lab(tmp_path, "local"))

    assert spec.command == [os.environ.get("SHELL", "bash")]
    assert spec.cwd == repo, "la session doit s'ouvrir à la racine du dépôt"
    assert spec.env == {"DSOXLAB_LAB_SESSION": "demo-vm"}
    assert "ssh" not in spec.command


def test_vm_session_defaults_to_the_target() -> None:
    """Le défaut reste la session SSH : les labs système ne bougent pas."""
    assert RuntimeConfig(type=RuntimeType.VM).session == "target"


def _welcome(lab: LabDefinition) -> str:
    """Le panneau d'accueil, rendu en texte brut."""
    import importlib
    import io

    from rich.console import Console

    # `dsoxlab.reporting` réexporte un objet nommé `console`, qui masque le
    # sous-module du même nom : un import direct rendrait la Console, pas le
    # module dont on veut remplacer la sortie.
    reporting = importlib.import_module("dsoxlab.reporting.console")

    buf = io.StringIO()
    ancien = reporting.console
    reporting.console = Console(file=buf, width=100, no_color=True)
    try:
        reporting.print_lab_welcome(lab)
    finally:
        reporting.console = ancien
    return " ".join(buf.getvalue().split())


def test_welcome_warns_that_dsoxlab_is_absent_from_the_lab_host(tmp_path: Path) -> None:
    """Le panneau listait six commandes juste avant d'ouvrir une session SSH.

    `dsoxlab` n'est installé sur aucune VM : sans cet avertissement, l'apprenant
    les tape sur l'hôte et récolte des « command not found ».
    """
    texte = _welcome(_vm_lab(tmp_path, "target"))

    assert "node1.lab" in texte, "le panneau doit nommer l'hôte de destination"
    assert "exit" in texte


def test_welcome_points_to_the_lab_directory_when_local(tmp_path: Path) -> None:
    """En session locale, l'apprenant doit savoir où travailler."""
    texte = _welcome(_vm_lab(tmp_path, "local"))

    assert "labs/demo" in texte, "le panneau doit situer le répertoire du lab"
    assert "challenge" in texte, "et amorcer par la lecture de la mission"
