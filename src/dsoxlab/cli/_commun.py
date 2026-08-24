"""Les helpers partagés du paquet : résoudre le contexte d'une commande.

Racine du dépôt, catalogue, lab actif, langue, provider, verrou d'écriture,
services conteneurisés : chaque commande commence par quelques-unes de ces
résolutions, et elles se composent ici, une seule fois. L'amorçage de l'app
(callback global, ``--version``, avis de mise à jour) vit dans ``_amorcage``,
le verdict d'un lab dans ``_validation``.

Convention de ce module : un ``except`` qui a déjà rendu la cause en une phrase
traduite (``error(...)``) sort par ``raise typer.Exit(n) from None``. Le ``from
None`` n'est pas un raccourci, c'est l'affirmation que la cause a été dite à
l'utilisateur, et qu'un chaînage d'exceptions n'ajouterait qu'une trace Python
au-dessus d'un message déjà écrit pour lui. Partout ailleurs, on chaîne.
"""

from __future__ import annotations

from pathlib import Path
from typing import Annotated, NoReturn

import typer

from ..config import (
    get_lab_home,
    read_context,
)
from ..i18n import _, get_lang
from ..interrupt import (
    EXIT_INTERRUPTED,
    Interrupted,
    Stage,
    interruptible,
)
from ..locking import EXIT_LOCKED, RepoLock, RepoLocked
from ..models import (
    ContractError,
    LabDefinition,
    ProviderUnresolved,
    RepoMetadata,
    UnsupportedSchemaVersion,
)
from ..reporting import (
    error,
    info,
    success,
    warn,
)
from ..services import (
    find_lab,
    get_all_labs,
)

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
