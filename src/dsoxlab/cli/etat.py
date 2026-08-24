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
import subprocess
from typing import Annotated, Any

import typer

from ..config import (
    read_context,
)
from ..i18n import _
from ..infra import libvirt
from ..reporting import (
    error,
    info,
    machine,
    success,
    warn,
)
from ..services import (
    host_diagnosis,
)
from ..utils.shell import CommandError
from ._commun import (
    LabHomeOption,
    _lab,
    _lang,
    _read_repo,
    _require_provider,
    _root,
)
from ._socle import app, infra_app
from ._validation import _diagnostic_message

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
    """Vérifie la connectivité SSH des hosts du meta.yml."""
    from ..infra.inventory import build_inventory, read_terraform_outputs

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

    from ..infra.inventory import bastion_info

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
    from ..infra.inventory import write_user_ssh_config

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

    # ── Interrogation de l'hyperviseur ───────────────────────────────────────
    # Elle est PARESSEUSE : tant que tout répond, il n'y a rien à diagnostiquer
    # et rien à demander. Elle n'a lieu qu'au premier hôte muet, et une seule
    # fois pour toute la commande.
    interrogeable = libvirt.supports_domain_state(provider)
    domaines_connus: list[str] | None = None
    hyperviseur_tente = False
    hyperviseur_erreur: str | None = None

    def _etat_domaine(fqdn: str) -> libvirt.DomainStatus | None:
        """Ce que l'hyperviseur dit de cet hôte, ou ``None`` s'il ne dit rien.

        ``None`` signifie « je n'ai pas pu regarder », jamais « rien n'existe » :
        le diagnostic retombe alors sur ce que SSH sait, sans jamais conclure à
        une machine absente.
        """
        nonlocal domaines_connus, hyperviseur_tente, hyperviseur_erreur
        if not interrogeable:
            return None
        if not hyperviseur_tente:
            hyperviseur_tente = True
            try:
                domaines_connus = libvirt.list_domains()
            except CommandError as exc:
                hyperviseur_erreur = exc.result.stderr.strip() or str(exc)
        if domaines_connus is None:
            return None
        try:
            return libvirt.inspect_host(fqdn, known=domaines_connus)
        except CommandError as exc:
            logger.debug("libvirt state unavailable for %s: %s", fqdn, exc)
            return None

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
        # LC_ALL=C : la raison de l'échec vient de ``strerror``, que la libc
        # traduit. Sans ce verrou, « No route to host » devient une phrase
        # différente sur chaque poste, et le diagnostic ne reconnaîtrait plus
        # rien de ce que ssh lui dit.
        # check=False : l'échec de ce ssh EST la mesure. Un hôte injoignable
        # est un résultat à rapporter, pas un incident qui arrête le tour des
        # autres hôtes.
        result = subprocess.run(
            cmd, capture_output=True, timeout=15,
            env={**os.environ, "LC_ALL": "C"}, check=False,
        )
        joignable = result.returncode == 0
        raison = None
        if not joignable:
            stderr_tail = result.stderr.decode(errors="replace").strip().splitlines()[-1:]
            raison = stderr_tail[0] if stderr_tail else "timeout"
        etat = None if joignable else _etat_domaine(fqdn)
        hotes.append({
            "fqdn": fqdn,
            "ip": ip,
            "reachable": joignable,
            "reason": raison,
            "domain": etat.domain if etat else None,
            "domain_state": etat.state if etat else None,
            "cause": host_diagnosis.diagnose(
                reachable=joignable, reason=raison or "", status=etat
            ),
        })
        if as_json:
            ok_count += 1 if joignable else 0
            continue
        if joignable:
            # `success` et `error` posent déjà leur propre marqueur : en
            # rajouter un dans la chaîne donnait « ✘   ✘ hote.lab », que
            # l'utilisateur lit comme un défaut de rendu.
            success(f"  {fqdn} ({ip})")
            ok_count += 1
        else:
            error(f"  {fqdn} ({ip}) : {raison}")

    if as_json:
        machine.emit({
            "provider": provider,
            # Un consommateur doit pouvoir distinguer « aucun domaine » d'un
            # hyperviseur qui n'a rien répondu : sans ce bloc, les deux se
            # ressembleraient à des `domain_state: null`.
            "hypervisor": {
                "queryable": interrogeable and hyperviseur_erreur is None,
                "error": hyperviseur_erreur,
            },
            "hosts": hotes,
            "summary": {"reachable": ok_count, "total": len(hosts_dict)},
        })
        if ok_count != len(hosts_dict):
            raise typer.Exit(1)
        return
    if ok_count == len(hosts_dict):
        success(_("status_all_ok", count=ok_count))
        return

    error(_("status_partial", ok=ok_count, total=len(hosts_dict), provider=provider))
    # Dire pourquoi le diagnostic est limité, plutôt que de laisser croire que
    # l'outil a regardé la machine alors qu'il n'a pu regarder que le réseau.
    if not interrogeable:
        warn(_("status_provider_not_inspectable", provider=provider))
    elif hyperviseur_erreur is not None:
        warn(_("status_hypervisor_unavailable", error=hyperviseur_erreur))
    for hote in hotes:
        if hote["reachable"]:
            continue
        info(f"  {hote['fqdn']} — {_diagnostic_message(hote)}")
    raise typer.Exit(1)
