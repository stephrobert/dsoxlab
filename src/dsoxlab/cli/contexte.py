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
    clear_context,
    read_context,
    set_active_provider,
    write_context,
)
from ..i18n import _
from ..reporting import (
    error,
    info,
    machine,
    print_lab_detail,
    print_labs_table,
    success,
)
from ..services import (
    lab_status,
)
from ..sessions.store import (
    get_best_scores,
)
from ._commun import (
    LabHomeOption,
    _catalogue,
    _complete_lab_id,
    _lab,
    _lang,
    _root,
    _verrou,
)
from ._socle import app

logger = logging.getLogger(__name__)



# ── use ──────────────────────────────────────────────────────────────────────

@app.command("use", help=_("cmd_use_help"))
def use(
    ctx: typer.Context,
    context: Annotated[str | None, typer.Argument(help=_("cmd_use_arg"))] = None,
    lab_home: LabHomeOption = None,
    lang: Annotated[str | None, typer.Option("--lang", help=_("opt_lang"))] = None,
    target: Annotated[str | None, typer.Option("--target", "-t",
        help=_("opt_target"))] = None,
    provider: Annotated[str | None, typer.Option("--provider", "-p",
        help=_("opt_use_provider"))] = None,
    reset: Annotated[bool, typer.Option("--reset", "-r", help=_("opt_use_reset"))] = False,
) -> None:
    from ..services.contexte_service import (
        MetaIllisible,
        decouper,
        lire_declarations,
        refus_eventuel,
    )

    root = _root(lab_home)
    # `.dsoxlab-context.json` est réécrit EN ENTIER à chaque changement : deux
    # `use` concurrents, et le premier est perdu sans laisser de trace.
    ctx.call_on_close(_verrou(root, "use").release)

    # `--reset`, et `use` tout court : sans rien à poser, la commande efface.
    # Les deux chemins étaient écrits deux fois, à l'identique.
    if reset or (context is None and target is None and lang is None and provider is None):
        clear_context(root)
        success(_("context_cleared"))
        return

    try:
        declarations = lire_declarations(root)
    except MetaIllisible as exc:
        error(_("meta_read_failed", error=exc.cause))
        raise typer.Exit(1) from None

    refus = refus_eventuel(declarations, context=context, provider=provider)
    if refus is not None:
        error(_(refus.cle, **refus.params))
        raise typer.Exit(1)

    if provider is not None:
        set_active_provider(root, provider)
        success(_("context_provider_set", provider=provider))

    section: str | None = None
    level: str | None = None
    if context:
        section, level = decouper(context)
    if context or lang or target:
        write_context(root, section, level, lang=lang, active_target=target)
    if section:
        label = f"{section}/{level}" if level else section
        success(_("context_set", label=label))
        info(_("context_set_info"))
    if lang:
        info(_("context_lang_set", lang=lang[:2].lower()))
    if target:
        success(_("context_target_set", target=target))



# ── list-labs ─────────────────────────────────────────────────────────────────

# ── list-labs ─────────────────────────────────────────────────────────────────

@app.command("list-labs", help=_("cmd_list_labs_help"))
def list_labs(
    lab_home: LabHomeOption = None,
    level: Annotated[str | None, typer.Option("--level", "-l", help=_("opt_level"))] = None,
    section: Annotated[str | None, typer.Option("--section", "-s", help=_("opt_section"))] = None,
    lab_type: Annotated[str | None, typer.Option("--type", "-t", help=_("opt_type"))] = None,
    bloc: Annotated[int | None, typer.Option("--bloc", "-b", help=_("opt_bloc"))] = None,
    long: Annotated[bool, typer.Option("--long", help=_("opt_labs_long"))] = False,
    as_json: Annotated[bool, typer.Option("--json", help=_("opt_json"))] = False,
) -> None:
    root = _root(lab_home)
    ctx = read_context(root)

    effective_section = section or ctx.section
    effective_level = level or ctx.level

    # En mode machine, aucun message d'ambiance : la sortie doit être un
    # document JSON et rien d'autre.
    if (ctx.section or ctx.level) and not as_json:
        info(_("context_active", label=ctx.label()))

    lang = _lang(root)
    labs = _catalogue(root, lang, quiet=as_json)
    if effective_section:
        labs = [lab for lab in labs if lab.section == effective_section]
    if effective_level:
        labs = [lab for lab in labs if lab.level == effective_level]
    if lab_type:
        labs = [lab for lab in labs if lab.lab_type == lab_type]
    if bloc is not None:
        labs = [lab for lab in labs if lab.bloc == bloc]
    lab_ids = [lab.id for lab in labs]
    scores = get_best_scores(root, lab_ids)
    if as_json:
        machine.emit({
            "labs": [machine.lab_dict(lab, scores.get(lab.id)) for lab in labs],
            "count": len(labs),
        })
        return
    print_labs_table(labs, scores, tout=long)


# ── show ──────────────────────────────────────────────────────────────────────

# ── show ──────────────────────────────────────────────────────────────────────

@app.command("show", help=_("cmd_show_help"))
def show(
    lab_id: Annotated[str, typer.Argument(help=_("cmd_show_arg"), autocompletion=_complete_lab_id)],
    lab_home: LabHomeOption = None,
    as_json: Annotated[bool, typer.Option("--json", help=_("opt_json"))] = False,
) -> None:
    root = _root(lab_home)
    lang = _lang(root)
    try:
        lab = _lab(root, lab_id, lang)
    except ValueError as exc:
        error(str(exc))
        raise typer.Exit(1) from None

    # Le drapeau et non une comparaison de chaînes : `status` est un jeton
    # (`ready` / `stopped`) sauf dans ce cas-là, où c'est une phrase traduite.
    # Le mode machine doit distinguer les deux sans lire du français.
    indisponible = False
    try:
        status = lab_status(lab)
    except RuntimeError:
        status = _("runtime_unavailable")
        indisponible = True

    if as_json:
        # `best_score` doit dire la vérité : le laisser à `null` sur un lab
        # déjà noté se lirait « jamais tenté ».
        scores = get_best_scores(root, [lab.id])
        machine.emit({
            "lab": machine.lab_dict(lab, scores.get(lab.id)),
            "status": None if indisponible else status,
        })
        return

    print_lab_detail(lab, status=status)


# ── run ───────────────────────────────────────────────────────────────────────
