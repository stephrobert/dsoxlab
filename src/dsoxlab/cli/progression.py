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
import os
from typing import Annotated

import typer

from ..config import (
    read_context,
    set_active_lab,
)
from ..i18n import _
from ..interrupt import (
    Interrupted,
)
from ..reporting import (
    console,
    error,
    info,
    machine,
    print_progress_table,
    print_scores_table,
    success,
)
from ..services import (
    clean_lab,
    next_pending_lab,
    reset_lab,
)
from ..sessions.store import (
    get_best_scores,
    get_results,
    reset_hints,
)
from ._barres import (
    _run_ansible_with_progress,
)
from ._commun import (
    LabHomeOption,
    _catalogue,
    _complete_lab_id,
    _interrompu,
    _lab,
    _lang,
    _resolve_lab,
    _root,
    _stop_services,
    _verrou,
)
from ._socle import app
from ._validation import _run_check

logger = logging.getLogger(__name__)



# ── check ─────────────────────────────────────────────────────────────────────

@app.command("check", help=_("cmd_check_help"))
def check(
    lab_id: Annotated[str | None, typer.Argument(help=_("cmd_check_arg"), autocompletion=_complete_lab_id)] = None,
    target: Annotated[str | None, typer.Option("--target", "-t",
        help=_("opt_check_target"))] = None,
    as_json: Annotated[bool, typer.Option("--json", help=_("opt_json"))] = False,
    lab_home: LabHomeOption = None,
) -> None:
    root = _root(lab_home)
    lab = _resolve_lab(root, lab_id, _lang(root))
    try:
        result, score, max_score = _run_check(root, lab, target, quiet=as_json)
    except Interrupted as exc:
        _interrompu(exc, f"dsoxlab check {lab.id}")
    if as_json:
        # La sortie brute de pytest est conservée : c'est là que l'appelant
        # trouve le détail des échecs, qu'aucun compteur ne résume.
        machine.emit({
            "lab": machine.lab_dict(lab),
            "check": {
                "ok": result.ok,
                "passed": result.passed,
                "total": result.total,
                "score": score,
                "max_score": max_score,
                "output": result.output,
            },
        })
        if not result.ok:
            raise typer.Exit(1)
        return
    if result.ok:
        success(_("all_tests_passed"))
        info(_("check_tip_submit"))
    else:
        error(_("tests_failed"))
        raise typer.Exit(1)


# ── submit ────────────────────────────────────────────────────────────────────

# ── submit ────────────────────────────────────────────────────────────────────

@app.command("submit", help=_("cmd_submit_help"))
def submit(
    lab_id: Annotated[str | None, typer.Argument(help=_("cmd_submit_arg"), autocompletion=_complete_lab_id)] = None,
    target: Annotated[str | None, typer.Option("--target", "-t",
        help=_("opt_check_target"))] = None,
    lab_home: LabHomeOption = None,
) -> None:
    root = _root(lab_home)
    lab = _resolve_lab(root, lab_id, _lang(root))
    try:
        result, score, max_score = _run_check(root, lab, target)
    except Interrupted as exc:
        _interrompu(exc, f"dsoxlab submit {lab.id}")

    if result.ok:
        success(_("submit_success", score=score, max_score=max_score))
    else:
        info(_("submit_partial", passed=result.passed, total=result.total, score=score, max_score=max_score))

    # Un lab qui déclare un seuil est un examen blanc, et un examen rend un
    # verdict. Sans lui, un apprenant qui rendait 40/100 sur un mock RHCSA ne
    # lisait nulle part qu'il avait échoué : la note s'affichait, jamais son
    # sens. Un lab ordinaire n'en déclare pas et n'affiche donc rien.
    from ..services.progress_service import exam_percentage, exam_verdict

    verdict = exam_verdict(score, max_score, lab.exam_passing_score)
    if verdict is not None:
        cle = "exam_passed" if verdict else "exam_failed"
        rendu = success if verdict else error
        rendu(_(
            cle,
            pct=exam_percentage(score, max_score),
            threshold=lab.exam_passing_score,
        ))

    set_active_lab(root, None)
    console.print()
    # CTA "tape exit" uniquement si on est dans le sous-shell ouvert
    # par ``dsoxlab run`` (cas runtime shell). Sur runtime vm,
    # l'apprenant est revenu sur son poste local — pas de sous-shell
    # à fermer, donc le message serait trompeur.
    if os.environ.get("DSOXLAB_LAB_SESSION"):
        console.print(_("submit_exit_cta"))
    else:
        console.print(_("submit_done"))


# ── scores ────────────────────────────────────────────────────────────────────

# ── scores ────────────────────────────────────────────────────────────────────

@app.command("scores", help=_("cmd_scores_help"))
def scores(
    lab_home: LabHomeOption = None,
    section: Annotated[str | None, typer.Option("--section", "-s", help=_("opt_section"))] = None,
    lab_id: Annotated[str | None, typer.Option("--lab", "-l", help=_("opt_filter_lab"))] = None,
    top: Annotated[int, typer.Option("--top", help=_("opt_top"))] = 20,
    as_json: Annotated[bool, typer.Option("--json", help=_("opt_json"))] = False,
) -> None:
    root = _root(lab_home)
    ctx = read_context(root)
    effective_section = section or ctx.section
    results = get_results(root, lab_id=lab_id, section=effective_section, limit=top)
    # Les seuils vivent dans le catalogue, les notes dans la base : le verdict
    # d'un examen demande les deux. On ne balaie que pour les labs affichés.
    affiches = {r["lab_id"] for r in results}
    seuils = {
        lab.id: lab.exam_passing_score
        for lab in _catalogue(root, _lang(root), quiet=as_json)
        if lab.exam_passing_score and lab.id in affiches
    }
    if as_json:
        machine.emit({
            "results": [machine.score_dict(r, seuils.get(r["lab_id"])) for r in results],
            "count": len(results),
        })
        return
    print_scores_table(results, seuils)


# ── progress ──────────────────────────────────────────────────────────────────

# ── progress ──────────────────────────────────────────────────────────────────

@app.command("progress", help=_("cmd_progress_help"))
def progress(
    lab_home: LabHomeOption = None,
    section: Annotated[str | None, typer.Option("--section", "-s", help=_("opt_section"))] = None,
    level: Annotated[str | None, typer.Option("--level", "-l", help=_("opt_level"))] = None,
    as_json: Annotated[bool, typer.Option("--json", help=_("opt_json"))] = False,
) -> None:
    root = _root(lab_home)
    ctx = read_context(root)
    lang = _lang(root)

    effective_section = section or ctx.section
    effective_level = level or ctx.level

    labs = _catalogue(root, lang, quiet=as_json)
    if effective_section:
        labs = [lab for lab in labs if lab.section == effective_section]
    if effective_level:
        labs = [lab for lab in labs if lab.level == effective_level]

    # Sort by bloc then bloc_order for a coherent display
    labs = sorted(labs, key=lambda lab: (lab.bloc, lab.bloc_order, lab.id))

    lab_ids = [lab.id for lab in labs]
    scores_data = get_best_scores(root, lab_ids)
    if as_json:
        faits = [i for i in lab_ids if i in scores_data]
        machine.emit({
            "labs": [machine.lab_dict(lab, scores_data.get(lab.id)) for lab in labs],
            "summary": {
                "total": len(labs),
                "attempted": len(faits),
                "points": sum(scores_data[i][0] for i in faits),
                "max_points": sum(scores_data[i][1] for i in faits),
            },
        })
        return
    print_progress_table(labs, scores_data)


# ── next ──────────────────────────────────────────────────────────────────────

# ── next ──────────────────────────────────────────────────────────────────────

@app.command("next", help=_("cmd_next_help"))
def next_lab(
    lab_home: LabHomeOption = None,
    as_json: Annotated[bool, typer.Option("--json", help=_("opt_json"))] = False,
) -> None:
    root = _root(lab_home)
    ctx = read_context(root)
    lang = _lang(root)

    # Erreur dure, en `--json` comme ailleurs : sans contexte il n'y a rien à
    # décrire. La cause part sur stderr, la sortie standard reste vide, et le
    # code de retour ne change pas.
    if not ctx.section:
        error(_("next_no_context"))
        raise typer.Exit(1)

    labs = _catalogue(root, lang, quiet=as_json)
    if ctx.section:
        labs = [lab for lab in labs if lab.section == ctx.section]
    if ctx.level:
        labs = [lab for lab in labs if lab.level == ctx.level]

    scores_data = get_best_scores(root, [lab.id for lab in labs])

    upcoming = next_pending_lab(labs, scores_data)
    if as_json:
        # `next` et `all_done` disent deux choses différentes : un contexte
        # sans lab du tout rendrait aussi `next: null`, et l'appelant fêterait
        # une section terminée qui est en fait vide.
        machine.emit({
            "context": {"section": ctx.section, "level": ctx.level or None},
            "next": None if upcoming is None
            else machine.lab_dict(upcoming, scores_data.get(upcoming.id)),
            "all_done": upcoming is None and bool(labs),
            "remaining": sum(1 for lab in labs if lab.id not in scores_data),
        })
        return
    if upcoming is None:
        success(_("next_all_done"))
        return
    success(_("next_suggestion", lab_id=upcoming.id, title=upcoming.title))


# ── reset ─────────────────────────────────────────────────────────────────────

# ── reset ─────────────────────────────────────────────────────────────────────

@app.command("reset", help=_("cmd_reset_help"))
def reset(
    ctx: typer.Context,
    lab_id: Annotated[str, typer.Argument(help=_("cmd_reset_arg"), autocompletion=_complete_lab_id)],
    target: Annotated[str | None, typer.Option("--target", "-t",
        help=_("opt_run_target"))] = None,
    lab_home: LabHomeOption = None,
) -> None:
    root = _root(lab_home)
    lang = _lang(root)
    try:
        lab = _lab(root, lab_id, lang)
    except ValueError as exc:
        error(str(exc))
        raise typer.Exit(1) from None

    ctx.call_on_close(_verrou(root, "reset").release)
    info(_("resetting", lab_id=lab.id))
    try:
        if lab.runtime.type.value in ("vm", "kvm", "incus"):
            _run_ansible_with_progress(
                lab.path / "cleanup.yaml",
                lambda cb: reset_lab(lab, target_name=target, on_event=cb),
            )
        else:
            reset_lab(lab, target_name=target)
        reset_hints(root, lab.id)
        success(_("lab_reset"))
    except Interrupted as exc:
        _interrompu(exc, f"dsoxlab reset {lab.id}")
    except RuntimeError as exc:
        error(str(exc))
        raise typer.Exit(2) from None


# ── clean ─────────────────────────────────────────────────────────────────────

# ── clean ─────────────────────────────────────────────────────────────────────

@app.command("clean", help=_("cmd_clean_help"))
def clean(
    ctx: typer.Context,
    lab_id: Annotated[str, typer.Argument(help=_("cmd_clean_arg"), autocompletion=_complete_lab_id)],
    target: Annotated[str | None, typer.Option("--target", "-t",
        help=_("opt_run_target"))] = None,
    lab_home: LabHomeOption = None,
    yes: Annotated[bool, typer.Option("--yes", "-y", help=_("opt_yes"))] = False,
) -> None:
    root = _root(lab_home)
    lang = _lang(root)
    try:
        lab = _lab(root, lab_id, lang)
    except ValueError as exc:
        error(str(exc))
        raise typer.Exit(1) from None

    if not yes:
        typer.confirm(_("confirm_clean", lab_id=lab.id), abort=True)

    # Après la confirmation, jamais avant : tenir le verrou pendant qu'on
    # attend une réponse au clavier bloquerait l'autre terminal sur une
    # question que personne ne voit.
    ctx.call_on_close(_verrou(root, "clean").release)
    info(_("cleaning", lab_id=lab.id))
    try:
        if lab.runtime.type.value in ("vm", "kvm", "incus"):
            _run_ansible_with_progress(
                lab.path / "cleanup.yaml",
                lambda cb: clean_lab(lab, target_name=target, on_event=cb),
            )
        else:
            clean_lab(lab, target_name=target)
        _stop_services(lab, root)
        success(_("clean_done"))
    except Interrupted as exc:
        _interrompu(exc, f"dsoxlab clean {lab.id}")
    except RuntimeError as exc:
        error(str(exc))
        raise typer.Exit(2) from None


# ── validate-structure ────────────────────────────────────────────────────────
