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
"""

from __future__ import annotations

import atexit
import os
import webbrowser
import shutil
import subprocess
import sys
from collections.abc import Callable
from pathlib import Path
from typing import Annotated, Any, Optional

import click
import typer
from typer.core import TyperGroup, TyperOption

from . import __version__
from .config import (
    clear_context, get_lab_home, read_context, set_active_lab,
    set_active_provider, set_course_pos, write_context,
)
from .i18n import _, get_lang, set_lang
from .infra.inventory import InfraNotProvisioned
from .models.hint import HintFile
from .sessions.store import (
    get_best_scores,
    get_results,
    hints_cost_total,
    next_hint_index,
    record_hint,
    reset_hints,
)
from .reporting import (
    console,
    error,
    info,
    print_check_result,
    print_course_end,
    print_doctor,
    print_course_section,
    print_course_toc,
    print_fullhelp,
    print_hint,
    print_lab_detail,
    print_labs_table,
    print_progress_table,
    print_scores_table,
    print_structure_reports,
    print_lab_challenge,
    print_lab_course,
    print_lab_welcome,
    success,
    update_console,
    warn,
)
from .models import (
    CourseManifest,
    LabDefinition,
    ProviderUnresolved,
    RepoMetadata,
)
from .reporting import machine
from .runtimes.base import EventCallback
from .services import (
    CheckResult,
    check_lab,
    clean_lab,
    evaluate_lab,
    get_all_labs,
    get_lab,
    guide_url,
    lab_status,
    next_pending_lab,
    open_lab_session,
    reset_lab,
    run_lab,
    validate_all_metadata,
    validate_all_structure,
)

class _I18nGroup(TyperGroup):
    """TyperGroup avec l'option --help traduite."""

    # ``ctx`` est annoté ``Any`` volontairement : typer a fait évoluer le
    # type du Context de get_help_option (click public en 0.25, copie
    # vendorée typer._click en 0.26+). Annoter ``Any`` garde la surcharge
    # valide (LSP) sans coupler le code à un module privé qui n'existe pas
    # dans toutes les versions. Le retour ``TyperOption`` est public et
    # stable.
    def get_help_option(self, ctx: Any) -> TyperOption | None:
        opt = super().get_help_option(ctx)
        if opt is not None:
            opt.help = _("opt_help")
        return opt


app = typer.Typer(
    name="dsoxlab",
    help=_("app_help"),
    no_args_is_help=True,
    rich_markup_mode="rich",
    add_completion=True,
    cls=_I18nGroup,
)

# ── Sous-application 'instructor' (commandes formateur) ───────────────────────

instructor_app = typer.Typer(
    name="instructor",
    help=_("cmd_instructor_help"),
    no_args_is_help=True,
    rich_markup_mode="rich",
    cls=_I18nGroup,
)
app.add_typer(instructor_app, name="instructor")

# ── Option globale lab-home ───────────────────────────────────────────────────

LabHomeOption = Annotated[
    Optional[Path],
    typer.Option(
        "--lab-home",
        envvar="LAB_HOME",
        help=_("opt_lab_home"),
        show_default=False,
    ),
]


def _root(lab_home: Optional[Path]) -> Path:
    return lab_home.resolve() if lab_home else get_lab_home()


def _read_repo(root: Path) -> RepoMetadata | None:
    """Wrapper de ``read_repo_metadata`` qui formate proprement les
    erreurs de résolution de provider (ValueError) en message CLI +
    typer.Exit(1), au lieu d'un traceback Python brut.
    """
    from .discovery.repo import read_repo_metadata

    try:
        return read_repo_metadata(root)
    except ValueError as exc:
        error(str(exc))
        raise typer.Exit(1)


def _require_provider(repo_meta: RepoMetadata) -> str:
    """Retourne le provider actif, ou sort proprement s'il n'est pas résolu.

    À n'appeler que dans les commandes d'infrastructure (provision,
    destroy, status…). Les commandes pédagogiques (list-labs, show,
    check, scores…) n'ont pas besoin de provider et ne doivent pas
    échouer quand le dépôt en déclare plusieurs.
    """
    try:
        return repo_meta.infra.require_provider()
    except ProviderUnresolved as exc:
        if not exc.candidates:
            error(_("provider_none_declared"))
        else:
            error(_("provider_required",
                    candidates=", ".join(exc.candidates),
                    first=exc.candidates[0]))
        raise typer.Exit(1)


def _lang(root: Path) -> str:
    """Langue effective : contexte > DSOXLAB_LANG > LANG système > en."""
    ctx = read_context(root)
    return get_lang(ctx_lang=ctx.lang)


def _complete_lab_id(
    ctx: click.Context, param: click.Parameter, incomplete: str
) -> list[Any]:
    """Retourne la liste des lab IDs disponibles pour l'auto-complétion."""
    from click.shell_completion import CompletionItem
    try:
        root = get_lab_home()
        labs = get_all_labs(root)
        return [
            CompletionItem(lab.id, help=lab.title)
            for lab in labs
            if lab.id.startswith(incomplete)
        ]
    except Exception:
        return []


def _detect_pytest(root: Path) -> tuple[bool, str, str | None]:
    """Détecte pytest dans le PATH, dans le venv du projet ou via uv."""
    pytest_path = shutil.which("pytest")
    if pytest_path:
        return True, pytest_path, None

    venv_candidates = [
        root / ".venv" / "bin" / "pytest",
        root / ".venv" / "Scripts" / "pytest.exe",
    ]
    for candidate in venv_candidates:
        if candidate.is_file():
            return True, f"{candidate} (project .venv)", None

    uv_path = shutil.which("uv")
    if uv_path:
        result = subprocess.run(
            [uv_path, "run", "pytest", "--version"],
            cwd=root,
            capture_output=True,
            text=True,
            timeout=10,
        )
        if result.returncode == 0:
            detail = result.stdout.strip() or result.stderr.strip() or "available via uv run"
            return True, detail, None

    return False, _("detail_pytest_missing"), "uv add --dev pytest pytest-testinfra"


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
) -> None:
    """Initialise la langue UI depuis le contexte avant toute commande."""
    if ctx.invoked_subcommand is None:
        return
    try:
        root = get_lab_home()
        lang = _lang(root)
        set_lang(lang)
    except Exception:  # noqa: S110 — silence volontaire : pas de contexte lab, on continue en langue par défaut
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
        from .services.update_check import available_update

        latest = available_update(__version__)
        if latest is None:
            return
        update_console.print(
            _("update_available", latest=latest, current=__version__)
        )
    except Exception:  # noqa: S110 — un avis ne casse jamais une commande
        return


# ── install ─────────────────────────────────────────────────────────────────

@app.command("install", help=_("cmd_install_help"))
def install() -> None:
    """Install the dsoxlab wrapper in ~/.local/bin and shell completion."""
    from typer.completion import get_completion_script

    # ── 1. Wrapper script in ~/.local/bin ─────────────────────────────────────
    local_bin = Path.home() / ".local" / "bin"
    local_bin.mkdir(parents=True, exist_ok=True)

    venv_binary = Path(sys.argv[0]).resolve()
    wrapper = local_bin / "dsoxlab"
    wrapper.write_text(f"#!/bin/sh\nexec {venv_binary} \"$@\"\n")
    wrapper.chmod(0o755)
    success(_("install_wrapper", path=str(wrapper), source=str(venv_binary)))

    # ── 2. Shell completion ────────────────────────────────────────────────────
    shell_name = Path(os.environ.get("SHELL", "bash")).name

    if shell_name == "zsh":
        zfunc_dir = Path.home() / ".zfunc"
        zfunc_dir.mkdir(exist_ok=True)
        comp_file = zfunc_dir / "_dsoxl"
        script = get_completion_script(  # noqa: S604 — `shell` = nom du shell Typer ("zsh"), pas un subprocess shell=True
            prog_name="dsoxlab", complete_var="_DSOXL_COMPLETE", shell="zsh"
        )
        comp_file.write_text(script)
        success(_("install_completion", path=str(comp_file)))

        zshrc = Path.home() / ".zshrc"
        zshrc_content = zshrc.read_text() if zshrc.exists() else ""
        additions = []
        if "fpath=(~/.zfunc $fpath)" not in zshrc_content:
            additions.append("fpath=(~/.zfunc $fpath)")
        if "autoload -Uz compinit" not in zshrc_content:
            additions.append("autoload -Uz compinit && compinit")
        if additions:
            with zshrc.open("a") as f:
                f.write("\n# dsoxlab completion\n" + "\n".join(additions) + "\n")
        info(_("install_rc", path=str(zshrc)))

    elif shell_name == "bash":
        bash_comp_dir = Path.home() / ".bash_completion.d"
        bash_comp_dir.mkdir(exist_ok=True)
        comp_file = bash_comp_dir / "dsoxlab"
        script = get_completion_script(  # noqa: S604 — `shell` = nom du shell Typer ("bash"), pas un subprocess shell=True
            prog_name="dsoxlab", complete_var="_DSOXL_COMPLETE", shell="bash"
        )
        comp_file.write_text(script)
        success(_("install_completion", path=str(comp_file)))

        bashrc = Path.home() / ".bashrc"
        source_line = f". {comp_file}"
        bashrc_content = bashrc.read_text() if bashrc.exists() else ""
        if source_line not in bashrc_content:
            with bashrc.open("a") as f:
                f.write(f"\n# dsoxlab completion\n{source_line}\n")
        info(_("install_rc", path=str(bashrc)))

    else:
        info(_("install_completion_unsupported", shell=shell_name))
        info(_("install_reload"))


# ── use ──────────────────────────────────────────────────────────────────────

@app.command("use", help=_("cmd_use_help"))
def use(
    context: Annotated[Optional[str], typer.Argument(help=_("cmd_use_arg"))] = None,
    lab_home: LabHomeOption = None,
    lang: Annotated[Optional[str], typer.Option("--lang", help=_("opt_lang"))] = None,
    target: Annotated[Optional[str], typer.Option("--target", "-t",
        help=_("opt_target"))] = None,
    provider: Annotated[Optional[str], typer.Option("--provider", "-p",
        help="Provider d'infra à activer (ex. kvm, outscale, incus). "
             "Override par DSOXLAB_PROVIDER. Persisté entre commandes.")] = None,
    reset: Annotated[bool, typer.Option("--reset", "-r", help=_("opt_use_reset"))] = False,
) -> None:
    root = _root(lab_home)
    if reset:
        clear_context(root)
        success(_("context_cleared"))
        return
    # Si seule l'option --target est donnée (pas de section/level),
    # on met juste à jour la target sans toucher au contexte.
    if context is None and target is None and lang is None and provider is None:
        clear_context(root)
        success(_("context_cleared"))
        return

    # Lecture brute du meta.yml (pas _resolve_provider) : on doit pouvoir
    # valider même quand la résolution standard laisse le provider non
    # résolu (plusieurs candidats sans choix actif).
    declared_providers: list[str] = []
    declared_sections: list[str] = []
    import yaml as _yaml
    from .discovery.repo import find_meta_yml

    meta_path = find_meta_yml(root) or (root / "meta.yml")
    if meta_path.is_file():
        try:
            raw = _yaml.safe_load(meta_path.read_text(encoding="utf-8")) or {}
        except _yaml.YAMLError as exc:
            error(f"Lecture meta.yml impossible : {exc}")
            raise typer.Exit(1)
        declared = (raw.get("infra") or {}).get("provider")
        if isinstance(declared, list):
            declared_providers = [str(p) for p in declared if p]
        elif isinstance(declared, str) and declared:
            declared_providers = [declared]
        declared_sections = [
            str(s.get("id")) for s in (raw.get("sections") or []) if s.get("id")
        ]

    # Garde-fou : `dsoxlab use incus` pose une SECTION nommée « incus »,
    # pas un provider — et filtre alors le catalogue sur une section qui
    # n'existe pas (« Aucun lab trouvé »). Piège d'autant plus vicieux que
    # le nom ressemble à un provider. On refuse et on guide.
    if (
        context is not None
        and context in declared_providers
        and context not in declared_sections
    ):
        error(_("provider_not_a_section", name=context))
        raise typer.Exit(1)

    # --provider <name> : valider contre les providers candidats du
    # meta.yml avant de l'enregistrer dans le contexte session.
    if provider is not None:
        if declared_providers and provider not in declared_providers:
            error(_("provider_unknown",
                    name=provider,
                    candidates=", ".join(declared_providers)))
            raise typer.Exit(1)
        set_active_provider(root, provider)
        success(f"Provider actif : [bold]{provider}[/bold]")

    section: str | None = None
    level: str | None = None
    if context:
        parts = context.strip().split("/", 1)
        section = parts[0] or None
        level = parts[1] if len(parts) > 1 else None
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

@app.command("list-labs", help=_("cmd_list_labs_help"))
def list_labs(
    lab_home: LabHomeOption = None,
    level: Annotated[Optional[str], typer.Option("--level", "-l", help=_("opt_level"))] = None,
    section: Annotated[Optional[str], typer.Option("--section", "-s", help=_("opt_section"))] = None,
    lab_type: Annotated[Optional[str], typer.Option("--type", "-t", help=_("opt_type"))] = None,
    bloc: Annotated[Optional[int], typer.Option("--bloc", "-b", help=_("opt_bloc"))] = None,
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
    labs = get_all_labs(root, lang=lang)
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
    print_labs_table(labs, scores)


# ── show ──────────────────────────────────────────────────────────────────────

@app.command("show", help=_("cmd_show_help"))
def show(
    lab_id: Annotated[str, typer.Argument(help=_("cmd_show_arg"), shell_complete=_complete_lab_id)],
    lab_home: LabHomeOption = None,
) -> None:
    root = _root(lab_home)
    lang = _lang(root)
    try:
        lab = get_lab(root, lab_id, lang=lang)
    except ValueError as exc:
        error(str(exc))
        raise typer.Exit(1)

    try:
        status = lab_status(lab)
    except RuntimeError:
        status = _("runtime_unavailable")

    print_lab_detail(lab, status=status)


# ── run ───────────────────────────────────────────────────────────────────────

@app.command("run", help=_("cmd_run_help"))
def run(
    lab_id: Annotated[str, typer.Argument(help=_("cmd_run_arg"), shell_complete=_complete_lab_id)],
    target: Annotated[Optional[str], typer.Option("--target", "-t",
        help=_("opt_run_target"))] = None,
    lab_home: LabHomeOption = None,
) -> None:
    root = _root(lab_home)
    lang = _lang(root)
    try:
        lab = get_lab(root, lab_id, lang=lang)
    except ValueError as exc:
        error(str(exc))
        raise typer.Exit(1)

    info(_("lab_starting", lab_id=lab.id, runtime=lab.runtime.type.value))
    try:
        if lab.runtime.type.value in ("vm", "kvm", "incus"):
            _run_ansible_with_progress(
                lab.path / "setup.yaml",
                lambda cb: run_lab(lab, target_name=target, on_event=cb),
            )
        else:
            run_lab(lab, target_name=target)
    except InfraNotProvisioned:
        # Avant le except RuntimeError : InfraNotProvisioned en hérite, et
        # mérite la phrase actionnable plutôt que son message technique.
        error(_("infra_not_provisioned"))
        raise typer.Exit(2) from None
    except RuntimeError as exc:
        error(str(exc))
        raise typer.Exit(2)

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

    open_lab_session(lab)   # bloquant : sous-shell interactif

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

@app.command("course", help=_("cmd_course_help"))
def course(
    lab_id: Annotated[Optional[str], typer.Argument(help=_("cmd_course_arg"), shell_complete=_complete_lab_id)] = None,
    section: Annotated[Optional[str], typer.Option("--section", "-s", help=_("cmd_course_opt_section"))] = None,
    next_section: Annotated[bool, typer.Option("--next", "-n", help=_("cmd_course_opt_next"))] = False,
    prev_section: Annotated[bool, typer.Option("--prev", "-p", help=_("cmd_course_opt_prev"))] = False,
    lab_home: LabHomeOption = None,
) -> None:
    root = _root(lab_home)
    lang = _lang(root)
    lab = _resolve_lab(root, lab_id, lang)


    manifest = CourseManifest.load(lab.path, lang=lang)

    if manifest is None:
        # Pas de course.yaml : fallback sur scenario.md
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
            # Jamais commencé → sommaire + section 1
            print_course_toc(lab, manifest)
            target_pos = 1

    # ── Fin de cours ─────────────────────────────────────────────────────────
    if target_pos > total:
        set_course_pos(root, total)
        print_course_end(lab, manifest)
        return

    # ── Affichage de la section ───────────────────────────────────────────────
    sec = manifest.sections[target_pos - 1]
    set_course_pos(root, target_pos)
    print_course_section(lab, sec, pos=target_pos, total=total)


# ── challenge ─────────────────────────────────────────────────────────────────

@app.command("challenge", help=_("cmd_challenge_help"))
def challenge_cmd(
    lab_id: Annotated[Optional[str], typer.Argument(help=_("cmd_challenge_arg"), shell_complete=_complete_lab_id)] = None,
    lab_home: LabHomeOption = None,
) -> None:
    root = _root(lab_home)
    lab = _resolve_lab(root, lab_id, _lang(root))
    print_lab_challenge(lab, lang=_lang(root))


# ── hint ──────────────────────────────────────────────────────────────────────

@app.command("guide", help=_("cmd_guide_help"))
def guide(
    lab_id: Annotated[Optional[str], typer.Argument(help=_("cmd_guide_arg"), shell_complete=_complete_lab_id)] = None,
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


@app.command("hint", help=_("cmd_hint_help"))
def hint(
    lab_id: Annotated[Optional[str], typer.Argument(help=_("cmd_hint_arg"), shell_complete=_complete_lab_id)] = None,
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
        lab = get_lab(root, effective_id, lang=lang)
    except ValueError as exc:
        error(str(exc))
        raise typer.Exit(1)

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

def _resolve_lab(
    root: Path, lab_id: str | None, lang: str
) -> LabDefinition:
    """Résout l'ID effectif et retourne le LabDefinition, ou lève typer.Exit."""
    ctx = read_context(root)
    effective_id = lab_id or ctx.active_lab
    if not effective_id:
        error(_("no_active_lab"))
        raise typer.Exit(1)
    try:
        return get_lab(root, effective_id, lang=lang)
    except ValueError as exc:
        error(str(exc))
        raise typer.Exit(1)


def _run_check_with_progress(
    lab: LabDefinition, target: str | None = None, *, quiet: bool = False,
) -> CheckResult:
    """Lance ``check_lab`` en streamant les verdicts pytest dans une
    progress bar Rich.

    ``target`` sélectionne la target du lab sur laquelle valider (labs
    multi-distrib). None = la target ``default`` du lab.

    Affiche un ✔/✘/⊘ par test et une barre M of N. En cas d'échec,
    le caller imprime le résumé/traceback contenu dans ``result.output``.
    """
    from rich.progress import (
        BarColumn,
        MofNCompleteColumn,
        Progress,
        SpinnerColumn,
        TextColumn,
        TimeElapsedColumn,
    )

    state: dict[str, Any] = {"done": 0, "task_id": None}

    # Mode machine : la barre et les verdicts partent sur stdout et
    # rendraient le document JSON illisible. On lance les tests sans rien
    # afficher — mesuré, sans cela la sortie commence par « ℹ Validation… ».
    if quiet:
        return check_lab(lab, target=target)

    with Progress(
        SpinnerColumn(),
        TextColumn("[bold]{task.description}"),
        BarColumn(bar_width=30),
        MofNCompleteColumn(),
        TimeElapsedColumn(),
        transient=False,
        console=console,
    ) as progress:
        task = progress.add_task("Collecte des tests…", total=None)
        state["task_id"] = task

        def on_event(event: dict[str, Any]) -> None:
            etype = event.get("type")
            if etype == "collected":
                total = event.get("total", 0) or None
                progress.update(
                    task,
                    description=f"Tests : {lab.id}",
                    total=total,
                )
            elif etype == "verdict":
                nodeid = event.get("nodeid", "?")
                verdict = event.get("verdict", "?")
                # Raccourcit le nodeid pour l'affichage : ne garde que test_xxx::test_yyy
                short = nodeid.rsplit("/", 1)[-1]
                state["done"] += 1
                progress.update(task, completed=state["done"])
                if verdict == "PASSED":
                    progress.console.print(f"  [green]✔[/green] {short}")
                elif verdict in ("FAILED", "ERROR"):
                    progress.console.print(f"  [red]✘ {short}  [dim]({verdict})[/dim][/red]")
                elif verdict == "SKIPPED":
                    progress.console.print(f"  [dim]⊘ {short}  (skipped)[/dim]")
                else:
                    progress.console.print(f"  [yellow]·[/yellow] {short}  [dim]({verdict})[/dim]")
            # Les autres lignes (log/header/traceback) sont gardées dans
            # result.output et imprimées seulement si le check échoue.

        result = check_lab(lab, target=target, on_event=on_event)
        progress.update(task, description=f"Tests {lab.id} terminés")

    return result


def _run_check(
    root: Path, lab: LabDefinition, target: str | None = None, *, quiet: bool = False,
) -> tuple[CheckResult, int, int]:
    """Lance les tests, enregistre le résultat, retourne (result, score, max_score).

    ``target`` (option ``--target``) l'emporte sur la target active de la
    session ; à défaut, la target ``default`` du lab s'applique.
    """
    # Même logique que pour --target : on refuse de NOTER ce qui n'a pas pu
    # tourner. Un lab VM sans infrastructure n'est pas un échec de l'apprenant
    # et ne doit pas lui coûter un 0/100 dans son historique. pytest tourne en
    # sous-processus, donc l'erreur du conftest ne remonterait pas jusqu'ici :
    # il faut vérifier AVANT.
    if lab.runtime.type.value in ("vm", "kvm", "incus"):
        from .discovery.repo import read_repo_metadata
        from .infra.inventory import build_inventory, read_terraform_outputs

        repo_meta = read_repo_metadata(root)
        if repo_meta is not None:
            try:
                build_inventory(
                    repo_meta,
                    terraform_outputs=read_terraform_outputs(repo_meta),
                )
            except InfraNotProvisioned:
                error(_("infra_not_provisioned"))
                raise typer.Exit(2) from None
            except ProviderUnresolved as exc:
                # Un dépôt qui déclare plusieurs providers sans qu'aucun ne
                # soit actif : lire les outputs Terraform est impossible, mais
                # ce n'est pas une faute de l'apprenant. Sans ce garde-fou, la
                # traceback remontait telle quelle depuis inventory.py.
                if not exc.candidates:
                    error(_("provider_none_declared"))
                else:
                    error(_("provider_required",
                            candidates=", ".join(exc.candidates),
                            first=exc.candidates[0]))
                raise typer.Exit(2) from None

    # Un --target explicite et inconnu est une ERREUR : on sort avant de
    # lancer quoi que ce soit, sinon une faute de frappe enregistrerait un
    # 0/100 dans l'historique de l'apprenant.
    if target is not None and lab.runtime.target(target) is None:
        declared = ", ".join(t.name for t in lab.runtime.targets) or "—"
        error(_("unknown_target", target=target, declared=declared))
        raise typer.Exit(1)

    # À défaut, la target de session. Elle vaut pour TOUS les labs du dépôt :
    # si celui-ci ne la déclare pas (lab shell, lab mono-target), on l'ignore
    # simplement — ce n'est pas une erreur de l'apprenant.
    if target is None:
        session_target = read_context(root).active_target
        if session_target and lab.runtime.target(session_target) is not None:
            target = session_target

    if not quiet:
        info(_("validating", lab_id=lab.id))
    result = _run_check_with_progress(lab, target, quiet=quiet)
    if not result.ok and not quiet:
        # En cas d'échec, dump l'output brut (tracebacks, summary pytest)
        # pour que l'apprenant voie les erreurs détaillées.
        #
        # « and not quiet » : sans lui, la sortie pytest précédait le document
        # JSON sur stdout dès qu'un test échouait, et le flux n'était plus
        # analysable. Le cas le plus fréquent en usage réel, et le plus facile
        # à manquer : un lab qui passe n'emprunte jamais cette branche.
        # L'appelant en mode machine retrouve ce texte dans check.output.
        console.print(result.output)

    evaluation = evaluate_lab(root, lab, result)
    if quiet:
        # Mode machine : le tableau Rich et le message de confirmation
        # pollueraient le document JSON. Le résultat est tout de même
        # enregistré, comme dans le mode normal.
        return result, evaluation.score, evaluation.max_score
    print_check_result(
        lab.id,
        result.passed,
        result.total,
        evaluation.max_score,
        evaluation.score,
        evaluation.hints_used,
        evaluation.hints_cost,
    )
    info(_("check_result_saved", score=evaluation.score, max_score=evaluation.max_score))
    return result, evaluation.score, evaluation.max_score


# ── check ─────────────────────────────────────────────────────────────────────

@app.command("check", help=_("cmd_check_help"))
def check(
    lab_id: Annotated[Optional[str], typer.Argument(help=_("cmd_check_arg"), shell_complete=_complete_lab_id)] = None,
    target: Annotated[Optional[str], typer.Option("--target", "-t",
        help=_("opt_check_target"))] = None,
    as_json: Annotated[bool, typer.Option("--json", help=_("opt_json"))] = False,
    lab_home: LabHomeOption = None,
) -> None:
    root = _root(lab_home)
    lab = _resolve_lab(root, lab_id, _lang(root))
    result, score, max_score = _run_check(root, lab, target, quiet=as_json)
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

@app.command("submit", help=_("cmd_submit_help"))
def submit(
    lab_id: Annotated[Optional[str], typer.Argument(help=_("cmd_submit_arg"), shell_complete=_complete_lab_id)] = None,
    target: Annotated[Optional[str], typer.Option("--target", "-t",
        help=_("opt_check_target"))] = None,
    lab_home: LabHomeOption = None,
) -> None:
    root = _root(lab_home)
    lab = _resolve_lab(root, lab_id, _lang(root))
    result, score, max_score = _run_check(root, lab, target)

    if result.ok:
        success(_("submit_success", score=score, max_score=max_score))
    else:
        info(_("submit_partial", passed=result.passed, total=result.total, score=score, max_score=max_score))

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

@app.command("scores", help=_("cmd_scores_help"))
def scores(
    lab_home: LabHomeOption = None,
    section: Annotated[Optional[str], typer.Option("--section", "-s", help=_("opt_section"))] = None,
    lab_id: Annotated[Optional[str], typer.Option("--lab", "-l", help=_("opt_filter_lab"))] = None,
    top: Annotated[int, typer.Option("--top", help=_("opt_top"))] = 20,
) -> None:
    root = _root(lab_home)
    ctx = read_context(root)
    effective_section = section or ctx.section
    results = get_results(root, lab_id=lab_id, section=effective_section, limit=top)
    print_scores_table(results)


# ── progress ──────────────────────────────────────────────────────────────────

@app.command("progress", help=_("cmd_progress_help"))
def progress(
    lab_home: LabHomeOption = None,
    section: Annotated[Optional[str], typer.Option("--section", "-s", help=_("opt_section"))] = None,
    level: Annotated[Optional[str], typer.Option("--level", "-l", help=_("opt_level"))] = None,
    as_json: Annotated[bool, typer.Option("--json", help=_("opt_json"))] = False,
) -> None:
    root = _root(lab_home)
    ctx = read_context(root)
    lang = _lang(root)

    effective_section = section or ctx.section
    effective_level = level or ctx.level

    labs = get_all_labs(root, lang=lang)
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

@app.command("next", help=_("cmd_next_help"))
def next_lab(
    lab_home: LabHomeOption = None,
) -> None:
    root = _root(lab_home)
    ctx = read_context(root)
    lang = _lang(root)

    if not ctx.section:
        error(_("next_no_context"))
        raise typer.Exit(1)

    labs = get_all_labs(root, lang=lang)
    if ctx.section:
        labs = [lab for lab in labs if lab.section == ctx.section]
    if ctx.level:
        labs = [lab for lab in labs if lab.level == ctx.level]

    scores_data = get_best_scores(root, [lab.id for lab in labs])

    upcoming = next_pending_lab(labs, scores_data)
    if upcoming is None:
        success(_("next_all_done"))
        return
    success(_("next_suggestion", lab_id=upcoming.id, title=upcoming.title))


# ── reset ─────────────────────────────────────────────────────────────────────

@app.command("reset", help=_("cmd_reset_help"))
def reset(
    lab_id: Annotated[str, typer.Argument(help=_("cmd_reset_arg"), shell_complete=_complete_lab_id)],
    target: Annotated[Optional[str], typer.Option("--target", "-t",
        help=_("opt_run_target"))] = None,
    lab_home: LabHomeOption = None,
) -> None:
    root = _root(lab_home)
    lang = _lang(root)
    try:
        lab = get_lab(root, lab_id, lang=lang)
    except ValueError as exc:
        error(str(exc))
        raise typer.Exit(1)

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
    except RuntimeError as exc:
        error(str(exc))
        raise typer.Exit(2)


# ── clean ─────────────────────────────────────────────────────────────────────

@app.command("clean", help=_("cmd_clean_help"))
def clean(
    lab_id: Annotated[str, typer.Argument(help=_("cmd_clean_arg"), shell_complete=_complete_lab_id)],
    target: Annotated[Optional[str], typer.Option("--target", "-t",
        help=_("opt_run_target"))] = None,
    lab_home: LabHomeOption = None,
    yes: Annotated[bool, typer.Option("--yes", "-y", help=_("opt_yes"))] = False,
) -> None:
    root = _root(lab_home)
    lang = _lang(root)
    try:
        lab = get_lab(root, lab_id, lang=lang)
    except ValueError as exc:
        error(str(exc))
        raise typer.Exit(1)

    if not yes:
        typer.confirm(_("confirm_clean", lab_id=lab.id), abort=True)

    info(_("cleaning", lab_id=lab.id))
    try:
        if lab.runtime.type.value in ("vm", "kvm", "incus"):
            _run_ansible_with_progress(
                lab.path / "cleanup.yaml",
                lambda cb: clean_lab(lab, target_name=target, on_event=cb),
            )
        else:
            clean_lab(lab, target_name=target)
        success(_("clean_done"))
    except RuntimeError as exc:
        error(str(exc))
        raise typer.Exit(2)


# ── validate-structure ────────────────────────────────────────────────────────

@app.command("validate-structure", help=_("cmd_validate_help"))
def validate_structure_cmd(
    lab_home: LabHomeOption = None,
) -> None:
    root = _root(lab_home)
    structure_reports = validate_all_structure(root)
    metadata_reports = validate_all_metadata(root)

    print_structure_reports(structure_reports)

    issues = [r for r in metadata_reports if not r.ok]
    if issues:
        console.print(_("metadata_issues_header"))
        for report in issues:
            for issue in report.issues:
                console.print(f"  [red]✘[/red] {report.lab_id} — {issue.field}: {issue.message}")

    all_ok = all(r.ok for r in structure_reports) and not issues
    if all_ok:
        success(_("all_labs_valid"))
    else:
        error(_("labs_have_issues"))
        raise typer.Exit(1)


# ── doctor ────────────────────────────────────────────────────────────────────

@app.command("doctor", help=_("cmd_doctor_help"))
def doctor(
    lab_home: LabHomeOption = None,
    fix: Annotated[bool, typer.Option("--fix", help=_("opt_fix"))] = False,
) -> None:
    root = _root(lab_home)
    checks: list[tuple[str, bool, str, str | None]] = []

    # Python
    checks.append((_( "check_python"), True, sys.version.split()[0], None))

    # pytest
    pytest_ok, pytest_detail, pytest_fix = _detect_pytest(root)
    checks.append((_("check_pytest"), pytest_ok, pytest_detail, pytest_fix))

    # Shell runtime
    checks.append((_("check_shell"), True, _("detail_shell_always"), None))


    # Incus : binaire + daemon + permissions user + init storage/network.
    # Le simple ``which incus`` ne suffit pas : sans daemon actif ni
    # appartenance au groupe ``incus``, le client ne peut rien faire
    # (erreur "permissions to talk to the incus daemon").
    incus_path = shutil.which("incus")
    if not incus_path:
        checks.append((
            _("check_incus"), False, _("detail_incus_missing"),
            "sudo apt install incus",
        ))
    else:
        # Test daemon actif via socket : on lance ``incus list`` qui
        # échoue distinctement selon la cause (daemon down, perm,
        # init manquant).
        ver = subprocess.run(
            ["incus", "--version"], capture_output=True, text=True, timeout=5,
        )
        version = ver.stdout.strip() or "?"

        probe = subprocess.run(
            ["incus", "list"], capture_output=True, text=True, timeout=5,
        )
        if probe.returncode == 0:
            checks.append((
                _("check_incus"), True,
                f"client {version}, daemon ok",
                None,
            ))
        else:
            err = (probe.stderr or "").lower()
            if "permission" in err or "socket" in err:
                # Soit daemon inactif, soit user pas dans le groupe.
                daemon_active = subprocess.run(
                    ["systemctl", "is-active", "--quiet", "incus.service"],
                ).returncode == 0
                if not daemon_active:
                    checks.append((
                        _("check_incus"), False,
                        f"client {version}, daemon inactif",
                        "sudo systemctl enable --now incus.service",
                    ))
                else:
                    checks.append((
                        _("check_incus"), False,
                        f"client {version}, user hors groupe incus (re-login requis)",
                        f"sudo usermod -aG incus,incus-admin {os.environ.get('USER', '$USER')}",
                    ))
            elif "no storage pools" in err or "init" in err:
                checks.append((
                    _("check_incus"), False,
                    f"client {version}, daemon ok mais non initialisé",
                    "sudo incus admin init --auto",
                ))
            else:
                tail = (probe.stderr or probe.stdout).strip().splitlines()
                msg = tail[-1] if tail else "erreur inconnue"
                checks.append((_("check_incus"), False, msg, None))

    # KVM
    virsh_path = shutil.which("virsh")
    if virsh_path:
        result = subprocess.run(
            ["virsh", "version"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        if result.returncode == 0:
            first_line = result.stdout.splitlines()[0] if result.stdout else "ok"
            checks.append((_("check_kvm"), True, first_line, None))
        else:
            checks.append((
                _("check_kvm"),
                False,
                _("detail_kvm_daemon_err"),
                "sudo systemctl start libvirtd",
            ))
    else:
        checks.append((
            _("check_kvm"),
            False,
            _("detail_kvm_missing"),
            "sudo apt install libvirt-clients libvirt-daemon-system qemu-kvm",
        ))

    # Labs détectés
    labs = get_all_labs(root)
    checks.append((_("check_labs"), len(labs) > 0, _("detail_labs_count", count=len(labs), root=root), None))

    # LAB_HOME
    checks.append((_("check_lab_home"), True, str(root), None))

    print_doctor(checks)

    if fix:
        failing = [(label, fix_cmd) for label, ok, _detail, fix_cmd in checks if not ok and fix_cmd]
        if not failing:
            info(_("fix_nothing"))
            return

        # Pr\u00e9-conditions sudo : si au moins un fix d\u00e9marre par "sudo", on
        # v\u00e9rifie que l'env est compatible avant d'attaquer (TTY pour
        # taper le password, sudo dispo, et id\u00e9alement on cache le
        # password une seule fois pour toute la cascade).
        sudo_fixes = [c for _, c in failing if c.strip().startswith("sudo ")]
        if sudo_fixes:
            if not sys.stdin.isatty():
                error(
                    "Au moins un fix exige sudo, mais ce shell n'est pas "
                    "interactif (pas de TTY). Lance dsoxlab depuis un "
                    "terminal ou applique les commandes manuellement."
                )
                raise typer.Exit(1)
            if shutil.which("sudo") is None:
                error("sudo introuvable dans le PATH \u2014 fix impossible.")
                raise typer.Exit(1)

            # Pr\u00e9-cache les credentials sudo : un seul prompt password
            # pour toute la cascade. Sans ce sudo -v, l'apprenant
            # pourrait avoir \u00e0 retaper son password \u00e0 chaque commande
            # (si sudo timestamp_timeout=0 ou si la cascade d\u00e9passe 5min).
            info(
                f"[bold]{len(sudo_fixes)}[/bold] commande(s) n\u00e9cessitent "
                "sudo. Pr\u00e9-authentification ci-dessous (un seul prompt "
                "pour toute la cascade) :"
            )
            preauth = subprocess.run(["sudo", "-v"])  # noqa: S603,S607
            if preauth.returncode != 0:
                error("Pr\u00e9-authentification sudo \u00e9chou\u00e9e \u2014 abandon des fixes.")
                raise typer.Exit(1)

        info(_("fix_count", count=len(failing)))
        for label, fix_cmd in failing:
            info(f"[bold]{label}[/bold] \u2192 {fix_cmd}")
            result = subprocess.run(fix_cmd, shell=True, text=True)  # noqa: S602
            if result.returncode == 0:
                success(_("fix_success", label=label))
            else:
                error(_("fix_failure", label=label, code=result.returncode))
        info(_("fix_rerun"))


# ── provision / destroy / ssh / status ────────────────────────────────────────


@app.command("provision", help=_("cmd_provision_help"))
def provision(
    host: Annotated[Optional[list[str]], typer.Option(
        "--host",
        help="Cible une seule VM (fqdn meta.yml). Répétable. Si absent, "
             "applique tout le plan. Les ressources partagées (réseau, "
             "images de base) sont gérées par Terraform en cascade.",
    )] = None,
    lab_home: LabHomeOption = None,
) -> None:
    """Lance terraform apply sur le provider courant avec progress bar."""
    from .infra import terraform as tf
    from .infra.terraform import ProviderNotImplemented, TerraformNotInstalled, host_targets

    root = _root(lab_home)
    repo_meta = _read_repo(root)
    if repo_meta is None:
        error(_("provision_no_meta", root=root))
        raise typer.Exit(1)

    provider = _require_provider(repo_meta)

    # Garde-fou cohabitation : incus et KVM partagent le nom de réseau et le
    # subnet du lab → ils ne peuvent pas coexister. Si un AUTRE provider a
    # encore de l'infra debout, on guide l'apprenant (destroy) plutôt que de
    # le laisser buter sur « Network is already in use ».
    conflicts = tf.other_active_providers(repo_meta)
    if conflicts:
        error(_(
            "provision_provider_conflict",
            current=provider,
            others=", ".join(conflicts),
            other=conflicts[0],
        ))
        raise typer.Exit(5)

    info(_("provision_starting", provider=provider))

    # Garde-fou : la clé SSH du repo doit exister avant tout provision.
    # Sans elle, le keypair cloud serait créé avec une clé publique
    # vide → VMs inaccessibles. Cas vécu sur Outscale lors d'un test
    # initial.
    ssh_key = repo_meta.path / "ssh" / "id_ed25519"
    if not ssh_key.is_file():
        error(_("provision_no_ssh_key", path=ssh_key))
        raise typer.Exit(1)

    # Construit la liste des targets Terraform pour les --host demandés.
    targets: list[str] = []
    if host:
        known = {h.name for h in repo_meta.infra.hosts}
        for fqdn in host:
            if fqdn not in known:
                error(f"Host inconnu : '{fqdn}'. Connus : {sorted(known)}")
                raise typer.Exit(1)
            try:
                targets.extend(host_targets(provider, fqdn))
            except NotImplementedError as exc:
                error(str(exc))
                raise typer.Exit(2)
        info(f"Cible Terraform : {', '.join(host)} ({len(targets)} ressources)")

    try:
        # Étape 1 : terraform init (peut télécharger ~50 MB de provider
        # au premier run). Spinner pour ne pas laisser l'utilisateur
        # croire que ça plante.
        _run_terraform_init_with_spinner(
            lambda cb: tf.init(repo_meta, on_event=cb)
        )
        # Étape 2 : terraform apply avec progress bar par ressource
        result = _run_terraform_with_progress(
            "provision",
            lambda cb: tf.apply(
                repo_meta, on_event=cb,
                targets=targets or None, target_hosts=list(host) if host else None,
            ),
        )
    except ProviderNotImplemented as exc:
        error(str(exc))
        raise typer.Exit(2)
    except TerraformNotInstalled as exc:
        error(str(exc))
        raise typer.Exit(3)
    except Exception as exc:  # noqa: BLE001 — message utilisateur direct
        error(_("provision_failed", error=str(exc)))
        raise typer.Exit(4)

    # Étape 3 : attendre que les VMs soient réellement joignables (sshd +
    # compte student + cloud-init terminé). Sans ça, le premier `dsoxlab run`
    # échoue en « unreachable » car la VM boote encore.
    from .infra.inventory import HostReadyTimeout, wait_for_hosts_ready

    ready_hosts = sorted(result.hosts)
    if ready_hosts:
        from rich.progress import (
            Progress,
            SpinnerColumn,
            TextColumn,
            TimeElapsedColumn,
        )

        with Progress(
            SpinnerColumn(),
            TextColumn("[bold]{task.description}"),
            TimeElapsedColumn(),
            transient=True,
            console=console,
        ) as progress:
            task = progress.add_task(_("provision_waiting_ssh"), total=None)

            def _on_attempt(fqdn: str, attempt: int) -> None:
                progress.update(
                    task,
                    description=_(
                        "provision_waiting_ssh_host", host=fqdn, attempt=attempt
                    ),
                )

            try:
                wait_for_hosts_ready(
                    repo_meta, ready_hosts, on_attempt=_on_attempt
                )
            except HostReadyTimeout as exc:
                progress.stop()
                warn(_("provision_ssh_timeout", error=str(exc)))

    # Le fragment SSH, écrit à CHAQUE provision et non seulement quand des
    # machines viennent d'être créées : relancer un provision sur une infra
    # déjà en place laissait sinon l'apprenant sans fragment, alors que c'est
    # le moment où il en a besoin. Il doit refléter l'état courant, pas le
    # delta du dernier terraform apply.
    from .infra.inventory import (
        build_inventory,
        read_terraform_outputs,
        ssh_config_include_present,
        user_ssh_config_path,
        write_ssh_config,
        write_user_ssh_config,
    )

    fragment = user_ssh_config_path(repo_meta)
    try:
        inv = build_inventory(
            repo_meta, terraform_outputs=read_terraform_outputs(repo_meta)
        )
        write_ssh_config(inv, repo_meta)
        write_user_ssh_config(inv, repo_meta)
    except (OSError, RuntimeError) as exc:
        # Un fragment manquant ne doit pas faire échouer un provision réussi.
        warn(_("ssh_fragment_failed", error=str(exc)))

    if fragment.is_file():
        if ssh_config_include_present():
            info(_("ssh_fragment_written", path=fragment))
        else:
            warn(_("ssh_fragment_no_include", path=fragment))

    success(_("provision_done", count=len(result.hosts)))
    for fqdn, ip in sorted(result.hosts.items()):
        info(f"  {fqdn} → {ip}")


@app.command("destroy", help=_("cmd_destroy_help"))
def destroy(
    host: Annotated[Optional[list[str]], typer.Option(
        "--host",
        help="Restreint la cible Terraform à un fqdn du meta.yml. Répétable. "
             "ATTENTION : Terraform détruit aussi tout ce qui dépend de la "
             "cible, donc cette option n'isole PAS une VM des autres. Pour "
             "récupérer une machine, préférer destroy complet + provision.",
    )] = None,
    yes: Annotated[bool, typer.Option(
        "--yes", "-y",
        help="Ne pas demander confirmation (usage non interactif).",
    )] = False,
    lab_home: LabHomeOption = None,
) -> None:
    """Lance terraform destroy sur le provider courant avec progress bar."""
    from .infra import terraform as tf
    from .infra.terraform import ProviderNotImplemented, TerraformNotInstalled, host_targets

    root = _root(lab_home)
    repo_meta = _read_repo(root)
    if repo_meta is None:
        error(_("provision_no_meta", root=root))
        raise typer.Exit(1)

    provider = _require_provider(repo_meta)

    targets: list[str] = []
    if host:
        known = {h.name for h in repo_meta.infra.hosts}
        for fqdn in host:
            if fqdn not in known:
                error(f"Host inconnu : '{fqdn}'. Connus : {sorted(known)}")
                raise typer.Exit(1)
            try:
                targets.extend(host_targets(provider, fqdn))
            except NotImplementedError as exc:
                error(str(exc))
                raise typer.Exit(2)
        info(f"Cible Terraform : {', '.join(host)} ({len(targets)} ressources)")
        # Mesuré le 2026-07-23 : terraform détruit la cible ET tout ce qui en
        # dépend. Les volumes et disques cloud-init étant chaînés aux domaines,
        # cibler un seul hôte emporte les autres (7 ressources détruites pour
        # 1 demandée). On prévient plutôt que de laisser croire à un ciblage fin.
        warn(_("destroy_host_not_isolated"))

    # destroy est irréversible et ne prévenait pas : un « dsoxlab destroy »
    # tapé dans le mauvais dépôt effaçait le parc sans un mot. --yes garde
    # l'usage scripté (CI, procédure de récupération documentée).
    if not yes:
        typer.confirm(_("confirm_destroy", provider=provider), abort=True)

    info(_("destroy_starting", provider=provider))
    try:
        # init est rapide en destroy (provider déjà téléchargé) mais
        # nécessaire si l'utilisateur a fait un upgrade dsoxlab entre temps
        _run_terraform_init_with_spinner(
            lambda cb: tf.init(repo_meta, on_event=cb)
        )
        _run_terraform_with_progress(
            "destroy",
            lambda cb: tf.destroy(
                repo_meta, on_event=cb,
                targets=targets or None, target_hosts=list(host) if host else None,
            ),
        )
    except ProviderNotImplemented as exc:
        error(str(exc))
        raise typer.Exit(2)
    except TerraformNotInstalled as exc:
        error(str(exc))
        raise typer.Exit(3)
    except Exception as exc:  # noqa: BLE001
        error(_("destroy_failed", error=str(exc)))
        raise typer.Exit(4)

    # Le fragment SSH pointe désormais des machines mortes : le laisser
    # enverrait l'apprenant vers des adresses recyclées, ce qui est pire que
    # pas de configuration du tout.
    from .infra.inventory import remove_user_ssh_config

    if remove_user_ssh_config(repo_meta):
        info(_("ssh_fragment_removed", repo=repo_meta.id))

    success(_("destroy_done"))


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

            if etype == "playbook_on_task_start":
                task_name = data.get("name") or data.get("task", "")
                state["current_task"] = task_name
                progress.update(task, description=f"Task: {task_name}")
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
        progress.update(task, description=f"{playbook_path.name} complete")


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
        progress.update(task, description="Terraform init complete")


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

        state["result"] = runner(on_event)
        # Une fois terminé, fixe la barre à 100 % avec un label final
        if state["total"] > 0:
            progress.update(
                task,
                description=f"{label_action} complete",
                completed=state["total"],
            )
        else:
            progress.update(task, description="Nothing to do", total=1, completed=1)

    return state["result"]


@app.command("status", help=_("cmd_status_help"))
def status(
    lab_home: LabHomeOption = None,
    as_json: Annotated[bool, typer.Option("--json", help=_("opt_json"))] = False,
) -> None:
    """Vérifie la connectivité SSH des hosts du meta.yml."""
    from .infra.inventory import build_inventory, read_terraform_outputs

    root = _root(lab_home)
    repo_meta = _read_repo(root)
    if repo_meta is None:
        error(_("provision_no_meta", root=root))
        raise typer.Exit(1)

    if not repo_meta.infra.hosts:
        # Un dépôt sans infrastructure est un cas normal (catalogue 100 % shell),
        # pas une erreur. En mode machine il faut tout de même un document :
        # une phrase Rich et un code 0 laissaient l'appelant sans rien à lire.
        if as_json:
            machine.emit({
                "provider": None,
                "hosts": [],
                "summary": {"reachable": 0, "total": 0},
            })
            return
        info(_("status_no_hosts"))
        return

    provider = _require_provider(repo_meta)

    from .infra.inventory import bastion_info

    tf_outputs = read_terraform_outputs(repo_meta)
    inventory = build_inventory(repo_meta, terraform_outputs=tf_outputs)
    hosts_dict = inventory["all"]["children"]["labenv"]["hosts"]
    bastion = bastion_info(tf_outputs, repo_meta=repo_meta)

    ssh_key = repo_meta.path / "ssh" / "id_ed25519"
    if not ssh_key.is_file():
        error(_("status_no_key", path=ssh_key))
        raise typer.Exit(1)

    # On rafraîchit le fragment SSH au passage : « provision » ne peut pas
    # toujours être rejoué (le provider libvirt refuse certaines mises à jour
    # avec « Update Not Supported »), et l'apprenant se retrouverait alors sans
    # moyen de régénérer sa configuration. « status » est la commande qu'on
    # lance justement quand on doute de l'état de l'infra.
    from .infra.inventory import write_user_ssh_config

    try:
        write_user_ssh_config(inventory, repo_meta)
    except OSError as exc:
        if not as_json:
            warn(_("ssh_fragment_failed", error=str(exc)))

    hotes: list[dict[str, Any]] = []
    if not as_json:
        info(_("status_checking", count=len(hosts_dict)))
    if bastion:
        info(_("status_via_bastion",
               bastion=bastion["fqdn"] or bastion["public_ip"]))

    ok_count = 0
    for fqdn, host_vars in sorted(hosts_dict.items()):
        ip = host_vars["ansible_host"]
        cmd = [
            "ssh",
            # -F /dev/null : ignore la config SSH perso de l'apprenant
            # (~/.ssh/config) qui peut contenir un ProxyJump appliqué
            # par pattern d'IP (ex: "Host 10.*" → bastion). Sans ça,
            # un fqdn lab en 10.x.x.x peut être routé vers un bastion
            # tiers qui ne répond pas → "Connection to UNKNOWN port
            # 65535 timed out".
            "-F", "/dev/null",
            "-o", "ConnectTimeout=4", "-o", "BatchMode=yes",
            "-o", "StrictHostKeyChecking=no",
            "-o", "UserKnownHostsFile=/dev/null",
            "-i", str(ssh_key),
        ]
        # ProxyCommand explicite (pas ProxyJump) pour pouvoir
        # injecter -i sur le hop bastion. ProxyJump natif d'OpenSSH
        # ne propage pas le -i et utilise la clé par défaut de
        # l'utilisateur (~/.ssh/id_ed25519), qui ne matche pas notre
        # keypair lab → "Permission denied (publickey)".
        if bastion:
            proxy_target = bastion["fqdn"] or bastion["public_ip"]
            cmd += [
                "-o",
                (
                    f"ProxyCommand=ssh -F /dev/null -W %h:%p "
                    f"-i {ssh_key} "
                    f"-o StrictHostKeyChecking=no "
                    f"-o UserKnownHostsFile=/dev/null "
                    f"{bastion['user']}@{proxy_target}"
                ),
            ]
        cmd += [f"{host_vars.get('ansible_user', 'ansible')}@{ip}", "true"]
        result = subprocess.run(cmd, capture_output=True, timeout=15)  # noqa: S603
        joignable = result.returncode == 0
        raison = None
        if not joignable:
            stderr_tail = result.stderr.decode(errors="replace").strip().splitlines()[-1:]
            raison = stderr_tail[0] if stderr_tail else "timeout"
        hotes.append({"fqdn": fqdn, "ip": ip, "reachable": joignable, "reason": raison})
        if as_json:
            ok_count += 1 if joignable else 0
            continue
        if joignable:
            success(f"  ✔ {fqdn} ({ip})")
            ok_count += 1
        else:
            error(f"  ✘ {fqdn} ({ip}) — {raison}")

    if as_json:
        machine.emit({
            "provider": provider,
            "hosts": hotes,
            "summary": {"reachable": ok_count, "total": len(hosts_dict)},
        })
        if ok_count != len(hosts_dict):
            raise typer.Exit(1)
        return
    if ok_count == len(hosts_dict):
        success(_("status_all_ok", count=ok_count))
    else:
        error(_("status_partial",
                ok=ok_count, total=len(hosts_dict),
                provider=provider))
        raise typer.Exit(1)


@app.command("ssh", help=_("cmd_ssh_help"))
def ssh_cmd(
    host: Annotated[str, typer.Argument(help=_("cmd_ssh_arg"))],
    lab_home: LabHomeOption = None,
) -> None:
    """Ouvre une session SSH interactive sur un host du meta.yml.

    Si l'infrastructure expose un bastion (output Terraform ``bastion``),
    SSH passe automatiquement par ProxyJump (règle non contournable
    pour les providers cloud — REFACTORING-PLAN §11.8).
    """
    from .infra.inventory import bastion_info, build_inventory, read_terraform_outputs

    root = _root(lab_home)
    repo_meta = _read_repo(root)
    if repo_meta is None:
        error(_("provision_no_meta", root=root))
        raise typer.Exit(1)

    # Accepter le nom court (alma-rhcsa-1) ou le FQDN (alma-rhcsa-1.lab)
    target_fqdn: str | None = None
    for h in repo_meta.infra.hosts:
        if h.name == host or h.name.split(".", 1)[0] == host:
            target_fqdn = h.name
            break
    if target_fqdn is None:
        error(_("ssh_unknown_host", host=host,
                hosts=", ".join(h.name for h in repo_meta.infra.hosts)))
        raise typer.Exit(1)

    tf_outputs = read_terraform_outputs(repo_meta)
    inventory = build_inventory(repo_meta, terraform_outputs=tf_outputs)
    host_vars = inventory["all"]["children"]["labenv"]["hosts"][target_fqdn]
    ip = host_vars["ansible_host"]
    bastion = bastion_info(tf_outputs, repo_meta=repo_meta)

    ssh_key = repo_meta.path / "ssh" / "id_ed25519"
    cmd = [
        "ssh",
        # -F /dev/null : ignore la config SSH perso de l'apprenant.
        "-F", "/dev/null",
        "-o", "StrictHostKeyChecking=no",
        "-o", "UserKnownHostsFile=/dev/null",
        "-i", str(ssh_key),
    ]
    if bastion:
        proxy_target = bastion["fqdn"] or bastion["public_ip"]
        # ProxyCommand explicite avec -i pour le hop bastion
        # (OpenSSH ProxyJump n'applique pas -i aux hops).
        # -F /dev/null aussi côté bastion pour la même raison.
        cmd += [
            "-o",
            (
                f"ProxyCommand=ssh -F /dev/null -W %h:%p "
                f"-i {ssh_key} "
                f"-o StrictHostKeyChecking=no "
                f"-o UserKnownHostsFile=/dev/null "
                f"{bastion['user']}@{proxy_target}"
            ),
        ]
        info(_("ssh_via_bastion", host=target_fqdn, ip=ip,
                bastion=proxy_target))
    else:
        info(_("ssh_connecting", host=target_fqdn, ip=ip))
    cmd.append(f"{host_vars.get('ansible_user', 'ansible')}@{ip}")
    os.execvp("ssh", cmd)  # noqa: S606 — exec direct de ssh sans shell, argv construit en interne


# ── instructor : commandes formateur ─────────────────────────────────────────


@instructor_app.command("bootstrap", help=_("cmd_instructor_bootstrap_help"))
def instructor_bootstrap(
    lab_home: LabHomeOption = None,
) -> None:
    """Génère la clé SSH du lab si absente et vérifie les prérequis.

    Crée ``<repo>/ssh/id_ed25519`` (+ .pub) sans passphrase. La clé
    publique est ensuite injectée dans le tfvars par dsoxlab provision
    pour être propagée aux VMs via cloud-init.

    Vérifie la présence de ``terraform`` et ``ansible-runner``.
    """
    root = _root(lab_home)
    ssh_dir = root / "ssh"
    private_key = ssh_dir / "id_ed25519"
    public_key = ssh_dir / "id_ed25519.pub"

    if private_key.is_file() and public_key.is_file():
        info(_("bootstrap_key_exists", path=private_key))
    else:
        info(_("bootstrap_generating_key", path=private_key))
        ssh_dir.mkdir(parents=True, exist_ok=True)
        ssh_dir.chmod(0o700)
        result = subprocess.run(  # noqa: S603 — args contrôlés
            [
                "ssh-keygen",
                "-t", "ed25519",
                "-N", "",  # pas de passphrase
                "-C", "dsoxlab-lab",
                "-f", str(private_key),
            ],
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            error(_("bootstrap_keygen_failed", stderr=result.stderr.strip()))
            raise typer.Exit(2)
        success(_("bootstrap_key_created", path=private_key))

    # Vérifie les outils requis
    from .infra import ansible as ansible_infra
    from .infra import terraform as tf

    if not tf.is_available():
        error(_("bootstrap_no_terraform"))
    else:
        info(_("bootstrap_terraform_ok"))

    if not ansible_infra.is_available():
        error(_("bootstrap_no_ansible_runner"))
    else:
        info(_("bootstrap_ansible_runner_ok"))


# ── fullhelp ──────────────────────────────────────────────────────────────────

@app.command("fullhelp", help=_("cmd_fullhelp_help"))
def fullhelp() -> None:
    print_fullhelp()


# ── point d'entrée console ────────────────────────────────────────────────────

def main() -> None:
    """Point d'entrée de la commande ``dsoxlab``.

    Enveloppe l'app Typer pour rendre les erreurs ATTENDUES en une phrase
    actionnable, jamais en traceback Python. Une infrastructure non
    provisionnée est une situation normale (premier lancement, après un
    ``destroy``) : l'apprenant doit lire quoi faire, pas une pile d'appels.

    Les erreurs inattendues, elles, continuent de remonter avec leur
    traceback — c'est ce qu'on veut pour un vrai bug.
    """
    try:
        app()
    except InfraNotProvisioned:
        error(_("infra_not_provisioned"))
        raise SystemExit(1) from None
