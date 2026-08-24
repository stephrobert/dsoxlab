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
import webbrowser
from pathlib import Path
from typing import Annotated

import typer

from ..config import (
    read_context,
    set_active_lab,
    set_course_pos,
)
from ..i18n import _
from ..infra.inventory import InfraNotProvisioned
from ..interrupt import (
    Interrupted,
)
from ..models import (
    CourseManifest,
    LabDefinition,
)
from ..reporting import (
    console,
    error,
    info,
    paged,
    print_course_end,
    print_course_section,
    print_course_toc,
    print_lab_challenge,
    print_lab_course,
    print_lab_welcome,
    success,
)
from ..services import (
    guide_url,
    open_lab_session,
    run_lab,
)
from ._barres import (
    _run_ansible_with_progress,
)
from ._commun import (
    LabHomeOption,
    NoPagerOption,
    _complete_lab_id,
    _ensure_services,
    _interrompu,
    _lab,
    _lang,
    _resolve_lab,
    _root,
    _verrou,
)
from ._socle import app

logger = logging.getLogger(__name__)



# ── run ───────────────────────────────────────────────────────────────────────

@app.command("run", help=_("cmd_run_help"))
def run(
    lab_id: Annotated[str, typer.Argument(help=_("cmd_run_arg"), autocompletion=_complete_lab_id)],
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

    info(_("lab_starting", lab_id=lab.id, runtime=lab.runtime.type.value))
    # Le verrou ne couvre QUE la phase qui écrit : services, playbook de setup,
    # contexte. Il est rendu avant la session interactive, sinon le `dsoxlab
    # check` que l'apprenant tape dans ce sous-shell serait refusé par sa
    # propre session, blocage que personne ne comprendrait.
    with _verrou(root, "run"):
        _ensure_services(lab, root)
        try:
            if lab.runtime.type.value in ("vm", "kvm", "incus"):
                _run_ansible_with_progress(
                    lab.path / "setup.yaml",
                    lambda cb: run_lab(lab, target_name=target, on_event=cb, root=root),
                )
            else:
                run_lab(lab, target_name=target, root=root)
        except Interrupted as exc:
            _interrompu(exc, f"dsoxlab run {lab.id}")
        except InfraNotProvisioned:
            # Avant le except RuntimeError : InfraNotProvisioned en hérite, et
            # mérite la phrase actionnable plutôt que son message technique.
            error(_("infra_not_provisioned"))
            raise typer.Exit(2) from None
        except RuntimeError as exc:
            error(str(exc))
            raise typer.Exit(2) from None

        set_active_lab(root, lab.id)
    # Dire où l'on atterrit vraiment. Le message historique annonçait
    # « challenge/work/ » quel que soit le runtime : faux pour tout lab vm,
    # qui ouvre une session SSH ou, désormais, un shell à la racine du dépôt.
    if lab.runtime.type.value in ("vm", "kvm", "incus"):
        if lab.runtime.session == "local":
            success(_("lab_ready_local", lab_id=lab.id))
        else:
            resolved = lab.runtime.target(target)
            success(_("lab_ready_target", lab_id=lab.id,
                      host=resolved.host if resolved else "?"))
    else:
        success(_("lab_ready", lab_id=lab.id, workdir=lab.runtime.workdir))
    # La session SSH s'ouvre sur un hôte dépourvu de dsoxlab : une fois dedans,
    # l'apprenant ne peut plus afficher sa mission. On la lui met sous les yeux
    # avant d'entrer, elle reste dans le défilement du terminal.
    if lab.runtime.type.value in ("vm", "kvm", "incus") and lab.runtime.session != "local":
        print_lab_challenge(lab, lang=lang)

    print_lab_welcome(lab)

    try:
        open_lab_session(lab)   # bloquant : sous-shell interactif
    except Interrupted as exc:
        _interrompu(exc, f"dsoxlab run {lab.id}")

    # Retour au shell parent : on garde active_lab posé pour que
    # ``dsoxlab check`` et ``dsoxlab submit`` (sans argument) sachent
    # quel lab valider. L'active_lab est libéré au submit (cf. cmd
    # submit) ou écrasé par un prochain ``dsoxlab run <autre_lab>``.
    # En session locale, on n'a jamais quitté son répertoire : annoncer un
    # « retour » n'aurait aucun sens. Ce qui compte alors, c'est que le travail
    # reste là et que check puisse être relancé.
    if lab.runtime.session == "local":
        success(_("lab_session_ended_local", lab_id=lab.id))
    else:
        success(_("lab_session_ended", lab_id=lab.id))




# ── course ───────────────────────────────────────────────────────────────────

# ── course ───────────────────────────────────────────────────────────────────

@app.command("course", help=_("cmd_course_help"))
def course(
    lab_id: Annotated[str | None, typer.Argument(help=_("cmd_course_arg"), autocompletion=_complete_lab_id)] = None,
    section: Annotated[str | None, typer.Option("--section", "-s", help=_("cmd_course_opt_section"))] = None,
    next_section: Annotated[bool, typer.Option("--next", "-n", help=_("cmd_course_opt_next"))] = False,
    prev_section: Annotated[bool, typer.Option("--prev", "-p", help=_("cmd_course_opt_prev"))] = False,
    no_pager: NoPagerOption = False,
    lab_home: LabHomeOption = None,
) -> None:
    root = _root(lab_home)
    lang = _lang(root)
    lab = _resolve_lab(root, lab_id, lang)


    manifest = CourseManifest.load(lab.path, lang=lang)

    if manifest is None:
        # Pas de course.yaml : fallback sur scenario.md + README.md, soit
        # plusieurs centaines de lignes d'un bloc. C'est le cas qui rend le
        # pager indispensable.
        with paged(enabled=not no_pager):
            print_lab_course(lab, lang=lang)
        return

    total = len(manifest.sections)
    ctx = read_context(root)
    current_pos = ctx.course_pos  # 0 = non démarré

    # ── Résolution de la position cible ──────────────────────────────────────
    if next_section:
        target_pos = (current_pos or 0) + 1
    elif prev_section:
        target_pos = max(1, (current_pos or 1) - 1)
    elif section is not None:
        found = manifest.resolve_section(section)
        if found is None:
            error(_("course_section_not_found", name=section, id=lab.id))
            raise typer.Exit(1)
        # Retrouver l'index 1-based de la section
        target_pos = next(
            (i + 1 for i, s in enumerate(manifest.sections) if s.id == found.id),
            1,
        )
    else:
        # Pas d'option : reprendre là où on en était, ou afficher section 1
        if current_pos and 1 <= current_pos <= total:
            target_pos = current_pos
        elif current_pos and current_pos > total:
            print_course_end(lab, manifest)
            return
        else:
            # Jamais commencé → sommaire + section 1, paginés ensemble : les
            # séparer ferait défiler le sommaire hors de l'écran.
            with paged(enabled=not no_pager):
                print_course_toc(lab, manifest)
                _show_course_section(root, lab, manifest, 1)
            return

    # ── Fin de cours ─────────────────────────────────────────────────────────
    if target_pos > total:
        set_course_pos(root, total)
        print_course_end(lab, manifest)
        return

    # ── Affichage de la section ───────────────────────────────────────────────
    with paged(enabled=not no_pager):
        _show_course_section(root, lab, manifest, target_pos)


def _show_course_section(
    root: Path, lab: LabDefinition, manifest: CourseManifest, pos: int
) -> None:
    """Mémorise la position atteinte puis affiche la section correspondante."""
    total = len(manifest.sections)
    set_course_pos(root, pos)
    print_course_section(lab, manifest.sections[pos - 1], pos=pos, total=total)


# ── challenge ─────────────────────────────────────────────────────────────────

# ── challenge ─────────────────────────────────────────────────────────────────

@app.command("challenge", help=_("cmd_challenge_help"))
def challenge_cmd(
    lab_id: Annotated[str | None, typer.Argument(help=_("cmd_challenge_arg"), autocompletion=_complete_lab_id)] = None,
    no_pager: NoPagerOption = False,
    lab_home: LabHomeOption = None,
) -> None:
    root = _root(lab_home)
    lab = _resolve_lab(root, lab_id, _lang(root))
    with paged(enabled=not no_pager):
        print_lab_challenge(lab, lang=_lang(root))


# ── hint ──────────────────────────────────────────────────────────────────────

# ── hint ──────────────────────────────────────────────────────────────────────

@app.command("guide", help=_("cmd_guide_help"))
def guide(
    lab_id: Annotated[str | None, typer.Argument(help=_("cmd_guide_arg"), autocompletion=_complete_lab_id)] = None,
    print_only: Annotated[bool, typer.Option("--print", help=_("cmd_guide_opt_print"))] = False,
    lab_home: LabHomeOption = None,
) -> None:
    """Ouvre le guide en ligne du lab dans le navigateur.

    Le cours est publié sur le site du formateur, pas embarqué dans le dépôt :
    on ouvre donc la vraie page plutôt que d'en rapatrier le contenu. Elle
    s'affiche telle qu'elle est publiée, et la lecture compte comme une visite
    réelle du site.
    """
    root = _root(lab_home)
    lang = _lang(root)
    lab = _resolve_lab(root, lab_id, lang)

    url = guide_url(lab)
    if url is None:
        error(_("guide_no_url", lab_id=lab.id))
        raise typer.Exit(1)

    # soft_wrap : une URL coupée sur deux lignes n'est plus copiable ni
    # exploitable dans un pipe. Elle doit sortir d'un seul tenant, même
    # au-delà de la largeur du terminal.
    if print_only:
        console.print(url, soft_wrap=True)
        return

    info(_("guide_opening", lab_id=lab.id))
    console.print(url, soft_wrap=True)
    # L'URL reste affichée : sur une machine sans navigateur (session SSH,
    # serveur), webbrowser rend False sans rien ouvrir, et l'apprenant doit
    # pouvoir la copier.
    if not webbrowser.open(url):
        error(_("guide_no_browser"))
