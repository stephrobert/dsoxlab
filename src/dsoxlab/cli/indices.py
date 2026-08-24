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
from typing import Annotated

import typer

from ..config import (
    read_context,
)
from ..i18n import _
from ..models.hint import HintFile
from ..reporting import (
    error,
    info,
    print_hint,
)
from ..sessions.store import (
    hints_cost_total,
    next_hint_index,
    record_hint,
)
from ._commun import (
    LabHomeOption,
    _complete_lab_id,
    _lab,
    _lang,
    _root,
)
from ._socle import app

logger = logging.getLogger(__name__)



@app.command("hint", help=_("cmd_hint_help"))
def hint(
    lab_id: Annotated[str | None, typer.Argument(help=_("cmd_hint_arg"), autocompletion=_complete_lab_id)] = None,
    lab_home: LabHomeOption = None,
) -> None:
    root = _root(lab_home)
    lang = _lang(root)
    ctx = read_context(root)
    effective_id = lab_id or ctx.active_lab
    if not effective_id:
        error(_("no_active_lab"))
        raise typer.Exit(1)
    try:
        lab = _lab(root, effective_id, lang)
    except ValueError as exc:
        error(str(exc))
        raise typer.Exit(1) from None

    hint_file = HintFile.load(lab.path / "challenge")
    if not hint_file.hints:
        info(_("no_hints"))
        return

    idx = next_hint_index(root, effective_id)
    if idx >= len(hint_file.hints):
        info(_("all_hints_used", count=len(hint_file.hints), total=len(hint_file.hints)))
        return

    current = hint_file.hints[idx]
    record_hint(root, effective_id, idx, current.cost)
    total_cost = hints_cost_total(root, effective_id)
    print_hint(
        idx, len(hint_file.hints),
        current.text(_lang(root)),
        current.cost, total_cost,
    )


# ── check helpers ─────────────────────────────────────────────────────────────









# ── check ─────────────────────────────────────────────────────────────────────
