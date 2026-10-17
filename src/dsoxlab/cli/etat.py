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
from ..exit_codes import ExitCode
from ..i18n import _
from ..reporting import (
    error,
    info,
    machine,
    print_infra_status,
    warn,
)
from ._commun import (
    LabHomeOption,
    _lab,
    _lang,
    _read_repo,
    _require_provider,
    _root,
)
from ._socle import app, infra_app

logger = logging.getLogger(__name__)



@app.command("status", help=_("cmd_lab_status_help"))
def status(
    lab_id: Annotated[str | None, typer.Argument(help=_("arg_lab_id_optionnel"))] = None,
    lab_home: LabHomeOption = None,
    as_json: Annotated[bool, typer.Option("--json", help=_("opt_json"))] = False,
) -> None:
    """Où en est le lab actif, ou celui qu'on nomme."""
    from ..services.lab_state import calculer

    root = _root(lab_home)
    lang = _lang(root)
    ctx = read_context(root)
    effective_id = lab_id or ctx.active_lab

    if not effective_id:
        # Sans lab actif, dire quoi faire — et nommer la commande qui portait
        # ce nom jusqu'en 0.1.67, pour qui la cherche encore ici.
        if as_json:
            machine.emit({"schema": 1, "lab": None, "state": None})
            return
        info(_("status_aucun_lab_actif"))
        info(_("status_voir_infra"))
        return

    try:
        lab = _lab(root, effective_id, lang)
    except ValueError as exc:
        error(str(exc))
        raise typer.Exit(1) from None

    repo_meta = _read_repo(root)
    repo_id = repo_meta.id if repo_meta else root.name
    etat = calculer(root, lab, repo_id)

    if as_json:
        machine.emit({
            "schema": 1,
            "lab": lab.id,
            "state": etat.state,
            "label": etat.label,
            "detail": etat.detail,
            "best_score": etat.best_score,
            "max_score": etat.max_score,
        })
        return

    from ..reporting.console import print_lab_state

    print_lab_state(etat)


@infra_app.command("status", help=_("cmd_status_help"))
def infra_status(
    lab_home: LabHomeOption = None,
    as_json: Annotated[bool, typer.Option("--json", help=_("opt_json"))] = False,
) -> None:
    """L'état de l'infrastructure : qui répond, et pourquoi les autres non.

    Cette fonction portait 205 lignes et une complexité cognitive de 61 : elle
    construisait l'inventaire, sondait chaque hôte, interrogeait l'hyperviseur à
    travers trois variables ``nonlocal``, diagnostiquait, puis rendait deux
    sorties. La mesure vit désormais dans ``services.infra_state_service``, et
    la phrase de diagnostic dans ``reporting`` ; il ne reste ici que la
    préparation et le choix de la sortie.
    """
    from ..infra.inventory import (
        bastion_info,
        build_inventory,
        read_terraform_outputs,
        write_user_ssh_config,
    )
    from ..services.infra_state_service import (
        document,
        document_sans_infrastructure,
        mesurer,
    )

    root = _root(lab_home)
    repo_meta = _read_repo(root)
    if repo_meta is None:
        error(_("provision_no_meta", root=root))
        raise typer.Exit(ExitCode.ECHEC)

    if not repo_meta.infra.hosts:
        if as_json:
            machine.emit(document_sans_infrastructure())
            return
        info(_("status_no_hosts"))
        return

    provider = _require_provider(repo_meta)
    sorties_tf = read_terraform_outputs(repo_meta)
    inventaire = build_inventory(repo_meta, terraform_outputs=sorties_tf)
    hotes = inventaire["all"]["children"]["labenv"]["hosts"]
    bastion = bastion_info(sorties_tf, repo_meta=repo_meta)

    cle_ssh = repo_meta.path / "ssh" / "id_ed25519"
    if not cle_ssh.is_file():
        error(_("status_no_key", path=cle_ssh))
        raise typer.Exit(ExitCode.ECHEC)

    # On rafraîchit le fragment SSH au passage : `provision` ne peut pas
    # toujours être rejoué (le provider libvirt refuse certaines mises à jour
    # avec « Update Not Supported »), et l'apprenant se retrouverait alors sans
    # moyen de régénérer sa configuration. `status` est la commande qu'on lance
    # justement quand on doute de l'état de l'infra.
    try:
        write_user_ssh_config(inventaire, repo_meta)
    except OSError as exc:
        if not as_json:
            warn(_("ssh_fragment_failed", error=str(exc)))

    if not as_json:
        # `not as_json` : la première règle de la sortie machine est que rien
        # d'autre que le document n'atteigne la sortie standard.
        info(_("status_checking", count=len(hotes)))
        if bastion:
            info(_("status_via_bastion",
                   bastion=bastion["fqdn"] or bastion["public_ip"]))

    etat = mesurer(repo_meta, hotes, cle_ssh, provider=provider, bastion=bastion)

    if as_json:
        machine.emit(document(etat))
        if not etat.tout_repond:
            raise typer.Exit(ExitCode.ECHEC)
        return

    print_infra_status(etat)
    if not etat.tout_repond:
        raise typer.Exit(ExitCode.ECHEC)
