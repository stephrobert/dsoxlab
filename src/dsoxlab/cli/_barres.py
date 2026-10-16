"""Brancher une barre Rich sur un suivi d'événements, et rien d'autre.

Ce module portait, pour chaque outil piloté (ansible-runner, ``terraform
init``, ``terraform apply``), une fonction qui lisait les événements, tenait
l'état de la progression dans un ``dict`` capturé par fermeture, et appelait
Rich. Mesuré le 2026-10-16 : complexité cognitive de 54 et 77, profondeur
d'imbrication 7 et 8, couverture **19 %**, et une complexité cyclomatique de
**1** sur la pire des deux, qui la rendait invisible à ``ruff C901``.

La lecture des événements et l'état vivent désormais dans
``reporting/evenements.py``, qui se teste avec une liste et sans terminal. Il ne
reste ici que le câblage : une barre, un suivi, et :func:`_appliquer` qui
traduit un :class:`Avancement` en appels Rich.

Les trois fonctions gardent leur signature : ``provision``, ``destroy``, ``run``
et ``check`` les appellent, et ce n'était pas le moment de changer deux choses.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from pathlib import Path
from typing import TYPE_CHECKING, Any

from ..reporting import console
from ..reporting.evenements import (
    AVIS,
    CHANGE,
    DETAIL,
    ECHEC,
    IGNORE,
    OK,
    SuiviAnsible,
    SuiviTerraform,
    SuiviTerraformInit,
)
from ..runtimes.base import EventCallback

if TYPE_CHECKING:
    from rich.progress import Progress, TaskID

    from ..reporting.evenements import Avancement

logger = logging.getLogger(__name__)

#: Comment chaque marque s'écrit. C'est le SEUL endroit où une couleur est
#: décidée : les suivis rendent un sens (``ok``, ``echec``), jamais un style.
_STYLES = {
    OK: "  [green]✔[/green] {texte}",
    CHANGE: "  [yellow]●[/yellow] {texte}",
    IGNORE: "  [dim]⊘ {texte}[/dim]",
    ECHEC: "  [red]✘ {texte}[/red]",
    DETAIL: "    [red]{texte}[/red]",
    AVIS: "{texte}",
}


def _appliquer(progress: Progress, tache: TaskID, avancement: Avancement | None) -> None:
    """Reporte un avancement sur la barre, et écrit ses lignes au-dessus.

    Les lignes passent par ``progress.console`` et non par ``console`` :
    pendant qu'une barre est active, c'est le seul moyen d'écrire sans
    déchirer son rendu.
    """
    if avancement is None:
        return
    champs: dict[str, Any] = {}
    if avancement.total is not None:
        champs["total"] = avancement.total
    if avancement.fait is not None:
        champs["completed"] = avancement.fait
    if avancement.description is not None:
        champs["description"] = avancement.description
    if champs:
        progress.update(tache, **champs)
    for ligne in avancement.lignes:
        progress.console.print(_STYLES[ligne.marque].format(texte=ligne.texte))


def _barre_comptee() -> Any:
    """La barre des opérations dont on connaît le nombre d'étapes."""
    from rich.progress import (
        BarColumn,
        MofNCompleteColumn,
        Progress,
        SpinnerColumn,
        TextColumn,
        TimeElapsedColumn,
    )

    return Progress(
        SpinnerColumn(),
        TextColumn("[bold]{task.description}"),
        BarColumn(bar_width=30),
        MofNCompleteColumn(),
        TimeElapsedColumn(),
        transient=False,
        console=console,
    )


def _run_ansible_with_progress(
    playbook_path: Path, runner: Callable[[EventCallback], Any]
) -> None:
    """Joue un playbook en streamant ses événements vers une barre.

    ``runner`` prend un callback ``on_event`` et invoque ``run_lab`` ou son
    équivalent côté services.
    """
    suivi = SuiviAnsible(playbook=playbook_path.name)
    with _barre_comptee() as progress:
        tache = progress.add_task(f"Running {playbook_path.name}…", total=None)
        runner(lambda evenement: _appliquer(progress, tache, suivi(evenement)))
        _appliquer(progress, tache, suivi.fin())


def _run_terraform_init_with_spinner(runner: Callable[[EventCallback], Any]) -> None:
    """Lance ``terraform init`` avec un spinner : un téléchargement n'a pas de total."""
    from rich.progress import Progress, SpinnerColumn, TextColumn, TimeElapsedColumn

    suivi = SuiviTerraformInit()
    with Progress(
        SpinnerColumn(),
        TextColumn("[bold]{task.description}"),
        TimeElapsedColumn(),
        transient=True,
        console=console,
    ) as progress:
        tache = progress.add_task("Terraform init…", total=None)
        runner(lambda evenement: _appliquer(progress, tache, suivi(evenement)))
        _appliquer(progress, tache, suivi.fin())


def _run_terraform_with_progress(
    operation: str, runner: Callable[[EventCallback], Any]
) -> Any:
    """Joue un ``terraform apply``/``destroy`` et rend ce que ``runner`` rend."""
    suivi = SuiviTerraform(operation=operation)
    with _barre_comptee() as progress:
        tache = progress.add_task("Planning…", total=None)
        resultat = runner(lambda evenement: _appliquer(progress, tache, suivi(evenement)))
        _appliquer(progress, tache, suivi.fin())
    return resultat
