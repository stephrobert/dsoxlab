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

from ..i18n import _
from ..interrupt import (
    Interrupted,
    Stage,
    interruptible,
)
from ..reporting import (
    console,
    error,
    info,
    success,
    warn,
)
from ._barres import (
    _run_terraform_init_with_spinner,
    _run_terraform_with_progress,
)
from ._commun import (
    LabHomeOption,
    _interrompu,
    _read_repo,
    _require_provider,
    _root,
    _verrou,
)
from ._socle import app
from ._validation import _undefine_command

logger = logging.getLogger(__name__)



@app.command("provision", help=_("cmd_provision_help"))
def provision(
    ctx: typer.Context,
    host: Annotated[list[str] | None, typer.Option(
        "--host",
        help=_("opt_provision_host"),
    )] = None,
    lab_home: LabHomeOption = None,
) -> None:
    """Lance terraform apply sur le provider courant avec progress bar."""
    from ..infra import terraform as tf
    from ..infra.terraform import ProviderNotImplemented, TerraformNotInstalled, host_targets

    root = _root(lab_home)
    # Le verrou est pris avant même de lire le contrat : ce qui suit interroge
    # l'hyperviseur, puis écrit le state Terraform. Un `destroy` lancé dans un
    # autre terminal pendant le scan des machines orphelines rendrait ce scan
    # faux au moment où on s'en sert.
    ctx.call_on_close(_verrou(root, "provision").release)
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

    # Garde-fou « machines fantômes » : un provisionnement interrompu après la
    # définition d'un domaine le laisse sur l'hyperviseur sans jamais l'inscrire
    # au state. Terraform ne le voit donc pas, et tout apply suivant meurt sur
    # « domain already exists », une phrase qui ne dit pas quoi faire. On nomme
    # les machines et la commande qui les retire, avant de perdre une minute
    # d'init et d'apply.
    scan = tf.find_orphan_domains(repo_meta)
    if scan.reason:
        warn(_("orphan_check_skipped", error=scan.reason))
    if scan.orphans:
        error(_("provision_orphan_domains", hosts=", ".join(sorted(scan.orphans))))
        info(_("provision_orphan_fix", cmd=_undefine_command(scan.orphans)))
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
                error(_("host_unknown", fqdn=fqdn, known=", ".join(sorted(known))))
                raise typer.Exit(1)
            try:
                targets.extend(host_targets(provider, fqdn))
            except NotImplementedError as exc:
                error(str(exc))
                raise typer.Exit(2) from None
        info(_("terraform_target", hosts=", ".join(host), count=len(targets)))

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
    except Interrupted as exc:
        # AVANT le `except Exception` : une interruption n'est pas un échec de
        # provisionnement, et sortir en 4 avec « provision failed » ferait
        # chercher une panne là où l'apprenant a simplement appuyé sur Ctrl-C.
        _interrompu(exc, "dsoxlab provision")
    except ProviderNotImplemented as exc:
        error(str(exc))
        raise typer.Exit(2) from None
    except TerraformNotInstalled as exc:
        error(str(exc))
        raise typer.Exit(3) from None
    except Exception as exc:  # noqa: BLE001 — message utilisateur direct
        error(_("provision_failed", error=str(exc)))
        # Terraform est exact mais opaque pour qui découvre l'outil. Quand la
        # cause est connue et le correctif tient en une ligne, on les donne
        # plutôt que de laisser l'apprenant chercher : c'est là qu'il est
        # bloqué, et c'est le seul moment où l'on peut l'affirmer sans risque
        # de fausse alerte.
        from ..services.doctor import explique_echec_provision

        connu = explique_echec_provision(str(exc))
        if connu is not None:
            explication, commande = connu
            info(explication)
            info(f"  {commande}")
        raise typer.Exit(4) from None

    # Un bail DHCP refusé pendant l'apply se dit ici, à l'écran : confiné au
    # journal, l'hôte échouerait plus tard en « injoignable » sans que rien ne
    # relie l'échec à sa cause.
    for message in result.warnings:
        warn(message)

    # Déclaré ici, avant tout branchement : quand il n'y a aucun hôte à
    # attendre, le bloc plus bas n'est pas entré, et la boucle d'affichage
    # doit quand même avoir une liste à parcourir.
    avertissements_cloud_init: list[str] = []

    # Étape 3 : attendre que les VMs soient réellement joignables (sshd +
    # compte student + cloud-init terminé). Sans ça, le premier `dsoxlab run`
    # échoue en « unreachable » car la VM boote encore.
    from ..infra.inventory import (
        EXIT_HOTES_INJOIGNABLES,
        HostReadyTimeout,
        wait_for_hosts_ready,
    )

    attente_depassee = False

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
                with interruptible(Stage.HOSTS_WAIT):
                    # Les hôtes sont joignables, mais leur cloud-init a
                    # peut-être mal fini : sans ces avertissements, les labs
                    # échoueraient plus tard sur des paquets absents, sans que
                    # rien ne relie l'échec au provisionnement.
                    avertissements_cloud_init = wait_for_hosts_ready(
                        repo_meta, ready_hosts, on_attempt=_on_attempt
                    )
            except HostReadyTimeout as exc:
                progress.stop()
                warn(_("provision_ssh_timeout", error=str(exc)))
                # Retenu pour la fin : le fragment SSH et les autres gestes qui
                # suivent restent utiles, mais la commande ne doit pas conclure
                # au succès. Annoncer « ✔ N hôtes provisionnés » puis sortir en
                # 0 rendait l'échec invisible à tout script — et le `run`
                # suivant échouait en « unreachable » sans lien avec la cause.
                attente_depassee = True
            except Interrupted as exc:
                # L'infrastructure existe déjà : c'est l'attente qui a été
                # coupée, pas la création. Rejouer `provision` est idempotent
                # et reprend exactement ici.
                progress.stop()
                _interrompu(exc, "dsoxlab provision")

    # Les hôtes répondent, mais leur configuration a peut-être mal fini. Le dire
    # ici, à l'écran, et non dans un journal : c'est la seule occasion de relier
    # un paquet absent au provisionnement qui n'a pas pu l'installer.
    for message in avertissements_cloud_init:
        warn(message)

    # Le fragment SSH, écrit à CHAQUE provision et non seulement quand des
    # machines viennent d'être créées : relancer un provision sur une infra
    # déjà en place laissait sinon l'apprenant sans fragment, alors que c'est
    # le moment où il en a besoin. Il doit refléter l'état courant, pas le
    # delta du dernier terraform apply.
    from ..infra.inventory import (
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

    if attente_depassee:
        error(_("provision_incomplet"))
        info(_("provision_incomplet_suite"))
        raise typer.Exit(EXIT_HOTES_INJOIGNABLES)

    success(_("provision_done", count=len(result.hosts)))
    for fqdn, ip in sorted(result.hosts.items()):
        info(f"  {fqdn} → {ip}")


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
    from ..infra.inventory import bastion_info, build_inventory, read_terraform_outputs

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
