"""Rendu terminal avec Rich : tableaux, panneaux, statuts."""

from __future__ import annotations

from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.text import Text
from rich.tree import Tree

from pathlib import Path
from typing import Any

from ..models.lab import LabDefinition
from ..models.course import CourseManifest, CourseSection
from ..services.progress_service import build_progress
from ..validators.structure import StructureReport
from ..i18n import _

console = Console()
err_console = Console(stderr=True, style="bold red")
#: Avis de mise a jour : sur stderr comme les erreurs, pour ne jamais
#: polluer un document JSON, mais sans le rouge qui ferait croire a un echec.
update_console = Console(stderr=True, style="dim", highlight=False)


# ── Helpers ──────────────────────────────────────────────────────────────────

def _level_color(level: str) -> str:
    return {"l1": "green", "l2": "yellow", "lfcs": "cyan", "rhcsa": "magenta"}.get(level, "white")


def _difficulty_label(difficulty: str) -> str:
    """Traduit les difficultés courantes, laisse passer le reste.

    Le champ est libre par contrat : un dépôt de labs peut y mettre ce qu'il
    veut. On ne traduit donc que les trois valeurs employées partout, et toute
    autre valeur s'affiche telle quelle plutôt que de disparaître.
    """
    cle = f"difficulty_{difficulty.strip().lower()}"
    traduit = _(cle)
    return difficulty if traduit == cle else traduit


def _section_color(section: str) -> str:
    return {
        "linux": "bold green",
        "ansible": "bold red",
        "terraform": "bold purple4",
        "docker": "bold blue",
        "kubernetes": "bold cyan",
        "git": "bold orange3",
    }.get(section, "white")


def _type_badge(lab_type: str) -> str:
    """Short coloured badge for the lab type."""
    return {
        "lab":       "[bold green]lab[/bold green]",
        "challenge": "[bold yellow]challenge[/bold yellow]",
        "capstone":  "[bold red]capstone[/bold red]",
    }.get(lab_type, f"[dim]{lab_type}[/dim]")


# ── list-labs ─────────────────────────────────────────────────────────────────

def print_labs_table(labs: list[LabDefinition], scores: dict[str, tuple[int, int]] | None = None) -> None:
    if not labs:
        console.print(f"[yellow]{_('no_labs_found')}[/yellow]")
        return

    table = Table(title=_('table_labs_title'), show_lines=True)
    table.add_column(_('col_section'), style="bold", no_wrap=True)
    table.add_column(_('col_id'), style="bold cyan", no_wrap=True)
    table.add_column(_('col_title'))
    table.add_column(_('col_type'), justify="center")
    table.add_column(_('col_level'), justify="center")
    table.add_column(_('col_runtime'), justify="center")
    table.add_column(_('col_duration'), justify="center")
    table.add_column(_('col_score'), justify="center")

    current_section = ""
    for lab in labs:
        level_text = Text(lab.level, style=_level_color(lab.level))
        runtime_text = lab.runtime.type.value

        # Une seule section affichée par groupe : les lignes suivantes du
        # même groupe laissent la cellule vide.
        section_display = Text("", style="")
        if lab.section != current_section:
            current_section = lab.section
            section_display = Text(lab.section, style=_section_color(lab.section))

        if scores and lab.id in scores:
            best, max_s = scores[lab.id]
            pct = int(best * 100 / max_s) if max_s else 0
            color = "green" if pct == 100 else "yellow" if pct >= 50 else "red"
            score_cell = Text(f"{best}/{max_s}", style=color)
        else:
            score_cell = Text("—", style="dim")

        table.add_row(
            section_display,
            lab.id,
            lab.title,
            _type_badge(lab.lab_type),
            level_text,
            runtime_text,
            lab.estimated_time,
            score_cell,
        )

    console.print(table)


# ── show ──────────────────────────────────────────────────────────────────────

def print_lab_detail(lab: LabDefinition, status: str | None = None) -> None:
    lines = [
        f"{_('field_section')}    [{_section_color(lab.section)}]{lab.section}[/{_section_color(lab.section)}]",
        f"{_('field_title')}      {lab.title}",
        f"{_('field_type')}       {_type_badge(lab.lab_type)}"
        + (f"  —  bloc {lab.bloc}" if lab.bloc else ""),
        f"{_('field_level')}     [{_level_color(lab.level)}]{lab.level}[/{_level_color(lab.level)}]",
        f"{_('field_runtime')}    {lab.runtime.type.value} / {lab.runtime.topology}",
        f"{_('field_duration')}      {lab.estimated_time}",
        f"{_('field_difficulty')} {_difficulty_label(lab.difficulty)}",
        f"{_('field_distros')}    {', '.join(lab.distros)}",
        f"{_('field_skills')}     {', '.join(lab.skills)}",
        f"{_('field_doc')}        [link={lab.doc_url}]{lab.doc_url}[/link]",
    ]
    if lab.track:
        lines.append(f"{_('field_track')}   {', '.join(lab.track)}")
    if lab.certification_tags:
        lines.append(f"{_('field_certifs')}    {', '.join(lab.certification_tags)}")
    if status:
        lines.append(f"{_('field_status')}     {status}")

    val = lab.validation
    val_parts = []
    if val.functional:
        val_parts.append(f"[green]{_('val_functional')}[/green]")
    if val.security:
        val_parts.append(f"[yellow]{_('val_security')}[/yellow]")
    if val.persistence_after_reboot:
        val_parts.append(f"[cyan]{_('val_persistence')}[/cyan]")
    lines.append(f"{_('field_validation')} {', '.join(val_parts)}")

    console.print(Panel("\n".join(lines), title=f"[bold]{lab.id}[/bold]", expand=False))


# ── validate-structure ────────────────────────────────────────────────────────

def print_structure_reports(reports: list[StructureReport]) -> None:
    tree = Tree(_('tree_structure_title'))
    for report in reports:
        if report.ok:
            branch = tree.add(f"[green]✔[/green] {report.lab_id}")
        else:
            branch = tree.add(f"[red]✘[/red] {report.lab_id}")
            for issue in report.issues:
                branch.add(f"[red]{issue.message}[/red]")
    console.print(tree)


# ── doctor ────────────────────────────────────────────────────────────────────

def print_doctor(checks: list[tuple[str, bool, str, str | None]]) -> None:
    """checks : liste de (label, ok, détail, fix_cmd|None)."""
    table = Table(title=_('doctor_table_title'), show_header=True)
    table.add_column(_('col_component'))
    table.add_column(_('col_status'), justify="center")
    table.add_column(_('col_detail'))
    table.add_column(_('col_remediation'))

    has_failures = False
    for label, ok, detail, fix_cmd in checks:
        status = _('status_ok') if ok else _('status_ko')
        fix_cell = "" if ok or not fix_cmd else f"[dim]{fix_cmd}[/dim]"
        if not ok:
            has_failures = True
        table.add_row(label, status, detail, fix_cell)

    console.print(table)
    if has_failures:
        console.print(f"[yellow]{_('doctor_fix_hint')}[/yellow]")


# ── messages simples ──────────────────────────────────────────────────────────

def success(msg: str) -> None:
    console.print(f"[green]✔[/green] {msg}")


def info(msg: str) -> None:
    console.print(f"[cyan]ℹ[/cyan] {msg}")


def warn(msg: str) -> None:
    console.print(f"[yellow]⚠[/yellow] {msg}")


def error(msg: str) -> None:
    err_console.print(f"✘ {msg}")


# ── check result ──────────────────────────────────────────────────────────────

def print_check_result(
    lab_id: str,
    passed: int,
    total: int,
    max_score: int,
    score: int,
    hints_used: int,
    hints_cost: int,
) -> None:
    pct = f"{passed}/{total}" if total else "—"
    bar_filled = int((passed / total) * 20) if total else 0
    bar = "[green]" + "█" * bar_filled + "[/green]" + "[dim]" + "░" * (20 - bar_filled) + "[/dim]"

    lines = [
        f"{_('check_result_tests')}       {bar}  {pct}",
    ]
    if hints_used:
        lines.append(
            f"{_('check_result_hints_label')}       {_('check_result_hints_used', count=hints_used, cost=hints_cost)}"
        )
    else:
        lines.append(f"{_('check_result_hints_label')}       {_('check_result_no_hints')}")

    score_color = "green" if passed == total and total > 0 else "yellow" if passed > 0 else "red"
    lines.append(
        f"{_('check_result_score_label')}       [{score_color}]{score}[/{score_color}] / {max_score} pts"
    )

    console.print(
        Panel(
            "\n".join(lines),
            title=f"[bold]{_('check_result_title', lab_id=lab_id)}[/bold]",
            expand=False,
        )
    )


# ── hint ──────────────────────────────────────────────────────────────────────

def print_hint(index: int, total_hints: int, text: str, cost: int, remaining_cost: int) -> None:
    console.print(
        Panel(
            f"[bold yellow]{_('hint_label', index=index + 1, total=total_hints)}[/bold yellow]\n\n{text}\n\n"
            f"{_('hint_costs', cost=cost, total=remaining_cost)}",
            title=_('hint_panel_title'),
            expand=False,
        )
    )


# ── progress ──────────────────────────────────────────────────────────────────

def print_progress_table(
    labs: list[LabDefinition],
    scores: dict[str, tuple[int, int]],
) -> None:
    """Print a bloc-by-bloc progression summary.

    For each bloc that has at least one lab, shows:
    - number of labs validated / total labs in the bloc
    - average score (best attempts only)
    - whether the challenge is validated
    - whether the capstone is validated
    """
    if not labs:
        console.print(f"[yellow]{_('progress_no_labs')}[/yellow]")
        return

    table = Table(title=_("progress_table_title"), show_lines=True)
    table.add_column(_("col_bloc_num"), justify="left", style="bold")
    table.add_column(_("col_bloc_done"), justify="center")
    table.add_column(_("col_bloc_avg"), justify="center")
    table.add_column(_("col_challenge"), justify="center")
    table.add_column(_("col_capstone"), justify="center")

    def _status(validated: bool | None) -> str:
        if validated is None:
            return "—"
        return _("progress_validated") if validated else _("progress_pending")

    for bloc in build_progress(labs, scores):
        done_text = f"{bloc.validated}/{bloc.total}"
        if bloc.complete:
            done_text = f"[green]{done_text}[/green]"
        elif bloc.started:
            done_text = f"[yellow]{done_text}[/yellow]"
        else:
            done_text = f"[dim]{done_text}[/dim]"

        if bloc.average_pct is None:
            avg_text = _("progress_pending")
        else:
            avg = bloc.average_pct
            avg_color = "green" if avg >= 80 else "yellow" if avg >= 50 else "red"
            avg_text = f"[{avg_color}]{avg} %[/{avg_color}]"

        table.add_row(
            bloc.label or "?",
            done_text,
            avg_text,
            _status(bloc.challenge_validated),
            _status(bloc.capstone_validated),
        )

    console.print(table)


# ── scores ────────────────────────────────────────────────────────────────────

def print_scores_table(results: list[dict[str, Any]]) -> None:
    if not results:
        console.print(f"[yellow]{_('no_scores')}[/yellow]")
        return

    table = Table(title=_('scores_table_title'), show_lines=True)
    table.add_column(_('col_lab'), style="bold cyan", no_wrap=True)
    table.add_column(_('col_section'), justify="center")
    table.add_column(_('col_score'), justify="center")
    table.add_column(_('col_tests'), justify="center")
    table.add_column(_('col_hints'), justify="center")
    table.add_column(_('col_validated_at'))

    for r in results:
        score = r["score"]
        max_s = r["max_score"]
        pct = score / max_s if max_s else 0
        score_color = "green" if pct >= 1.0 else "yellow" if pct >= 0.5 else "red"
        score_text = Text(f"{score}/{max_s}", style=score_color)

        tests = f"{r['passed_tests']}/{r['total_tests']}"
        validated_at = r["validated_at"][:16].replace("T", " ")

        table.add_row(
            r["lab_id"],
            Text(r["section"], style=_section_color(r["section"])),
            score_text,
            tests,
            str(r["hints_used"]),
            validated_at,
        )

    console.print(table)


# ── fullhelp ──────────────────────────────────────────────────────────────────

def print_course_list(labs: list[LabDefinition]) -> None:
    """Display a table of all labs with course (scenario.md) availability."""
    table = Table(title=_("course_list_title"), show_lines=True)
    table.add_column(_("course_list_col_id"), style="bold cyan", no_wrap=True)
    table.add_column(_("course_list_col_title"))
    table.add_column(_("col_level"), justify="center")
    table.add_column(_("course_list_col_status"), justify="center")

    for lab in labs:
        has_course = (lab.path / "scenario.md").exists()
        status = Text("✔", style="green") if has_course else Text("✗", style="dim red")
        table.add_row(
            lab.id,
            lab.title,
            Text(lab.level, style=_level_color(lab.level)),
            status,
        )

    console.print(table)


def print_course_toc(lab: "LabDefinition", manifest: "CourseManifest") -> None:
    """Display the table of contents from a course.yaml."""
    table = Table(title=_("course_toc_title", title=manifest.title), show_lines=True)
    table.add_column(_("course_toc_col_n"), style="bold", justify="right", width=4)
    table.add_column(_("course_toc_col_id"), style="cyan", no_wrap=True)
    table.add_column(_("course_toc_col_title"))

    for i, section in enumerate(manifest.sections, 1):
        table.add_row(str(i), section.id, section.title)

    console.print(table)
    console.print(f"[dim]{_('course_toc_tip', id=lab.id)}[/dim]")


def print_course_section(
    lab: "LabDefinition",
    section: "CourseSection",
    *,
    pos: int = 0,
    total: int = 0,
) -> None:
    """Display a single course section from its markdown file."""
    from rich.markdown import Markdown
    from rich.rule import Rule

    section_file = lab.path / section.file
    console.print(Rule(f"[bold cyan]{section.id} — {section.title}[/bold cyan]"))
    if section_file.exists():
        text = section_file.read_text(encoding="utf-8")
        # Strip the leading H1 (already shown in the Rule above)
        lines = text.splitlines()
        if lines and lines[0].startswith("# "):
            # Skip the H1 and any immediately following blank line
            start = 1
            while start < len(lines) and lines[start].strip() == "":
                start += 1
            text = "\n".join(lines[start:])
        console.print(Markdown(text))
    else:
        msg = _("course_section_file_missing", file=section.file)
        console.print(f"[yellow]{msg}[/yellow]")
    console.print(Rule())

    # Navigation bar
    if pos > 0 and total > 0:
        progress = _("course_nav_progress", pos=pos, total=total)
        parts: list[str] = []
        if pos > 1:
            parts.append(_("course_nav_prev", id=lab.id))
        if pos < total:
            parts.append(_("course_nav_next", id=lab.id))
        console.print(f"[dim]{progress}[/dim]")
        if parts:
            console.print("[dim]" + "   |   ".join(parts) + "[/dim]")


def print_course_end(lab: "LabDefinition", manifest: "CourseManifest") -> None:
    """Display an end-of-course congratulation panel."""
    from rich.panel import Panel

    total = len(manifest.sections)
    body = _("course_end_body", total=total, id=lab.id)
    console.print(
        Panel(
            body,
            title=_("course_end_title", id=lab.id),
            border_style="green",
            padding=(1, 4),
        )
    )


def _localised(base: Path, nom: str, lang: str) -> Path | None:
    """``<nom>.<lang>.md`` s'il existe, sinon ``<nom>.md``, sinon rien."""
    if lang != "en":
        traduit = base / f"{nom}.{lang}.md"
        if traduit.is_file():
            return traduit
    defaut = base / f"{nom}.md"
    return defaut if defaut.is_file() else None


def print_lab_course(lab: LabDefinition, lang: str = "en") -> None:
    """Affiche le cours du lab : le contexte, puis la partie qui enseigne.

    Les deux fichiers sont complémentaires et étaient jusqu'ici traités comme
    des concurrents : ``scenario`` pose la situation en quelques lignes,
    ``README`` explique les commandes et déroule les exercices. Seul le premier
    était affiché, si bien que la partie la plus riche n'était atteignable par
    aucune commande (mesuré : 10 465 lignes de code dans les README d'un seul
    dépôt, exposées par rien). L'apprenant en concluait qu'il n'y avait pas de
    cours, et allait chercher la réponse dans l'énoncé du challenge.
    """
    from rich.markdown import Markdown
    from rich.rule import Rule

    console.print(Rule(f"[bold cyan]{lab.id}[/bold cyan]"))
    parties = [
        f for f in (_localised(lab.path, "scenario", lang),
                    _localised(lab.path, "README", lang))
        if f is not None
    ]
    if parties:
        for i, fichier in enumerate(parties):
            if i:
                console.print(Rule(style="dim"))
            console.print(Markdown(fichier.read_text(encoding="utf-8")))
    else:
        msg = _("course_missing")
        console.print(f"[yellow]{msg}[/yellow]")
    console.print(Rule())
    tip = _("course_tip", id=lab.id)
    console.print(f"[dim]{tip}[/dim]")


def print_lab_welcome(lab: LabDefinition) -> None:
    """Display the lab welcome panel explaining available commands."""
    from rich.panel import Panel

    title = _("lab_welcome_title")
    lines = []
    # Dire où l'on atterrit ET où travailler. Sans ces deux lignes, l'apprenant
    # arrive dans un shell à la racine du dépôt sans savoir quel répertoire le
    # concerne : le panneau listait des commandes, jamais un point de départ.
    if lab.runtime.session == "local":
        parts = lab.path.parts
        labdir = (
            "/".join(parts[parts.index("labs"):]) if "labs" in parts else lab.path.name
        )
        lines += [
            _("lab_welcome_session_local"),
            _("lab_welcome_labdir", labdir=labdir),
        ]
        # Un lab piloté depuis le poste peut malgré tout se jouer SUR une
        # machine (cas des labs système). On donne alors la commande de
        # connexion : la taper soi-même fait partie de l'apprentissage, mais
        # deviner le nom d'hôte, non.
        cible = lab.runtime.target()
        if cible is not None:
            lines.append(_("lab_welcome_local_ssh", host=cible.host))
        lines += ["", _("lab_welcome_start_here"), ""]
    elif lab.runtime.type.value in ("vm", "kvm", "incus"):
        # La session s'ouvre en SSH sur la VM, où dsoxlab n'est PAS installé.
        # Sans cet avertissement, le panneau annonce six commandes juste avant
        # de déposer l'apprenant là où aucune ne répond.
        tgt = lab.runtime.target()
        lines += [
            _("lab_welcome_session_target", host=tgt.host if tgt else "?"),
            _("lab_welcome_commands_here"),
            "",
        ]
    lines += [
        _("lab_welcome_course"),
        _("lab_welcome_challenge"),
        "",
        _("lab_welcome_check"),
        _("lab_welcome_submit"),
        "",
        _("lab_welcome_hint"),
        "",
        _("lab_welcome_exit"),
    ]
    console.print(Panel("\n".join(lines), title=f"[bold yellow]{title}[/bold yellow]", border_style="yellow"))


def print_lab_challenge(lab: LabDefinition, lang: str = "en") -> None:
    """Display the challenge brief (challenge/README.md or README.<lang>.md)."""
    from rich.markdown import Markdown
    from rich.rule import Rule

    localised = lab.path / "challenge" / f"README.{lang}.md"
    challenge_file = (
        localised
        if lang != "en" and localised.exists()
        else lab.path / "challenge" / "README.md"
    )
    console.print(Rule(f"[bold cyan]{lab.id} — challenge[/bold cyan]"))
    if challenge_file.exists():
        console.print(Markdown(challenge_file.read_text()))
    else:
        msg = _("challenge_missing")
        console.print(f"[yellow]{msg}[/yellow]")
    console.print(Rule())
    workdir = _("challenge_workdir", path=str(lab.path / "challenge"))
    console.print(f"[dim]{workdir}[/dim]")


# ── fullhelp ──────────────────────────────────────────────────────────────────

def print_fullhelp() -> None:
    """Affiche le guide complet de la plateforme."""
    from rich.panel import Panel
    from rich.rule import Rule

    sections = [
        ("fullhelp_concept",  None),
        ("fullhelp_workflow", None),
        ("fullhelp_commands", None),
        ("fullhelp_runtimes", None),
        ("fullhelp_language", None),
        ("fullhelp_scoring",  None),
        ("fullhelp_update",   None),
    ]

    console.print()
    console.print(Panel(
        f"[bold cyan]{_('fullhelp_title')}[/bold cyan]",
        expand=False,
        border_style="bright_blue",
    ))
    console.print()

    for key, _unused in sections:
        console.print(_( key))
        console.print()
        console.print(Rule(style="dim"))
        console.print()
