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

from ..i18n import _
from ..infra import libvirt
from ..interrupt import (
    Interrupted,
)
from ..models import (
    RepoMetadata,
)
from ..reporting import (
    error,
    info,
    success,
    warn,
)
from ..utils.shell import CommandError
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
    _undefine_command,
    _verrou,
)
from ._socle import app

logger = logging.getLogger(__name__)



@app.command("destroy", help=_("cmd_destroy_help"))
def destroy(
    ctx: typer.Context,
    host: Annotated[list[str] | None, typer.Option(
        "--host",
        help=_("opt_destroy_host"),
    )] = None,
    yes: Annotated[bool, typer.Option(
        "--yes", "-y",
        help=_("opt_yes"),
    )] = False,
    lab_home: LabHomeOption = None,
) -> None:
    """Lance terraform destroy sur le provider courant avec progress bar."""
    from ..infra import terraform as tf
    from ..infra.terraform import ProviderNotImplemented, TerraformNotInstalled, host_targets

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
                error(_("host_unknown", fqdn=fqdn, known=", ".join(sorted(known))))
                raise typer.Exit(1)
            try:
                targets.extend(host_targets(provider, fqdn))
            except NotImplementedError as exc:
                error(str(exc))
                raise typer.Exit(2) from None
        info(_("terraform_target", hosts=", ".join(host), count=len(targets)))
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

    # Après la confirmation : tenir le verrou pendant l'attente d'une réponse
    # au clavier bloquerait l'autre terminal sans rien protéger.
    ctx.call_on_close(_verrou(root, "destroy").release)
    info(_("destroy_starting", provider=provider))
    _purge_snapshots_before_destroy(repo_meta)
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
    except Interrupted as exc:
        # Avant le `except Exception`, même raison qu'au provision : Terraform
        # a écrit son state, ce qui reste debout est connu, et rejouer suffit.
        _interrompu(exc, "dsoxlab destroy")
    except ProviderNotImplemented as exc:
        error(str(exc))
        raise typer.Exit(2) from None
    except TerraformNotInstalled as exc:
        error(str(exc))
        raise typer.Exit(3) from None
    except Exception as exc:  # noqa: BLE001
        error(_("destroy_failed", error=str(exc)))
        raise typer.Exit(4) from None

    # Terraform ne détruit que ce qu'il connaît. Un domaine défini puis jamais
    # inscrit au state lui est invisible : il annonçait donc « infrastructure
    # détruite » et sortait en 0 en laissant les machines debout, ce qui est le
    # contraire de ce que la commande promet. On regarde l'hyperviseur.
    if not _handle_orphans_after_destroy(repo_meta, assume_yes=yes):
        raise typer.Exit(6)

    # Le fragment SSH pointe désormais des machines mortes : le laisser
    # enverrait l'apprenant vers des adresses recyclées, ce qui est pire que
    # pas de configuration du tout.
    from ..infra.inventory import remove_user_ssh_config

    if remove_user_ssh_config(repo_meta):
        info(_("ssh_fragment_removed", repo=repo_meta.id))

    success(_("destroy_done"))


def _purge_snapshots_before_destroy(repo_meta: RepoMetadata) -> None:
    """Retire les points de reprise **avant** que Terraform ne passe.

    Un snapshot externe laisse un fichier de recouvrement que Terraform ne
    connaît pas : il n'est dans aucun state, et le volume qu'il recouvre est
    supprimé sous lui. Il faut donc le retirer tant que l'hyperviseur sait
    encore qu'il existe — après l'``undefine``, la métadonnée du snapshot a
    disparu avec le domaine, et le fichier devient introuvable autrement qu'à
    la main.

    Best-effort : un dépôt sans labs ``vm``, un provider sans backend snapshot
    ou un hyperviseur muet ne doivent pas empêcher une destruction.
    """
    from ..infra import snapshot as snapshot_infra

    hosts = snapshot_infra.host_names(repo_meta)
    if not hosts:
        return
    try:
        retires = snapshot_infra.purge(repo_meta, hosts)
    except Exception as exc:  # noqa: BLE001 — la destruction prime sur le ménage
        warn(_("snapshot_purge_failed", error=str(exc)))
        return
    if retires:
        info(_("snapshot_purge_done", count=len(retires)))
        for chemin in retires:
            info(f"  − {chemin}")


def _handle_orphans_after_destroy(
    repo_meta: RepoMetadata, *, assume_yes: bool
) -> bool:
    """Retire les machines que Terraform a laissées derrière lui, ou le dit.

    Le retrait est **confirmé**, jamais implicite : rien ne garantit à dsoxlab
    qu'un domaine homonyme d'un ``infra.hosts[].name`` soit bien le sien, et
    une machine dé-définie ne revient pas. ``--yes`` vaut confirmation — c'est
    déjà lui qui a autorisé la destruction de cette infrastructure, et ces
    machines-là en font partie par leur nom.

    Returns:
        ``True`` si l'hyperviseur ne porte plus rien de ce dépôt et que la
        commande peut sortir en succès. ``False`` s'il reste des machines :
        l'appelant doit alors sortir en code non nul, faute de quoi il
        annoncerait une destruction qui n'a pas eu lieu.
    """
    from ..infra import terraform as tf

    scan = tf.find_orphan_domains(repo_meta)
    if scan.reason:
        warn(_("orphan_check_skipped", error=scan.reason))
    if not scan.orphans:
        return True

    noms = sorted(scan.orphans)
    warn(_("destroy_orphan_domains", hosts=", ".join(noms)))
    if not assume_yes and not typer.confirm(_("confirm_destroy_orphans")):
        info(_("destroy_orphan_kept", cmd=_undefine_command(scan.orphans)))
        return False

    restants: dict[str, str] = {}
    for fqdn in noms:
        domaine = scan.orphans[fqdn]
        try:
            libvirt.remove_domain(domaine)
        except CommandError as exc:
            restants[fqdn] = domaine
            error(_("destroy_orphan_failed", host=domaine,
                    error=exc.result.stderr.strip() or str(exc)))
    if restants:
        info(_("destroy_orphan_kept", cmd=_undefine_command(restants)))
        return False
    success(_("destroy_orphan_removed", hosts=", ".join(noms)))
    return True
