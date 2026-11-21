"""``infra stop``, ``infra pause`` et ``infra start`` (issue #405).

Arrêter les machines d'un catalogue sans les détruire. La logique vit dans
:mod:`dsoxlab.infra.alimentation` ; ce module prépare, prend le verrou et
affiche.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Annotated

import typer

from ..exit_codes import ExitCode
from ..i18n import _
from ..infra import alimentation
from ..infra.alimentation import Action, Issue, ProviderSansAlimentation, Resultat
from ..reporting import error, info, success, warn
from ..utils.shell import CommandError
from ._commun import LabHomeOption, _read_repo, _require_provider, _root, _verrou
from ._socle import infra_app

logger = logging.getLogger(__name__)

HostOption = Annotated[list[str] | None, typer.Option("--host", help=_("opt_alim_host"))]
AllOption = Annotated[bool, typer.Option("--all", help=_("opt_alim_all"))]


def _afficher(action: Action, r: Resultat, delai: int) -> None:
    if r.issue is Issue.FAIT:
        success(_(f"alim_fait_{action}", host=r.host))
    elif r.issue is Issue.COUPEE:
        warn(_("alim_coupee", host=r.host, delai=delai))
    elif r.issue is Issue.DEJA:
        info(_(f"alim_deja_{action}", host=r.host))
    elif r.issue is Issue.IGNOREE:
        info(_("alim_ignoree_pause", host=r.host))
    elif r.delai_depasse:
        error(_("alim_echec_delai", host=r.host, delai=delai))
    else:
        error(_("alim_echec", host=r.host, cause=r.cause or "?"))


def _piloter(
    ctx: typer.Context,
    action: Action,
    lab_home: Path | None,
    host: list[str] | None,
    *,
    tout: bool,
    force: bool = False,
    delai: int = alimentation.DELAI_ARRET,
) -> None:
    root = _root(lab_home)
    repo_meta = _read_repo(root)
    if repo_meta is None:
        error(_("provision_no_meta", root=root))
        raise typer.Exit(ExitCode.ECHEC)
    if not repo_meta.infra.hosts:
        info(_("status_no_hosts"))
        return

    provider = _require_provider(repo_meta)
    if provider not in alimentation.PROVIDERS:
        error(_("alim_provider_non_pris_en_charge", provider=provider))
        raise typer.Exit(ExitCode.IMPOSSIBLE)

    vises = _hotes_vises(action, host, tout, [h.name for h in repo_meta.infra.hosts])
    ctx.call_on_close(_verrou(root, f"infra {action}").release)
    try:
        cibles = alimentation.machines(repo_meta, provider, vises)
        if not cibles:
            info(_("alim_aucune_machine", repo=repo_meta.id))
            return
        info(_(f"alim_debut_{action}", count=len(cibles), provider=provider))
        resultats = alimentation.appliquer(action, provider, cibles, force=force, delai=delai)
    except ProviderSansAlimentation:
        error(_("alim_provider_non_pris_en_charge", provider=provider))
        raise typer.Exit(ExitCode.IMPOSSIBLE) from None
    except CommandError as exc:
        error(_("alim_hyperviseur_injoignable", provider=provider, cause=str(exc)))
        raise typer.Exit(ExitCode.ECHEC) from None

    _conclure(action, resultats, force=force, delai=delai)


def _hotes_vises(
    action: Action, host: list[str] | None, tout: bool, declares: list[str]
) -> list[str] | None:
    """Les FQDN visés, ``None`` pour tous. Sort en 1 sur une demande mal formée."""
    # Arrêter des machines ne se fait pas par défaut : on les nomme, ou on
    # demande --all. Une commande nue qui éteindrait tout le parc surprendrait.
    if bool(host) == tout:
        error(_("alim_cible_requise" if not tout else "alim_cible_ambigue", action=action))
        raise typer.Exit(ExitCode.ECHEC)
    if not host:
        return None
    vises, inconnus = alimentation.resoudre_hotes(host, declares)
    if inconnus:
        error(_("alim_hote_inconnu", hosts=", ".join(inconnus), declared=", ".join(declares)))
        raise typer.Exit(ExitCode.ECHEC)
    return vises


def _conclure(action: Action, resultats: list[Resultat], *, force: bool, delai: int) -> None:
    for r in resultats:
        _afficher(action, r, delai)
    if any(r.issue is Issue.ECHEC for r in resultats):
        if action == "stop" and not force:
            info(_("alim_conseil_force"))
        raise typer.Exit(ExitCode.ECHEC)
    # Le conseil suit un changement : après un `pause` qui n'a rien gelé,
    # « la mémoire reste occupée » serait faux.
    if any(r.issue in (Issue.FAIT, Issue.COUPEE) for r in resultats):
        info(_(f"alim_conseil_{action}"))


@infra_app.command("stop", help=_("cmd_infra_stop_help"))
def infra_stop(
    ctx: typer.Context,
    host: HostOption = None,
    tout: AllOption = False,
    force: Annotated[bool, typer.Option("--force", help=_("opt_alim_force"))] = False,
    timeout: Annotated[int, typer.Option(
        "--timeout", min=1, help=_("opt_alim_timeout"),
    )] = alimentation.DELAI_ARRET,
    lab_home: LabHomeOption = None,
) -> None:
    """Arrête proprement les machines du catalogue, disques gardés."""
    _piloter(ctx, "stop", lab_home, host, tout=tout, force=force, delai=timeout)


@infra_app.command("pause", help=_("cmd_infra_pause_help"))
def infra_pause(
    ctx: typer.Context,
    host: HostOption = None,
    tout: AllOption = False,
    lab_home: LabHomeOption = None,
) -> None:
    """Gèle les machines du catalogue : le CPU est rendu, la mémoire non."""
    _piloter(ctx, "pause", lab_home, host, tout=tout)


@infra_app.command("start", help=_("cmd_infra_start_help"))
def infra_start(
    ctx: typer.Context,
    host: HostOption = None,
    tout: AllOption = False,
    lab_home: LabHomeOption = None,
) -> None:
    """Relance les machines arrêtées et reprend les machines gelées."""
    _piloter(ctx, "start", lab_home, host, tout=tout)
