"""Point d'entrée CLI — dsoxlab.

Usage:
    dsoxlab use linux/l1
    dsoxlab list-labs
    dsoxlab show <id>
    dsoxlab run <id>
    dsoxlab check <id>
    dsoxlab reset <id>
    dsoxlab clean <id>
    dsoxlab validate-structure
    dsoxlab doctor
    dsoxlab quit

Convention de ce module : un ``except`` qui a déjà rendu la cause en une phrase
traduite (``error(...)``) sort par ``raise typer.Exit(n) from None``. Le ``from
None`` n'est pas un raccourci, c'est l'affirmation que la cause a été dite à
l'utilisateur, et qu'un chaînage d'exceptions n'ajouterait qu'une trace Python
au-dessus d'un message déjà écrit pour lui. Partout ailleurs, on chaîne.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from pathlib import Path
from typing import Any

from ..i18n import _
from ..interrupt import (
    EVENT_INTERRUPT,
)
from ..reporting import (
    console,
)
from ..runtimes.base import EventCallback

logger = logging.getLogger(__name__)



def _run_ansible_with_progress(
    playbook_path: Path, runner: Callable[[EventCallback], Any]
) -> None:
    """Exécute un playbook Ansible en streamant les events vers Rich.

    ``runner`` est une lambda qui prend un callback ``on_event`` et
    invoque ``run_lab(lab, on_event=cb)`` ou équivalent
    (``clean_lab``/``reset_lab`` côté services).

    Events ansible-runner consommés :
    - ``playbook_on_task_start`` : MàJ description avec nom de la tâche
    - ``runner_on_ok`` / ``runner_on_failed`` / ``runner_on_unreachable``
      / ``runner_on_skipped`` : ✔/✘/⊘ par tâche-host
    - ``playbook_on_stats`` : récap final (silencieux, le caller utilise
      les stats côté PlaybookResult).
    """
    from rich.progress import (
        BarColumn,
        MofNCompleteColumn,
        Progress,
        SpinnerColumn,
        TextColumn,
        TimeElapsedColumn,
    )

    state: dict[str, Any] = {"done": 0, "current_task": "", "playbook": playbook_path.name}

    with Progress(
        SpinnerColumn(),
        TextColumn("[bold]{task.description}"),
        BarColumn(bar_width=30),
        MofNCompleteColumn(),
        TimeElapsedColumn(),
        transient=False,
        console=console,
    ) as progress:
        task = progress.add_task(f"Running {playbook_path.name}…", total=None)

        def on_event(event: dict[str, Any]) -> None:
            etype = event.get("event")
            data = event.get("event_data", {}) or {}

            if etype == EVENT_INTERRUPT:
                progress.console.print(_(
                    "interrupt_notice_first" if event.get("count", 1) == 1
                    else "interrupt_notice_second"
                ))
            elif etype == "playbook_on_task_start":
                task_name = data.get("name") or data.get("task", "")
                state["current_task"] = task_name
                progress.update(task, description=_("progress_ansible_task", task=task_name))
            elif etype == "runner_on_ok":
                host = data.get("host", "?")
                task_name = data.get("task", state["current_task"])
                changed = data.get("res", {}).get("changed", False)
                state["done"] += 1
                progress.update(task, completed=state["done"])
                marker = "[yellow]●[/yellow]" if changed else "[green]✔[/green]"
                tag = "changed" if changed else "ok"
                progress.console.print(
                    f"  {marker} {host}: {task_name} [dim]({tag})[/dim]"
                )
            elif etype == "runner_on_skipped":
                host = data.get("host", "?")
                task_name = data.get("task", state["current_task"])
                state["done"] += 1
                progress.update(task, completed=state["done"])
                progress.console.print(
                    f"  [dim]⊘[/dim] {host}: {task_name} [dim](skipped)[/dim]"
                )
            elif etype == "runner_on_failed":
                host = data.get("host", "?")
                task_name = data.get("task", state["current_task"])
                msg = data.get("res", {}).get("msg", "")
                progress.console.print(
                    f"  [red]✘ {host}: {task_name}[/red]"
                )
                if msg:
                    progress.console.print(f"    [red]{msg}[/red]")
            elif etype == "runner_on_unreachable":
                host = data.get("host", "?")
                msg = data.get("res", {}).get("msg", "host unreachable")
                progress.console.print(
                    f"  [red]✘ {host}: UNREACHABLE — {msg}[/red]"
                )

        runner(on_event)
        progress.update(
            task,
            description=_("progress_playbook_done", playbook=playbook_path.name),
        )


def _run_terraform_init_with_spinner(runner: Callable[[EventCallback], Any]) -> None:
    """Lance terraform init avec un spinner (téléchargement provider).

    ``runner`` reçoit un callback ``on_event`` et invoque
    ``tf.init(repo_meta, on_event=cb)``.
    """
    from rich.progress import Progress, SpinnerColumn, TextColumn, TimeElapsedColumn

    with Progress(
        SpinnerColumn(),
        TextColumn("[bold]{task.description}"),
        TimeElapsedColumn(),
        transient=True,
        console=console,
    ) as progress:
        task = progress.add_task("Terraform init…", total=None)

        def on_event(event: dict[str, Any]) -> None:
            etype = event.get("type")
            # Quelques events du mode init -json
            if etype == "log" or etype == "diagnostic":
                level = event.get("@level", "info")
                msg = event.get("@message", "")
                if level == "error":
                    progress.console.print(f"  [red]{msg}[/red]")
                elif "Installing" in msg or "Finding" in msg or "Reusing" in msg:
                    progress.update(task, description=msg.strip())

        runner(on_event)
        progress.update(task, description=_("progress_tf_init_done"))


def _run_terraform_with_progress(
    operation: str, runner: Callable[[EventCallback], Any]
) -> Any:
    """Exécute un terraform apply/destroy en streamant via Rich Progress.

    ``runner`` est une lambda qui prend un callback ``on_event`` et
    invoque ``tf.apply`` ou ``tf.destroy``. Retourne ce que ``runner``
    retourne (ProvisionResult pour apply, None pour destroy).

    La progress bar :
    - liste les ressources à créer/détruire (via planned_change)
    - avance à chaque apply_complete
    - imprime ✔/✘ par ressource avec durée
    - capture les diagnostics d'erreur pour le message final
    """
    from rich.progress import (
        BarColumn,
        MofNCompleteColumn,
        Progress,
        SpinnerColumn,
        TextColumn,
        TimeElapsedColumn,
    )

    # ``in_flight`` : ressources avec apply_start mais pas encore
    # apply_complete (utile pour afficher ce qui prend du temps)
    state: dict[str, Any] = {
        "total": 0,
        "done": 0,
        "result": None,
        "in_flight": {},  # addr → elapsed_seconds (depuis apply_progress)
    }

    label_action = "Creating" if operation == "provision" else "Destroying"
    counted_action = "create" if operation == "provision" else "delete"

    def _short_addr(addr: str) -> str:
        """outscale_security_group_rule.bastion_ssh_in → bastion_ssh_in."""
        return addr.split(".", 1)[-1] if "." in addr else addr

    def _refresh_description() -> str:
        """Description = liste des in-flight (avec elapsed s'il y en a)."""
        if not state["in_flight"]:
            return f"{label_action}…"
        items = sorted(state["in_flight"].items(), key=lambda kv: -kv[1])
        # Affiche jusqu'à 2 ressources pour ne pas surcharger
        head = items[:2]
        rest = len(items) - len(head)
        parts = [f"{_short_addr(a)} ({s}s)" for a, s in head]
        suffix = f" +{rest}" if rest > 0 else ""
        return f"{label_action} {', '.join(parts)}{suffix}"

    with Progress(
        SpinnerColumn(),
        TextColumn("[bold]{task.description}"),
        BarColumn(bar_width=30),
        MofNCompleteColumn(),
        TimeElapsedColumn(),
        transient=False,
        console=console,
    ) as progress:
        task = progress.add_task("Planning…", total=None)

        def on_event(event: dict[str, Any]) -> None:
            etype = event.get("type")
            if etype == "planned_change":
                action = event.get("change", {}).get("action")
                if action == counted_action:
                    state["total"] += 1
                    progress.update(task, total=state["total"])
            elif etype == "apply_start":
                hook = event.get("hook", {})
                addr = hook.get("resource", {}).get("addr", "?")
                state["in_flight"][addr] = 0
                progress.update(task, description=_refresh_description())
            elif etype == "apply_progress":
                # Émis périodiquement par Terraform pour les ressources
                # qui prennent du temps (elapsed_seconds croissant).
                hook = event.get("hook", {})
                addr = hook.get("resource", {}).get("addr", "?")
                elapsed = int(hook.get("elapsed_seconds", 0))
                if addr in state["in_flight"]:
                    state["in_flight"][addr] = elapsed
                    progress.update(task, description=_refresh_description())
            elif etype == "apply_complete":
                hook = event.get("hook", {})
                addr = hook.get("resource", {}).get("addr", "?")
                elapsed = hook.get("elapsed_seconds", 0)
                state["in_flight"].pop(addr, None)
                state["done"] += 1
                progress.update(
                    task,
                    completed=state["done"],
                    description=_refresh_description(),
                )
                progress.console.print(
                    f"  [green]✔[/green] {_short_addr(addr)} [dim]({elapsed:.0f}s)[/dim]"
                )
            elif etype == "apply_errored":
                hook = event.get("hook", {})
                addr = hook.get("resource", {}).get("addr", "?")
                state["in_flight"].pop(addr, None)
                progress.update(task, description=_refresh_description())
                progress.console.print(f"  [red]✘ {_short_addr(addr)}[/red]")
            elif etype == "diagnostic":
                if event.get("@level") == "error":
                    diag = event.get("diagnostic", {})
                    summary = diag.get("summary", "")
                    progress.console.print(f"  [red]Error:[/red] {summary}")
            elif etype == EVENT_INTERRUPT:
                progress.console.print(_(
                    "interrupt_notice_first" if event.get("count", 1) == 1
                    else "interrupt_notice_second"
                ))

        state["result"] = runner(on_event)
        # Une fois terminé, fixe la barre à 100 % avec un label final
        if state["total"] > 0:
            progress.update(
                task,
                description=_("progress_action_done", action=label_action),
                completed=state["total"],
            )
        else:
            progress.update(
                task,
                description=_("progress_nothing_to_do"),
                total=1,
                completed=1,
            )

    return state["result"]
