"""``dsoxlab vm`` : une VM en une commande, sans meta.yml (issue #401).

    dsoxlab vm create essai --distro debian13 --ram 4096
    dsoxlab vm ssh essai
    dsoxlab vm list
    dsoxlab vm destroy essai

Ces commandes ne réimplémentent rien. ``create`` écrit le ``meta.yml`` qu'on
aurait écrit à la main (``services/vm.py``), crée la clé, puis appelle le corps
de ``provision`` sur ce dossier ; ``ssh`` et ``destroy`` appellent les
commandes du même nom avec ce dossier comme ``--lab-home``. Une VM créée ainsi
se comporte donc exactement comme une stack ``docs/infra-only``, et une
correction de ``provision`` lui profite sans rien toucher ici.
"""

from __future__ import annotations

import shutil
from pathlib import Path
from typing import Annotated

import typer
from rich.table import Table

from ..i18n import _
from ..reporting import console, error, info, success
from ..services import vm as vms
from ._commun import _verrou
from ._socle import vm_app


def _dossier_existant(nom: str) -> Path:
    try:
        racine = vms.dossier(nom)
    except vms.NomRefuse:
        error(_("vm_nom_refuse", nom=nom))
        raise typer.Exit(2) from None
    if not (racine / "meta.yml").is_file():
        error(_("vm_inconnue", nom=nom))
        connues = [v.nom for v in vms.lister()]
        if connues:
            info(_("vm_connues", noms=", ".join(connues)))
        raise typer.Exit(1)
    return racine


@vm_app.command("create", help=_("cmd_vm_create_help"))
def create(
    ctx: typer.Context,
    nom: Annotated[str, typer.Argument(help=_("arg_vm_nom"))],
    distro: Annotated[str, typer.Option("--distro", help=_("opt_vm_distro"))] = "ubuntu24",
    ram: Annotated[int, typer.Option("--ram", min=512, help=_("opt_vm_ram"))] = 2048,
    cpu: Annotated[int, typer.Option("--cpu", min=1, help=_("opt_vm_cpu"))] = 2,
    disk: Annotated[int, typer.Option("--disk", min=5, help=_("opt_vm_disk"))] = 20,
    extra_disk: Annotated[int, typer.Option(
        "--extra-disk", min=0, help=_("opt_vm_extra_disk"))] = 0,
    provider: Annotated[str | None, typer.Option(
        "--provider", help=_("opt_vm_provider"))] = None,
) -> None:
    from ..services.doctor_controles.catalogue import creer_cle_ssh
    from .infrastructure import provisionner

    try:
        vms.verifier_nom(nom)
    except vms.NomRefuse:
        error(_("vm_nom_refuse", nom=nom))
        raise typer.Exit(2) from None
    if distro not in vms.DISTROS:
        error(_("vm_distro_inconnue", distro=distro, distros=", ".join(vms.DISTROS)))
        raise typer.Exit(2)
    choisi = provider or vms.provider_par_defaut()
    if choisi is None:
        error(_("vm_aucun_hyperviseur"))
        info(_("vm_aucun_hyperviseur_suite"))
        raise typer.Exit(1)
    if choisi not in vms.PROVIDERS:
        error(_("vm_provider_inconnu", provider=choisi, providers=", ".join(vms.PROVIDERS)))
        raise typer.Exit(2)

    racine = vms.dossier(nom)
    if racine.exists():
        error(_("vm_existe_deja", nom=nom, dossier=racine))
        info(_("vm_existe_deja_suite", nom=nom))
        raise typer.Exit(1)
    if vms.machine_existe(nom, choisi):
        error(_("vm_machine_deja_la", machine=vms.nom_de_machine(nom, choisi), provider=choisi))
        raise typer.Exit(1)

    try:
        cidr = vms.choisir_cidr(vms.reseaux_occupes())
    except vms.AucunSousReseauLibre:
        error(_("vm_aucun_sous_reseau"))
        raise typer.Exit(1) from None

    demande = vms.DemandeVM(nom=nom, distro=distro, ram_mb=ram, vcpu=cpu, disk_gb=disk,
                            extra_disk_gb=extra_disk, provider=choisi)
    racine = vms.ecrire(demande, cidr)
    sortie_cle = creer_cle_ssh(racine)
    if sortie_cle is not None:
        error(_("vm_cle_echouee", sortie=sortie_cle))
        raise typer.Exit(1)
    info(_("vm_creation", nom=nom, distro=distro, ram=ram, cpu=cpu, disk=disk,
           provider=choisi, cidr=cidr))

    ctx.call_on_close(_verrou(racine, "provision").release)
    try:
        provisionner(racine)
    except typer.Exit as sortie:
        if sortie.exit_code:
            # Des ressources ont peut-être été créées avant l'échec : la voie
            # de sortie se nomme ici, sans quoi le dossier resterait sans que
            # l'utilisateur sache quoi en faire.
            info(_("vm_echec_suite", nom=nom))
        raise
    success(_("vm_prete", nom=nom, ip=vms.adresse(str(cidr))))
    info(_("vm_prete_suite", nom=nom, fqdn=vms.fqdn(nom)))


@vm_app.command("ssh", help=_("cmd_vm_ssh_help"))
def ssh(nom: Annotated[str, typer.Argument(help=_("arg_vm_nom"))]) -> None:
    from .infrastructure import ssh_cmd

    racine = _dossier_existant(nom)
    ssh_cmd(host=vms.fqdn(nom), lab_home=racine)


@vm_app.command("list", help=_("cmd_vm_list_help"))
def list_cmd() -> None:
    connues = vms.lister()
    if not connues:
        info(_("vm_aucune"))
        return
    table = Table(title=_("vm_titre_liste"))
    for colonne in ("vm_col_nom", "vm_col_provider", "vm_col_distro", "vm_col_taille",
                    "vm_col_adresse"):
        table.add_column(_(colonne))
    for v in connues:
        table.add_row(
            v.nom, v.provider, v.distro,
            _("vm_taille", ram=v.ram_mb, cpu=v.vcpu, disk=v.disk_gb),
            vms.adresse(v.cidr),
        )
    console.print(table)


@vm_app.command("destroy", help=_("cmd_vm_destroy_help"))
def destroy(
    ctx: typer.Context,
    nom: Annotated[str, typer.Argument(help=_("arg_vm_nom"))],
    yes: Annotated[bool, typer.Option("--yes", "-y", help=_("opt_yes"))] = False,
) -> None:
    from ..infra.inventory import _xdg_cache_home
    from ..infra.terraform import _xdg_state_home
    from .destruction import destroy as detruire

    racine = _dossier_existant(nom)
    repo_id = f"vm-{nom}"

    def _effacer_les_traces() -> None:
        # Après la libération du verrou que `destroy` prend sur ce dépôt :
        # Click referme ses callbacks dans l'ordre inverse, et celui-ci est
        # inscrit AVANT l'appel, donc il passe en dernier. Effacer le dossier
        # d'état sous un verrou tenu, c'est la course que `RepoLock` décrit.
        for chemin in (racine, _xdg_state_home() / "dsoxlab" / repo_id,
                       _xdg_cache_home() / "dsoxlab" / repo_id):
            shutil.rmtree(chemin, ignore_errors=True)
        success(_("vm_detruite", nom=nom))

    termine = False

    def _si_termine() -> None:
        if termine:
            _effacer_les_traces()

    ctx.call_on_close(_si_termine)
    detruire(ctx, host=None, optional_hosts=False, yes=yes, lab_home=racine)
    # Arrivé ici, `destroy` n'a pas levé : les machines, le réseau et le
    # fragment SSH sont retirés, et les orphelins ont été traités (codes 5 et 6
    # sinon). Seul ce cas efface le dossier, qui reste la seule poignée sur
    # une VM qu'un échec aurait laissée debout.
    termine = True
