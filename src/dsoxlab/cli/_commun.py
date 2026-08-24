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

import atexit
import logging
import sys
from pathlib import Path
from typing import Annotated, Any, NoReturn

import typer

from .. import __version__
from ..config import (
    get_lab_home,
    read_context,
)
from ..i18n import _, get_lang, set_lang
from ..infra.inventory import InfraNotProvisioned
from ..interrupt import (
    EXIT_INTERRUPTED,
    Interrupted,
    Stage,
    interruptible,
)
from ..locking import EXIT_LOCKED, RepoLock, RepoLocked
from ..logging_setup import configurer as configurer_journal
from ..models import (
    ContractError,
    LabDefinition,
    ProviderUnresolved,
    RepoMetadata,
    UnsupportedSchemaVersion,
)
from ..reporting import (
    console,
    error,
    info,
    print_check_result,
    success,
    update_console,
    warn,
)
from ..services import (
    CheckResult,
    check_lab,
    evaluate_lab,
    find_lab,
    get_all_labs,
    host_diagnosis,
)
from ._socle import app

logger = logging.getLogger(__name__)



# ── Option globale lab-home ───────────────────────────────────────────────────

LabHomeOption = Annotated[
    Path | None,
    typer.Option(
        "--lab-home",
        envvar="LAB_HOME",
        help=_("opt_lab_home"),
        show_default=False,
    ),
]


#: Les affichages longs (cours, mission de challenge) passent par le pager
#: dès qu'ils dépassent l'écran. L'option permet de retrouver le déversement
#: brut, par exemple pour copier tout un README d'un seul tenant.
NoPagerOption = Annotated[
    bool,
    typer.Option("--no-pager", help=_("opt_no_pager")),
]


def _root(lab_home: Path | None) -> Path:
    return lab_home.resolve() if lab_home else get_lab_home()


def _contrat_trop_recent(exc: UnsupportedSchemaVersion) -> NoReturn:
    """Rend l'erreur de version du ``meta.yml`` et sort.

    Le ``meta.yml`` décrit tout le catalogue : ne pas savoir le lire ne laisse
    rien de fiable derrière. On ne dégrade donc pas, on nomme la cause et la
    réparation, qui n'est pas dans le dépôt de labs mais dans la version de
    l'outil.
    """
    error(_(
        "schema_version_meta_too_new",
        path=exc.source, found=exc.found, supported=exc.supported,
    ))
    raise typer.Exit(1)


def _phrase_contrat(exc: ContractError) -> str:
    """La phrase d'un champ du contrat que le moteur ne sait pas lire.

    Le modèle porte les faits (``source``, ``field``) et la **clé** ; la phrase
    se compose ici, dans la langue de l'apprenant. Le chemin du fichier encadre
    le message plutôt que d'entrer dans chaque traduction : il est le même pour
    toutes, et le répéter dans les tables les ferait diverger.

    Un seul endroit la compose, parce que deux appelants la disent :
    :func:`_contrat_illisible`, qui sort en ``typer.Exit``, et le filet de
    :func:`main`, qui sort en ``SystemExit``.
    """
    return f"{exc.source}: {_(exc.key, **exc.params)}"


def _contrat_illisible(exc: ContractError) -> NoReturn:
    """Rend l'erreur de contrat et sort, pour les commandes qui lisent le catalogue."""
    error(_phrase_contrat(exc))
    raise typer.Exit(1)


def _read_repo(root: Path) -> RepoMetadata | None:
    """Wrapper de ``read_repo_metadata`` qui formate proprement les
    erreurs de résolution de provider (ValueError) en message CLI +
    typer.Exit(1), au lieu d'un traceback Python brut.
    """
    from ..discovery.repo import read_repo_metadata

    try:
        return read_repo_metadata(root)
    # AVANT ValueError, dont elles héritent toutes deux : `str(exc)` rendrait
    # un message technique et non traduit là où la cause mérite une phrase.
    except UnsupportedSchemaVersion as exc:
        _contrat_trop_recent(exc)
    # Le meta.yml est le seul fichier du contrat dont les erreurs de lecture
    # s'affichent : le modèle porte la clé et les faits, la phrase se compose
    # dans `_contrat_illisible`.
    except ContractError as exc:
        _contrat_illisible(exc)
    except ValueError as exc:
        error(str(exc))
        raise typer.Exit(1) from None


def _catalogue(root: Path, lang: str, *, quiet: bool = False) -> list[LabDefinition]:
    """Le catalogue, et un mot sur ce qu'il a fallu en écarter.

    Un ``lab.yaml`` au contrat trop récent est laissé de côté — c'est la seule
    chose honnête à en faire — mais jamais en silence : sans cet
    avertissement, la seule trace serait un lab absent, le symptôme le plus
    coûteux à diagnostiquer de tout le contrat.

    ``quiet`` sert au mode ``--json``, où la sortie standard ne doit porter
    qu'un document et rien d'autre.
    """
    from ..discovery.scanner import scan_catalog

    try:
        scan = scan_catalog(root, lang=lang)
    except UnsupportedSchemaVersion as exc:
        _contrat_trop_recent(exc)
    # Le scanner relit le meta.yml pour l'ordre des sections : un champ mal
    # typé y remontait donc en traceback, sur `list-labs` comme sur `progress`,
    # alors que `_read_repo` disait déjà la phrase sur les autres commandes.
    except ContractError as exc:
        _contrat_illisible(exc)
    if not quiet:
        for ecarte in scan.unsupported:
            warn(_(
                "schema_version_lab_skipped",
                path=ecarte.source, found=ecarte.found, supported=ecarte.supported,
            ))
    return scan.labs


def _lab(root: Path, lab_id: str, lang: str) -> LabDefinition:
    """Un lab par son identifiant, en nommant d'abord ce qui a été écarté.

    Sans cela, ``dsoxlab show <id>`` d'un lab au contrat trop récent répondrait
    « lab introuvable », et laisserait croire à une faute de frappe plutôt qu'à
    un outil à mettre à jour.
    """
    return find_lab(_catalogue(root, lang), lab_id)


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
        raise typer.Exit(1) from None


def _verrou(root: Path, commande: str) -> RepoLock:
    """Prend le verrou d'écriture du dépôt, ou sort en nommant qui le tient.

    À n'appeler que dans les commandes qui **modifient** l'état. Les commandes
    de lecture (``list-labs``, ``show``, ``scores``, ``progress``, ``next``,
    ``status``, ``doctor``, ``course``, ``challenge``, ``hint``, ``guide``,
    ``validate-structure``, ``support``, ``fullhelp``) ne passent pas par ici :
    consulter son catalogue pendant qu'un ``provision`` tourne dans un autre
    terminal est un usage normal, pas un conflit.

    Le verrou rendu est **déjà pris**. L'appelant choisit sa portée :

    - ``ctx.call_on_close(_verrou(...).release)`` pour toute la commande ;
    - ``with _verrou(...):`` pour la seule phase qui écrit. C'est ce que fait
      ``run``, qui doit rendre le verrou **avant** d'ouvrir la session
      interactive, sinon le ``dsoxlab check`` que l'apprenant tape dans ce
      sous-shell serait refusé par sa propre session.
    """
    verrou = RepoLock(root, commande)
    try:
        verrou.acquire()
    except RepoLocked as exc:
        detenteur = exc.holder
        if detenteur is None:
            error(_("lock_busy_anonymous", path=exc.path))
        else:
            error(_(
                "lock_busy",
                command=detenteur.command, pid=detenteur.pid,
                age=detenteur.age_label,
            ))
        info(_("lock_busy_hint"))
        raise typer.Exit(EXIT_LOCKED) from None
    return verrou


def _interrompu(exc: Interrupted, reprise: str) -> NoReturn:
    """Rend une interruption : ce qui reste en place, puis comment reprendre.

    Trois affirmations, dans cet ordre, et le code de sortie **130** qui les
    confirme (``128 + SIGINT``) : ce qui a été interrompu, ce que ça laisse
    derrière, et la commande qui reprend. Le code, typer le rendait déjà ; ce
    qui manquait, c'était la phrase, et sur le chemin Ansible le code lui-même,
    qui annonçait un échec (2) là où l'apprenant avait appuyé sur Ctrl-C.
    """
    warn(_(exc.message_key))
    if exc.hard:
        warn(_("interrupted_hard"))
    info(_("interrupt_resume", cmd=reprise))
    raise typer.Exit(EXIT_INTERRUPTED)


def _services_repo_id(root: Path) -> str:
    """Slug du dépôt, pour namespacer les conteneurs de services.

    Le ``meta.yml`` fournit ``repo.id`` ; à défaut, le nom du répertoire racine.
    """
    from ..discovery.repo import read_repo_metadata
    try:
        meta = read_repo_metadata(root)
    except ValueError:
        meta = None
    return meta.id if meta else root.name


def _ensure_services(lab: LabDefinition, root: Path) -> None:
    """Démarre les services conteneurisés déclarés par le lab, avant run/check.

    Sans service déclaré, ne fait rien. Si Docker est injoignable ou qu'un
    service ne démarre pas, sort proprement : un lab qui déclare un service ne
    peut pas fonctionner sans lui.
    """
    if not lab.runtime.services:
        return
    from ..runtimes import services as svc
    if not svc.docker_available():
        error(_("services_docker_absent"))
        raise typer.Exit(2)
    repo_id = _services_repo_id(root)
    for service in lab.runtime.services:
        info(_("service_starting", name=service.name, image=service.image))
        # Le démarrage attend les sondes du service, jusqu'à `ready_timeout`
        # secondes : c'est le point d'attente le plus long d'un lab shell, donc
        # celui où le Ctrl-C tombe.
        with interruptible(Stage.SERVICES):
            try:
                svc.start(service, repo_id)
            except svc.ServiceError as exc:
                error(_("service_failed", name=service.name, detail=str(exc)))
                raise typer.Exit(2) from None
        success(_("service_ready", name=service.name))


def _stop_services(lab: LabDefinition, root: Path) -> None:
    """Arrête les services conteneurisés du lab, à destroy/clean. Best-effort."""
    if not lab.runtime.services:
        return
    from ..runtimes import services as svc
    if not svc.docker_available():
        return
    repo_id = _services_repo_id(root)
    for service in lab.runtime.services:
        if svc.stop(service, repo_id):
            info(_("service_stopped", name=service.name))


def _lang(root: Path) -> str:
    """Langue effective : contexte > DSOXLAB_LANG > LANG système > en."""
    ctx = read_context(root)
    return get_lang(ctx_lang=ctx.lang)


def _complete_lab_id(incomplete: str) -> list[tuple[str, str]]:
    """Propose les lab IDs du dépôt courant, filtrés par ce qui est déjà saisi.

    Contrat **typer**, pas celui de click. Deux différences, et elles ne sont
    pas cosmétiques :

    - typer construit lui-même les paramètres passés ici, d'après les
      annotations de cette signature (``incomplete: str`` reçoit le préfixe
      saisi). Il n'attend donc pas les trois positionnels
      ``(ctx, param, incomplete)`` de click, et ce qu'on ne déclare pas n'est
      pas injecté ;
    - le retour est une liste de couples ``(valeur, aide)``. C'est typer qui en
      fait des ``CompletionItem`` : lui rendre l'objet click directement casse
      son adaptateur, qui exige une chaîne ou un couple.

    Le second élément du couple est l'aide affichée à côté de la proposition,
    c'est-à-dire le titre du lab. Elle survit à la migration, et zsh l'affiche.
    """
    try:
        root = get_lab_home()
        labs = get_all_labs(root)
        return [
            (lab.id, lab.title)
            for lab in labs
            if lab.id.startswith(incomplete)
        ]
    # Aveugle, et délibérément : une complétion s'exécute à chaque Tab, dans un
    # répertoire quelconque. Un meta.yml absent, un lab.yaml qui lève, un
    # catalogue à moitié écrit — rien de tout cela ne doit faire cracher une
    # trace Python dans le shell de l'apprenant. Pas de proposition, et c'est tout.
    except Exception:  # noqa: BLE001
        return []


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


#: Les familles de contrôle de ``validate-structure``, dans l'ordre où elles
#: sont jouées. Elles figurent **toutes** dans ``counts``, à zéro s'il le faut :
#: un tableau de bord qui n'aurait pas la clé ne saurait pas si la famille est
#: saine ou si cette version de l'outil ne la connaît pas.
_FAMILLES_ANOMALIES = (
    "contract", "unknown_key", "structure", "content", "doc_url", "metadata",
)


def _compter(anomalies: list[dict[str, Any]]) -> dict[str, int]:
    """Le nombre d'anomalies par famille, toutes familles présentes."""
    compte = dict.fromkeys(_FAMILLES_ANOMALIES, 0)
    for anomalie in anomalies:
        compte[str(anomalie["kind"])] += 1
    return compte


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
        return _lab(root, effective_id, lang)
    except ValueError as exc:
        error(str(exc))
        raise typer.Exit(1) from None


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
                    description=_("progress_tests_running", lab_id=lab.id),
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
        progress.update(task, description=_("progress_tests_done", lab_id=lab.id))

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
        from ..discovery.repo import read_repo_metadata
        from ..infra.inventory import build_inventory, read_terraform_outputs

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

    # Le verrou couvre les services ET pytest. Les tests pilotent la machine
    # du lab (ou ses conteneurs) : deux validations concurrentes se marchent
    # dessus, et la seconde note un état que la première est en train de
    # changer. Il est pris ICI, pas au début : tout ce qui précède ne fait que
    # lire, et refuser une faute de frappe sur `--target` pour cause de verrou
    # serait absurde.
    with _verrou(root, "check"):
        return _valider(root, lab, target, quiet=quiet)


def _valider(
    root: Path, lab: LabDefinition, target: str | None, *, quiet: bool,
) -> tuple[CheckResult, int, int]:
    """Joue les tests et enregistre la note. Appelé sous verrou."""
    # Les services conteneurisés (émulateur cloud, base…) doivent être debout
    # avant que pytest ne s'exécute : les tests pilotent l'API qu'ils exposent.
    _ensure_services(lab, root)

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


def _undefine_command(orphans: dict[str, str]) -> str:
    """La commande exacte qui retire des machines restées sur l'hyperviseur.

    Rendue copiable telle quelle : dire « supprime-les » sans donner le geste
    laisse l'apprenant chercher ``virsh undefine``, qu'aucune page du parcours
    ne lui a montré. ``sudo`` sans ``-n``, ici : c'est un humain qui la tape,
    un mot de passe demandé au terminal ne pose aucun problème.
    """
    return "; ".join(
        f"sudo virsh undefine --nvram {domain}" for domain in sorted(orphans.values())
    )


def _diagnostic_message(hote: dict[str, Any]) -> str:
    """La phrase qui nomme la cause d'un hôte muet, et le geste qui la corrige.

    Une cause, un message, une action. L'ancien texte en proposait deux à la
    fois — « cloud-init tourne peut-être encore, ou alors reprovisionne » — pour
    tous les hôtes et toutes les pannes : l'apprenant devait trancher lui-même
    entre deux conseils dont l'un coûtait une infrastructure entière.
    """
    cause = hote["cause"]
    domaine = hote.get("domain") or hote["fqdn"]
    if cause == host_diagnosis.CAUSE_DOMAIN_ABSENT:
        return _("status_cause_domain_absent", host=hote["fqdn"])
    if cause == host_diagnosis.CAUSE_DOMAIN_NOT_RUNNING:
        return _("status_cause_domain_not_running",
                 domain=domaine, state=hote.get("domain_state") or "?")
    if cause == host_diagnosis.CAUSE_DOMAIN_NO_LEASE:
        return _("status_cause_domain_no_lease", domain=domaine)
    if cause == host_diagnosis.CAUSE_BOOTING:
        return _("status_cause_booting", domain=domaine)
    if cause == host_diagnosis.CAUSE_SSH_REFUSED:
        return _("status_cause_ssh_refused", ip=hote["ip"])
    if cause == host_diagnosis.CAUSE_UNREACHABLE:
        return _("status_cause_unreachable", ip=hote["ip"])
    if cause == host_diagnosis.CAUSE_SSH_TIMEOUT:
        return _("status_cause_ssh_timeout", ip=hote["ip"])
    if cause == host_diagnosis.CAUSE_SSH_DENIED:
        return _("status_cause_ssh_denied", ip=hote["ip"])
    return _("status_cause_unknown", reason=hote.get("reason") or "?")
