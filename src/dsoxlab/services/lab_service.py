"""Orchestration métier : actions sur les labs."""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import sys
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ..discovery.repo import find_meta_yml
from ..discovery.scanner import discover_labs
from ..models.lab import LabDefinition
from ..runtimes.base import EventCallback
from ..runtimes.manager import RuntimeManager
from ..utils.shell import CommandError, run_command
from ..validators.metadata import MetadataReport, validate_metadata
from ..validators.structure import StructureReport, validate_structure

_manager = RuntimeManager()


@dataclass
class CheckResult:
    ok: bool
    output: str
    passed: int
    total: int


def _parse_counts(output: str) -> tuple[int, int]:
    """Extrait (passed, total) depuis la sortie verbose de pytest."""
    passed = len(re.findall(r" PASSED", output))
    failed = len(re.findall(r" FAILED", output))
    errors = len(re.findall(r" ERROR", output))
    total = passed + failed + errors
    if total == 0:
        # Fallback sur la ligne récapitulative : "3 passed, 2 failed in 0.03s"
        m_p = re.search(r"(\d+) passed", output)
        m_f = re.search(r"(\d+) failed", output)
        passed = int(m_p.group(1)) if m_p else 0
        failed = int(m_f.group(1)) if m_f else 0
        total = passed + failed
    return passed, total


def get_all_labs(root: Path, lang: str = "en") -> list[LabDefinition]:
    return discover_labs(root, lang=lang)


def get_lab(root: Path, lab_id: str, lang: str = "en") -> LabDefinition:
    labs = discover_labs(root, lang=lang)
    for lab in labs:
        if lab.id == lab_id:
            return lab
    raise ValueError(f"Lab introuvable : {lab_id}")


def run_lab(
    lab: LabDefinition,
    target_name: str | None = None,
    *,
    on_event: EventCallback | None = None,
) -> None:
    """Prépare et démarre l'environnement du lab (setup uniquement)."""
    runtime = _manager.get(lab)
    runtime.start(lab, target_name, on_event=on_event)


def open_lab_session(lab: LabDefinition) -> None:
    """Ouvre une session interactive dans le répertoire du lab (bloquant pour shell)."""
    runtime = _manager.get(lab)
    runtime.open_session(lab)


def stop_lab(lab: LabDefinition, target_name: str | None = None) -> None:
    runtime = _manager.get(lab)
    runtime.stop(lab, target_name)


def reset_lab(
    lab: LabDefinition,
    target_name: str | None = None,
    *,
    on_event: EventCallback | None = None,
) -> None:
    """Remet le lab à l'état initial (clean + start)."""
    runtime = _manager.get(lab)
    runtime.reset(lab, target_name, on_event=on_event)


def clean_lab(
    lab: LabDefinition,
    target_name: str | None = None,
    *,
    on_event: EventCallback | None = None,
) -> None:
    """Supprime toutes les ressources créées par le lab."""
    runtime = _manager.get(lab)
    runtime.clean(lab, target_name, on_event=on_event)


def lab_status(lab: LabDefinition, target_name: str | None = None) -> str:
    runtime = _manager.get(lab)
    return runtime.status(lab, target_name)


def _resolve_pytest_cmd(repo_root: Path) -> list[str] | None:
    """Trouve la bonne façon de lancer pytest avec testinfra disponible.

    Ordre de résolution :

    1. ``sys.executable -m pytest`` (l'env du tool dsoxlab — pytest +
       pytest-testinfra sont déclarés en dependencies de dsoxlab donc
       installés par ``uv tool install dsoxlab``). C'est le mode
       cible : l'apprenant n'a rien à installer localement, dsoxlab
       embarque tout. Le subprocess hérite du PYTHONPATH du tool dsoxlab
       et peut importer ``dsoxlab.*`` depuis le conftest.py du repo de labs.
    2. ``<repo_root>/.venv/bin/pytest`` (fallback venv local).
    3. ``uv run pytest`` dans le repo (uv crée/sync à la volée).
    4. ``pytest`` système.

    Retourne ``None`` si vraiment aucun pytest disponible (rare —
    nécessite que dsoxlab ait été mal installé).
    """
    # Test rapide : dsoxlab tool a bien pytest dans son env ?
    try:
        import pytest as _pytest_check  # noqa: F401
        return [sys.executable, "-m", "pytest"]
    except ImportError:
        pass  # dsoxlab installé sans pytest (cas rare, fallback ci-dessous)

    venv_pytest = repo_root / ".venv" / "bin" / "pytest"
    if venv_pytest.is_file():
        return [str(venv_pytest)]

    uv_path = shutil.which("uv")
    if uv_path:
        return [uv_path, "run", "--quiet", "pytest"]

    pytest_path = shutil.which("pytest")
    if pytest_path:
        return [pytest_path]

    return None


_PYTEST_VERDICT_RE = re.compile(
    r"^(?P<nodeid>\S+::\S+)\s+(?P<verdict>PASSED|FAILED|ERROR|SKIPPED|XFAIL|XPASS)"
)


def _collect_test_count(
    pytest_cmd: list[str],
    tests_dir: Path,
    repo_root: Path,
    env: dict[str, str],
) -> int:
    """Compte les tests via ``pytest --collect-only -q``.

    Retourne 0 si la collecte échoue (pytest streame quand même les
    verdicts, donc on peut afficher une barre indéterminée).
    """
    try:
        result = run_command(
            [*pytest_cmd, "--collect-only", "-q", str(tests_dir)],
            cwd=repo_root,
            timeout=60,
            check=False,
            env=env,
        )
    except CommandError:
        return 0
    if not result.ok:
        return 0
    # Format pytest -q : une ligne par test, puis ligne vide, puis "N tests collected".
    m = re.search(r"(\d+)\s+tests?\s+collected", result.stdout)
    if m:
        return int(m.group(1))
    # Fallback : compter les lignes nodeid (contenant "::").
    return sum(1 for line in result.stdout.splitlines() if "::" in line)


def check_lab(
    lab: LabDefinition,
    *,
    on_event: Callable[[dict[str, Any]], None] | None = None,
) -> CheckResult:
    """Lance les tests pytest du lab et retourne un CheckResult détaillé.

    Si ``on_event`` est fourni, les évènements suivants sont émis pour
    afficher une progress bar côté CLI :

    - ``{"type": "collected", "total": int}`` une fois après collecte.
    - ``{"type": "verdict", "nodeid": str, "verdict": "PASSED"|"FAILED"|...}``
      pour chaque test terminé.
    - ``{"type": "log", "line": str}`` pour les autres lignes (header,
      tracebacks, summary). Le caller décide de les afficher ou non.
    """
    tests_dir = lab.path / "challenge" / "tests"
    if not tests_dir.is_dir():
        return CheckResult(
            ok=False,
            output="Répertoire challenge/tests/ introuvable",
            passed=0, total=0,
        )

    meta_path = find_meta_yml(lab.path)
    repo_root = meta_path.parent if meta_path else lab.path.parent
    pytest_cmd = _resolve_pytest_cmd(repo_root)
    if pytest_cmd is None:
        return CheckResult(
            ok=False,
            output=(
                "pytest introuvable. Réinstalle dsoxlab :\n"
                "  uv tool install --force dsoxlab\n"
                "(pytest+pytest-testinfra sont embarqués dans le tool)."
            ),
            passed=0, total=0,
        )

    # Désactive la fixture _apply_lab_state (rejouerait solution.yaml
    # côté formateur, écrasant le travail manuel de l'apprenant).
    env = os.environ.copy()
    env.setdefault("LAB_NO_REPLAY", "1")

    if on_event is None:
        # Mode legacy : capture en bloc, pas de streaming.
        try:
            result = run_command(
                [*pytest_cmd, "-v", str(tests_dir)],
                cwd=repo_root,
                timeout=300,
                check=False,
                env=env,
            )
            output = result.stdout + result.stderr
            passed, total = _parse_counts(output)
            return CheckResult(ok=result.ok, output=output, passed=passed, total=total)
        except CommandError as exc:
            return CheckResult(ok=False, output=str(exc), passed=0, total=0)

    # Mode streaming : pré-collecte pour le total, puis Popen ligne par ligne.
    total_collected = _collect_test_count(pytest_cmd, tests_dir, repo_root, env)
    on_event({"type": "collected", "total": total_collected})

    output_lines: list[str] = []
    try:
        proc = subprocess.Popen(
            [*pytest_cmd, "-v", "--no-header", "--tb=short", str(tests_dir)],
            cwd=repo_root,
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
        )
    except FileNotFoundError as exc:
        return CheckResult(ok=False, output=str(exc), passed=0, total=0)

    assert proc.stdout is not None
    for line in proc.stdout:
        line = line.rstrip("\n")
        output_lines.append(line)
        m = _PYTEST_VERDICT_RE.match(line)
        if m:
            on_event({
                "type": "verdict",
                "nodeid": m.group("nodeid"),
                "verdict": m.group("verdict"),
            })
        else:
            on_event({"type": "log", "line": line})

    rc = proc.wait(timeout=300)
    output = "\n".join(output_lines)
    passed, total = _parse_counts(output)
    return CheckResult(ok=(rc == 0), output=output, passed=passed, total=total)


def validate_all_structure(root: Path) -> list[StructureReport]:
    labs = discover_labs(root)
    return [validate_structure(lab) for lab in labs]


def validate_all_metadata(root: Path) -> list[MetadataReport]:
    labs = discover_labs(root)
    return [validate_metadata(lab) for lab in labs]
