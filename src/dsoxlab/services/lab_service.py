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
from ..models.hint import HintFile
from ..models.lab import LabDefinition
from ..runtimes.base import EventCallback, SessionSpec
from ..runtimes.manager import RuntimeManager
from ..sessions.store import hints_cost_total, hints_used_count, record_result
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


@dataclass(frozen=True)
class ScoreResult:
    """Un lab validé et noté : ce que les tests ont donné, et ce que ça vaut.

    ``hints_cost`` est ce que les indices demandés ont retiré du barème, et
    ``max_score`` reste le barème PLEIN du lab (pas le barème amputé) : on veut
    pouvoir afficher « 70/100, dont 20 de pénalité d'indices » plutôt qu'un
    « 70/80 » qui masquerait le coût des indices.
    """

    check: CheckResult
    score: int
    max_score: int
    hints_used: int
    hints_cost: int


def _parse_counts(output: str) -> tuple[int, int]:
    """Extrait (passed, total) depuis la sortie de pytest.

    On lit la ligne de RÉSUMÉ que pytest produit lui-même ("3 failed, 1 passed
    in 0.02s") : c'est la seule source fiable.

    Compter les occurrences de " PASSED"/" FAILED"/" ERROR" dans la sortie
    brute — ce que faisait cette fonction — est faux dès qu'un lab manipule ces
    mots : les messages d'assertion les affichent. Un lab qui filtre des lignes
    « ERROR » (l1-get-help, l1-grep-regex, l1-redirections-pipes…) gonflait son
    total, et le score de l'apprenant s'en trouvait FAUSSÉ : 1/5 au lieu de
    1/4. Bug vécu, trouvé en jouant les labs.
    """
    # La dernière ligne qui porte un compte est le résumé final : les lignes
    # de verdict par test ("… PASSED [ 25%]") n'ont pas ce format.
    resumes = [
        ligne
        for ligne in output.splitlines()
        if re.search(r"\b\d+ (passed|failed|error|skipped)", ligne)
    ]
    resume = resumes[-1] if resumes else ""

    def _compte(mot: str) -> int:
        m = re.search(rf"(\d+) {mot}", resume)
        return int(m.group(1)) if m else 0

    passed = _compte("passed")
    total = passed + _compte("failed") + _compte("error") + _compte("skipped")

    if total == 0:
        # Aucun résumé exploitable (pytest a planté avant) : on retombe sur le
        # comptage des verdicts, ancré sur le format "<nodeid> VERDICT" pour ne
        # pas ramasser les mots présents dans les messages.
        verdicts = re.findall(r"::\S+\s+(PASSED|FAILED|ERROR)\b", output)
        passed = verdicts.count("PASSED")
        total = len(verdicts)
    return passed, total


def compute_score(passed: int, total: int, max_score: int, hints_cost: int) -> int:
    """Note un lab : proportion de tests réussis, appliquée au barème amputé des indices.

    Le coût des indices est retiré du barème AVANT la règle de trois, et non du
    score final : demander de l'aide plafonne ce qu'on peut obtenir, plutôt que
    de pénaliser après coup quelqu'un qui a tout réussi. Le barème ne descend
    jamais sous zéro, donc un apprenant qui a consommé tous les indices obtient
    0, jamais un score négatif.

    ``total`` à zéro (pytest n'a pas pu collecter) rend 0 : on ne devine pas un
    score depuis une exécution qui n'a rien mesuré.
    """
    if total <= 0:
        return 0
    base = max(0, max_score - hints_cost)
    return round((passed / total) * base)


def evaluate_lab(root: Path, lab: LabDefinition, result: CheckResult) -> ScoreResult:
    """Note un ``CheckResult`` et l'enregistre dans l'historique de l'apprenant.

    Cette fonction était le cœur de ``_run_check`` dans ``cli.py``, où elle
    était entrelacée avec des ``typer.Exit`` et des appels d'affichage : toute
    autre interface (TUI, export) aurait dû redupliquer la formule de score.
    Elle n'imprime rien et ne traduit rien ; l'appelant présente le résultat.
    """
    hint_file = HintFile.load(lab.path / "challenge")
    max_score = hint_file.points
    hints_cost = hints_cost_total(root, lab.id)
    used = hints_used_count(root, lab.id)
    score = compute_score(result.passed, result.total, max_score, hints_cost)

    record_result(
        root,
        lab_id=lab.id,
        section=lab.section,
        score=score,
        max_score=max_score,
        passed_tests=result.passed,
        total_tests=result.total,
        hints_used=used,
    )
    return ScoreResult(
        check=result,
        score=score,
        max_score=max_score,
        hints_used=used,
        hints_cost=hints_cost,
    )


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


def lab_session_spec(lab: LabDefinition) -> SessionSpec | None:
    """Décrit la session interactive du lab sans l'ouvrir.

    Permet d'afficher la commande à taper plutôt que de l'exécuter, et laisse
    une interface qui ne peut pas céder son TTY choisir son mode d'attachement.
    """
    runtime = _manager.get(lab)
    return runtime.session_spec(lab)


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
    target: str | None = None,
    on_event: Callable[[dict[str, Any]], None] | None = None,
) -> CheckResult:
    """Lance les tests pytest du lab et retourne un CheckResult détaillé.

    ``target`` sélectionne la target du lab (``runtime.targets[].name``) sur
    laquelle les tests doivent porter. Son FQDN est exporté aux tests via
    ``DSOXLAB_TARGET_HOST`` : c'est ce qui permet à un lab multi-distrib
    d'être réellement validé sur la distrib choisie, au lieu que les tests
    codent un hôte en dur. Si ``target`` est None, la target ``default`` du
    lab est utilisée.

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

    # Expose aux tests le FQDN de la target choisie. Sans ça, un lab
    # multi-distrib ne peut que coder son hôte en dur : la target Ubuntu
    # serait déclarée mais jamais testée — le contrat mentirait.
    resolved = lab.runtime.target(target)
    if target and resolved is None:
        declared = ", ".join(t.name for t in lab.runtime.targets) or "aucune"
        return CheckResult(
            ok=False,
            output=(
                f"Target '{target}' inconnue pour le lab {lab.id}.\n"
                f"Targets déclarées : {declared}."
            ),
            passed=0, total=0,
        )
    if resolved is not None and resolved.host:
        env["DSOXLAB_TARGET_HOST"] = resolved.host

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
