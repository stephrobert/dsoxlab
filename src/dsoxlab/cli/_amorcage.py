"""L'amorçage de la CLI : ce qui se joue avant et après toute commande.

Trois moments encadrent chaque invocation, et rien d'autre ne vit ici :

- ``_version_callback`` répond à ``--version`` avant tout le reste ;
- ``_bootstrap``, le callback global de l'app, initialise le journal et la
  langue UI avant que la sous-commande ne s'exécute ;
- ``_notify_update_available``, posé par ``atexit``, parle en tout dernier,
  sur stderr, et jamais au détriment de la commande qui vient de tourner.
"""

from __future__ import annotations

import atexit
import sys
from typing import Annotated

import typer

from .. import __version__
from ..config import get_lab_home
from ..i18n import _, set_lang
from ..logging_setup import configurer as configurer_journal
from ..reporting import console, update_console
from ._commun import _lang
from ._socle import app


def _version_callback(value: bool) -> None:
    """Affiche la version puis quitte (option ``--version`` eager)."""
    if value:
        console.print(f"dsoxlab {__version__}")
        raise typer.Exit()


@app.callback(invoke_without_command=True)
def _bootstrap(
    ctx: typer.Context,
    version: Annotated[
        bool,
        typer.Option(
            "--version",
            help=_("opt_version_help"),
            callback=_version_callback,
            is_eager=True,
        ),
    ] = False,
    verbose: Annotated[
        int,
        typer.Option("--verbose", "-v", count=True, help=_("opt_verbose")),
    ] = 0,
    debug: Annotated[
        bool,
        typer.Option("--debug", help=_("opt_debug")),
    ] = False,
) -> None:
    """Initialise la langue UI et la journalisation avant toute commande."""
    # Avant le retour anticipé : `dsoxlab -v` sans sous-commande doit tout de
    # même écrire son journal, et c'est aussi ce qui garantit qu'une commande
    # qui échoue très tôt laisse une trace.
    configurer_journal(verbose, debug=debug)

    if ctx.invoked_subcommand is None:
        return
    try:
        root = get_lab_home()
        lang = _lang(root)
        set_lang(lang)
    # Aveugle et silencieux, volontairement : choisir la langue est un préalable
    # à TOUTES les commandes. Sans contexte de lab, on continue en langue par
    # défaut ; échouer ici empêcherait jusqu'à `dsoxlab --help`.
    except Exception:  # noqa: S110, BLE001
        pass  # silencieux si LAB_HOME introuvable

    # L'avis de mise à jour est posé ici, mais affiché à la toute fin par
    # atexit : c'est le seul moyen qu'il soit le dernier message, y compris
    # quand la commande sort en erreur ou lève typer.Exit.
    atexit.register(_notify_update_available)


def _notify_update_available() -> None:
    """Affiche l'avis de mise à jour, en dernier, sur stderr.

    Sur stderr et pas stdout : une commande en `--json` doit rendre un
    document lisible par un programme, quoi qu'il arrive. Et seulement si
    stderr est un terminal, pour ne pas polluer les journaux d'une CI ni la
    sortie capturée par un script.
    """
    if not sys.stderr.isatty():
        return
    try:
        from ..services.update_check import available_update

        latest = available_update(__version__)
        if latest is None:
            return
        update_console.print(
            _("update_available", latest=latest, current=__version__)
        )
    # Aveugle, et c'est le but : un avis de mise à jour ne casse jamais la
    # commande que l'utilisateur a lancée, quelle que soit la panne réseau,
    # de parsing ou d'affichage rencontrée.
    except Exception:  # noqa: BLE001
        return
