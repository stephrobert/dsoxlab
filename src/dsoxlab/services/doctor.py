"""Diagnostic de l'environnement — la matière de ``dsoxlab doctor``.

Deux principes gouvernent ce module, tous deux issus du premier lancement
de l'outil par un apprenant, qui s'est retrouvé devant trois lignes rouges
sans savoir laquelle l'empêchait de travailler :

1. **Un check doit refléter ce que fait la commande qu'il prétend couvrir.**
   ``doctor`` déclarait ``pytest`` introuvable en cherchant un binaire dans
   le PATH, alors que ``check`` lance les tests par
   :func:`~dsoxlab.services.lab_service.resolve_pytest_cmd`, c'est-à-dire
   d'abord l'environnement de l'outil, où pytest est une dépendance
   déclarée. Le diagnostic était rouge, la commande fonctionnait, et la
   remédiation proposée faisait installer à l'apprenant ce qu'il possédait
   déjà. Les deux chemins partagent désormais la même résolution.

2. **Un check n'est bloquant que s'il l'est pour ce dépôt-ci.** Un dépôt
   sans lab ``vm`` (``terraform-training`` n'a même pas de bloc ``infra:``)
   n'a besoin d'aucun hyperviseur ; un dépôt qui a choisi ``kvm`` n'a pas
   besoin d'incus. Ces composants restent affichés, mais dans un tableau
   informatif qui ne montre pas de rouge et que ``--fix`` ne touche pas.

Le module reste agnostique du domaine : il ne connaît que le contrat
(``meta.yml`` + ``lab.yaml``), jamais le sujet des labs.

Depuis l'issue #199, les familles de contrôles vivent dans
``services/doctor_controles/`` (modèle, outillage, kvm, pools, incus,
ressources, réseau, catalogue, conteneurs). Ce module reste le point d'entrée :
il les réexporte, et il garde le **classement requis/informatif** et
``collect_checks``, pour que ce classement ne soit pas dispersé. Les sondes que
les tests remplacent sont lues ici à l'appel, par ``_doctor()``.
"""

from __future__ import annotations

# Ces modules ne servent pas ici : les familles s'en servent. Ils restent des
# attributs de ce point d'entrée parce que les tests y remplacent des fonctions
# (`doctor.shutil.which`, `doctor.subprocess.run`...), ce qui vise le module
# lui-même et atteint donc les familles. Le découpage de l'issue #199 ne devait
# réécrire aucun test.
import os
import platform
import shutil  # noqa: F401
import subprocess  # noqa: F401
from dataclasses import dataclass, replace
from pathlib import Path

from ..discovery.scanner import compter_fichiers_labs
from ..i18n import _
from ..infra import ansible as ansible_infra  # noqa: F401 — voir plus haut
from ..models import LabDefinition, RepoMetadata
from .doctor_controles.catalogue import (
    _VM_RUNTIMES,
    _check_cle_ssh,
    _check_lab_home,
    _check_labs,
    _check_ssh_include,
    uses_vm,
)
from .doctor_controles.conteneurs import (
    _check_docker,
    uses_services,
)
from .doctor_controles.incus import (
    _POOL_INCUS,
    _check_incus,
    _check_incus_pool,
    _current_user,
)
from .doctor_controles.kvm import (
    _CPUINFO,
    _KVM_DEVICE,
    _LIBVIRT_MINIMUM,
    _PROVIDER_IMAGE_ARCHS,
    _SANS_VM,
    _VERSION_COMPILEE,
    _VERSION_UTILISEE,
    Hebergement,
    _check_cpu_arch,
    _check_efi,
    _check_groupes,
    _check_hw_virt,
    _check_kvm,
    _hebergement,
    _sonde_virsh,
    _version_libvirt,
)
from .doctor_controles.modele import (
    EXIT_DOCTOR_INDETERMINE,
    EXIT_DOCTOR_REQUIS_KO,
    STATE_CHOICE_REQUIRED,
    STATE_FAILED,
    STATE_OK,
    STATE_UNKNOWN,
    Check,
    DoctorReport,
    Fix,
    FixKind,
    _check,
    _fix,
    _installer,
)
from .doctor_controles.outillage import (
    _check_ansible,
    _check_collections,
    _check_git,
    _check_iso_tool,
    _check_pytest,
    _check_python,
    _check_shell,
    _check_terraform,
    _check_tf_providers,
    _sonder,
)
from .doctor_controles.pools import (
    _APPARMOR_OVERRIDE,
    _POOL_ABSENT,
    _POOL_INACTIF,
    _check_libvirt_pool,
    _pool_cite,
    _pools_libvirt,
    apparmor_fix_command,
    apparmor_override_absent,
    creer_pool_command,
    creer_pool_fix,
    demarrer_pool_command,
    demarrer_pool_fix,
    explique_echec_provision,
)
from .doctor_controles.remedes import systeme as _systeme
from .doctor_controles.reseau import (
    _DELAI_EGRESS,
    _URL_IMAGE,
    _check_egress,
    _hotes_images,
    _joignable,
)
from .doctor_controles.ressources import (
    _check_bridge_name,
    _check_resources,
    _hotes_a_compter,
    _mem_available_mb,
    _pool_available_gb,
    nom_du_pool,
)
from .lab_service import get_all_labs, resolve_pytest_cmd  # noqa: F401 — voir plus haut

#: Ce que les appelants importent d'ici : cli/, tests/, et les familles
#: elles-mêmes par ``_doctor()``. Rien ne change pour eux (issue #199).
__all__ = [
    "EXIT_DOCTOR_INDETERMINE",
    "EXIT_DOCTOR_REQUIS_KO",
    "STATE_CHOICE_REQUIRED",
    "STATE_FAILED",
    "STATE_OK",
    "STATE_UNKNOWN",
    "_APPARMOR_OVERRIDE",
    "_CPUINFO",
    "_DELAI_EGRESS",
    "_KVM_DEVICE",
    "_LIBVIRT_MINIMUM",
    "_POOL_ABSENT",
    "_POOL_INACTIF",
    "_POOL_INCUS",
    "_PROVIDER_IMAGE_ARCHS",
    "_SANS_VM",
    "_URL_IMAGE",
    "_VERSION_COMPILEE",
    "_VERSION_UTILISEE",
    "_VM_RUNTIMES",
    "Check",
    "DoctorReport",
    "Fix",
    "FixKind",
    "Hebergement",
    "_check",
    "_check_ansible",
    "_check_bridge_name",
    "_check_cle_ssh",
    "_check_collections",
    "_check_cpu_arch",
    "_check_docker",
    "_check_efi",
    "_check_egress",
    "_check_git",
    "_check_groupes",
    "_check_hw_virt",
    "_check_incus",
    "_check_incus_pool",
    "_check_iso_tool",
    "_check_kvm",
    "_check_lab_home",
    "_check_labs",
    "_check_libvirt_pool",
    "_check_pytest",
    "_check_python",
    "_check_resources",
    "_check_shell",
    "_check_ssh_include",
    "_check_terraform",
    "_check_tf_providers",
    "_current_user",
    "_fix",
    "_hebergement",
    "_hotes_a_compter",
    "_hotes_images",
    "_installer",
    "_joignable",
    "_mem_available_mb",
    "_pool_available_gb",
    "_pool_cite",
    "_pools_libvirt",
    "_sonde_virsh",
    "_sonder",
    "_systeme",
    "_version_libvirt",
    "apparmor_fix_command",
    "apparmor_override_absent",
    "creer_pool_command",
    "creer_pool_fix",
    "demarrer_pool_command",
    "demarrer_pool_fix",
    "explique_echec_provision",
    "nom_du_pool",
    "provider_recommande",
    "uses_services",
    "uses_vm",
]

#: Providers packagés qui reposent sur un hyperviseur **local**, donc
#: diagnosticables sur la machine de l'apprenant. ``outscale`` en est
#: absent volontairement : rien à vérifier localement pour un cloud.
_LOCAL_HYPERVISORS = ("kvm", "incus")


def _hypervisor_checks() -> dict[str, Check]:
    return {"kvm": _check_kvm(), "incus": _check_incus()}


def _sort_hypervisors(names: list[str]) -> list[Check]:
    checks = _hypervisor_checks()
    return [checks[n] for n in names if n in checks]


@dataclass(frozen=True)
class _CeQueLeDepotDemande:
    """Les quatre faits dont dépend le classement requis/informatif.

    Aucun ne relève du domaine du dépôt : ce sont des propriétés de son
    contrat. Les rassembler ici évite que chaque phase du diagnostic les
    recalcule, et dit d'un coup sur quoi repose tout le classement.
    """

    root: Path
    repo_meta: RepoMetadata | None
    #: Un hôte déclaré est un engagement : il sera provisionné. Regarder les
    #: seuls labs (issue #230) rangeait terraform et l'hyperviseur en
    #: informatifs sur un dépôt qui ne fait *que* provisionner.
    declare_des_hotes: bool
    needs_vm: bool
    active: str
    candidates: list[str]
    #: Les FQDN sur lesquels porte le contrôle de ressources. ``None`` veut dire
    #: « pas de restriction », donc tout le catalogue : c'est ce que voit le
    #: `doctor` lancé seul. Une liste VIDE veut dire « ce lab ne demande aucun
    #: hôte », donc une demande nulle, et les deux ne se confondent pas — le
    #: défaut d'un `field(default_factory=list)` les confondait, et `doctor`
    #: annonçait « 0 Mo déclarés », vert sur n'importe quelle machine.
    #: `start <lab>` y met les hôtes de son lab (issue #358). C'est le seul fait
    #: d'ici qui vienne de l'APPELANT et non du dépôt.
    hotes_demandes: list[str] | None = None


def _ranger_docker(report: DoctorReport, labs: list[LabDefinition]) -> None:
    """docker dépend de ce que le catalogue déclare, jamais de son domaine.

    Un dépôt sans `runtime.services` n'a aucune raison de voir du rouge pour un
    moteur qu'il n'utilise pas.
    """
    if uses_services(labs):
        report.required.append(_check_docker())
        return
    report.optional.append(_check_docker())
    report.notes.append(_("reason_docker_no_services"))


def _ranger_sortie_reseau(report: DoctorReport, ctx: _CeQueLeDepotDemande) -> None:
    """Le provisionnement télécharge une image puis laisse cloud-init installer
    des paquets : sans accès sortant, l'hôte est déclaré prêt et les labs
    échouent plus tard sur des commandes absentes. Un dépôt entièrement `shell`
    ne provisionne rien, donc n'a pas à en voir du rouge.
    """
    if not ctx.needs_vm:
        report.optional.append(_check_egress())
        report.notes.append(_("reason_egress_sans_vm"))
        return
    report.required.append(_check_egress())
    # Informatif, mais affiché là où on le regarde : c'est la version qui
    # décide du comportement de `provision`, et elle n'était nulle part.
    report.optional.append(_check_tf_providers(ctx.repo_meta))


def provider_recommande(
    candidates: list[str], hypervisors: dict[str, Check] | None = None
) -> str:
    """Le candidat que ce poste peut faire marcher, ou ``""`` s'il n'y en a aucun.

    Rien n'est enregistré : le choix reste une étape du plan, confirmée par
    l'utilisateur (décision 4 du 2026-11-16). L'ordre :

    1. un hyperviseur local déjà opérationnel, dans l'ordre du catalogue. Un
       Incus qui marche prime sur un KVM à installer : avant, KVM était
       recommandé d'office dès que ``/dev/kvm`` existait ;
    2. sinon un hyperviseur local que ce poste peut faire tourner (``/dev/kvm``
       présent, et pour KVM une architecture que ses images servent) : KVM s'il
       en fait partie, c'est le provider que les catalogues éprouvent ; sinon le
       premier du catalogue ;
    3. sinon le premier candidat distant (outscale…) ;
    4. sinon ``""`` : aucun candidat ne marchera ici. Le poste n'a pas de
       virtualisation matérielle (WSL ou VM sans virtualisation imbriquée,
       typiquement) et le catalogue ne déclare aucun provider distant. Avant,
       KVM était proposé quand même, et ``--fix`` l'installait pour rien.

    ``hypervisors`` : les sondes déjà jouées par ``collect_checks``, pour ne pas
    relancer ``virsh`` et ``incus`` une seconde fois.
    """
    locaux = _hyperviseurs_possibles(candidates)
    if locaux:
        sondes = hypervisors if hypervisors is not None else _hypervisor_checks()
        operationnel = next((nom for nom in locaux if _marche(nom, sondes)), None)
        if operationnel:
            return operationnel
        # Rien ne marche encore : KVM s'il est possible, c'est le provider que
        # les catalogues éprouvent ; sinon le premier du catalogue.
        return "kvm" if "kvm" in locaux else locaux[0]
    return next((nom for nom in candidates if nom not in _LOCAL_HYPERVISORS), "")


def _hyperviseurs_possibles(candidates: list[str]) -> list[str]:
    """Les hyperviseurs locaux candidats que ce poste peut faire tourner.

    Aucun sans ``/dev/kvm`` sur Linux. KVM est en plus écarté sur une
    architecture que ses images ne servent pas.
    """
    if platform.system() != "Linux" or not _kvm_present():
        return []
    arch = platform.machine().lower()
    return [
        nom for nom in candidates
        if nom in _LOCAL_HYPERVISORS
        and (nom != "kvm" or arch in _PROVIDER_IMAGE_ARCHS["kvm"])
    ]


def _marche(nom: str, sondes: dict[str, Check]) -> bool:
    """L'hyperviseur répond, et l'utilisateur peut s'en servir.

    Le droit sur /dev/kvm ne compte que pour KVM, que qemu ouvre sous le compte
    de l'utilisateur. Incus l'ouvre par son démon, en root.
    """
    if not sondes[nom].ok:
        return False
    return nom != "kvm" or os.access(_KVM_DEVICE, os.R_OK | os.W_OK)


def _kvm_present() -> bool:
    from .doctor_controles.modele import _doctor

    return bool(_doctor()._KVM_DEVICE.exists())


def _ranger_hyperviseurs(
    report: DoctorReport,
    ctx: _CeQueLeDepotDemande,
    hypervisors: dict[str, Check],
) -> None:
    """Quel hyperviseur bloque ici, et lesquels ne font qu'informer."""
    if not ctx.needs_vm:
        # Catalogue entièrement `shell` : aucun hyperviseur n'est requis, et le
        # dire évite le rouge décourageant du premier lancement.
        report.optional.extend(_sort_hypervisors(list(_LOCAL_HYPERVISORS)))
        report.notes.append(_("doctor_note_no_vm"))
        return

    if ctx.active in hypervisors:
        report.required.append(_check("provider", True, ctx.active))
        report.required.append(hypervisors[ctx.active])
        report.optional.extend(
            _sort_hypervisors([n for n in _LOCAL_HYPERVISORS if n != ctx.active])
        )
        report.notes.append(_("doctor_note_other_providers", provider=ctx.active))
        return

    if ctx.active:
        # Provider distant (outscale…) : rien à vérifier localement.
        report.required.append(_check("provider", True, ctx.active))
        report.optional.extend(_sort_hypervisors(list(_LOCAL_HYPERVISORS)))
        report.notes.append(_("doctor_note_remote_provider", provider=ctx.active))
        return

    # Plusieurs candidats déclarés, aucun choisi. On ne devine pas à la place
    # de l'apprenant : on nomme le choix qui reste à faire.
    #
    # On arrive ici avec `needs_vm` vrai : un hyperviseur EST indispensable.
    # Les checks restent pourtant hors du requis, et c'est délibéré : les y
    # mettre ferait proposer à `--fix` d'installer kvm **et** incus, pour un
    # choix que l'apprenant n'a pas encore fait. C'est le libellé du tableau
    # qui mentait, en annonçant « non requis ici » et « ces composants ne
    # bloquent rien » au-dessus du composant qui bloque 64 labs sur 84.
    #
    # Depuis la refonte du 2026-11-16, le diagnostic ne s'arrête plus là : il
    # prend le provider qu'il recommande, et contrôle tout ce que ce choix
    # demande. Avant, tous les contrôles kvm restaient cachés jusqu'au choix,
    # et l'apprenant découvrait le chemin une commande à la fois. Seul
    # l'hyperviseur recommandé passe en requis : `--fix` n'installe donc pas
    # kvm ET incus.
    recommande = provider_recommande(ctx.candidates, hypervisors)
    report.required.append(_check(
        "provider", False,
        _("detail_provider_unresolved", candidates=", ".join(ctx.candidates) or "?"),
        hint=f"dsoxlab use --provider {recommande}" if recommande else None,
        forced_state=STATE_CHOICE_REQUIRED,
    ))
    report.provider_a_confirmer = True
    if recommande in hypervisors:
        report.required.append(hypervisors[recommande])
        report.optional.extend(
            _sort_hypervisors([n for n in _LOCAL_HYPERVISORS if n != recommande])
        )
        return
    if not recommande:
        # Aucun candidat ne marchera sur ce poste. Le contrôle de
        # virtualisation reste en requis : c'est LUI qui dit pourquoi (poste
        # physique, VM sans virtualisation imbriquée, droit manquant), avec la
        # consigne utile. Sans lui, `doctor` taisait la seule cause qui compte.
        # Pas d'invite à choisir : aucun choix ne marcherait ici.
        report.required.append(_check_hw_virt())
        report.optional.extend(_sort_hypervisors(list(_LOCAL_HYPERVISORS)))
        report.notes.append(_("doctor_note_aucun_provider_compatible"))
        return
    report.optional.extend(_sort_hypervisors(list(_LOCAL_HYPERVISORS)))
    report.optional_title_key = "doctor_choose_title"
    report.optional_hint_key = "doctor_choose_hint"
    report.notes.append(_("doctor_note_provider_unresolved"))


def _ranger_materiel_local(report: DoctorReport, ctx: _CeQueLeDepotDemande) -> None:
    """Prérequis matériels d'un hyperviseur local : virtualisation, architecture,
    ressources, nom du pont.

    Ils ne dépendent d'aucun binaire installé (`/dev/kvm` et `/proc/meminfo` se
    lisent sans virsh), donc ils parlent même quand l'hyperviseur manque :
    c'est une cause DIFFÉRENTE, pas le même rouge répété. Un provider distant
    provisionne ailleurs : rien de tout cela ne concerne alors ce poste.
    """
    report.required.append(_check_hw_virt())
    report.required.append(_check_cpu_arch(ctx.active))
    if ctx.repo_meta is None:
        return
    if ctx.repo_meta.infra.hosts:
        ressources = _check_resources(ctx.repo_meta.infra, ctx.active, ctx.hotes_demandes)
        if ctx.hotes_demandes is None and ressources.state == STATE_FAILED:
            # Tout le catalogue ne tient pas en mémoire : « À savoir », non
            # bloquant (décision 6 du 2026-11-16). Un lab ne monte souvent
            # qu'une machine, et `provision --host` le permet. `start <lab>`,
            # qui passe les hôtes de son lab, garde le contrôle bloquant : là,
            # la mémoire manque pour CE lab.
            premier = ctx.repo_meta.infra.hosts[0].name
            report.a_savoir.append(replace(
                ressources, hint=f"dsoxlab provision --host {premier}", remede=None,
            ))
        else:
            report.required.append(ressources)
    # Le nom du pont ne dépend que du contrat : aucune sonde, donc aucune
    # raison de le taire quand l'hyperviseur manque. Il vaut mieux ici qu'au
    # premier `provision`, où l'échec arrive après le téléchargement de
    # l'image de base (issue #214).
    report.required.append(_check_bridge_name(ctx.repo_meta, ctx.active))


def _ranger_outillage_vm(
    report: DoctorReport,
    ctx: _CeQueLeDepotDemande,
    hypervisors: dict[str, Check],
) -> None:
    """Ce que `provision` et `run` exigent dès qu'un lab a besoin d'une VM.

    `terraform` et `ansible-playbook` manquaient au diagnostic, et leur absence
    ne se manifestait qu'au premier échec, en langage Terraform ou en `rc=127`.
    """
    report.required.append(_check_terraform())
    report.required.append(_check_ansible())
    # Les collections viennent juste après `ansible-playbook` : sans elles, il
    # est là et ne sait pas résoudre les modules que les playbooks appellent.
    report.required.append(_check_collections(ctx.root))
    if ctx.active in _LOCAL_HYPERVISORS:
        _ranger_materiel_local(report, ctx)

    # Ces contrôles-ci portent sur la CONFIGURATION d'un hyperviseur. Quand
    # l'hyperviseur manque, ils ne peuvent pas mesurer : ils restent listés,
    # en attente de l'étape qui l'installe, avec leur commande (refonte du
    # 2026-11-16). Avant, ils disparaissaient, et chaque passage de `doctor`
    # en révélait un de plus.
    if ctx.active == "kvm":
        kvm_ok = hypervisors["kvm"].ok
        report.required.append(_check_groupes(kvm_ok))
        # Même lecture que `_check_resources` et que le template Terraform :
        # une seule fonction la porte, sinon les trois divergent un jour.
        pool = nom_du_pool(ctx.repo_meta.infra) if ctx.repo_meta else "default"
        if kvm_ok:
            report.required.append(_check_libvirt_pool(pool))
        else:
            report.required.append(_check(
                "libvirt_pool", False, _("detail_pool_apres_kvm", pool=pool),
                forced_state=STATE_UNKNOWN, apres="kvm", fix=creer_pool_fix(pool),
            ))
        report.required.append(_check_efi(kvm_ok))
    elif ctx.active == "incus" and hypervisors["incus"].ok:
        # Symétrie avec la branche kvm : elle contrôle son pool de stockage,
        # celle-ci ne contrôlait que l'outil ISO.
        report.required.append(_check_incus_pool())
        report.required.append(_check_iso_tool())
    if ctx.repo_meta is not None and ctx.active in _LOCAL_HYPERVISORS:
        report.required.append(_check_cle_ssh(ctx.root))
        report.required.append(_check_ssh_include())


def _labs_juges(
    labs: list[LabDefinition], lab: LabDefinition | None,
) -> list[LabDefinition]:
    """Les labs dont dépend le classement : celui qu'on joue, ou tous."""
    return labs if lab is None else [lab]


def _exige_des_machines(
    juges: list[LabDefinition], lab: LabDefinition | None, declare_des_hotes: bool,
) -> bool:
    """Un hôte déclaré n'engage que le diagnostic du catalogue entier.

    Pour un lab précis, seul compte son runtime : les hôtes du ``meta.yml`` sont
    ceux des autres labs.
    """
    return uses_vm(juges) or (lab is None and declare_des_hotes)


def collect_checks(
    root: Path, repo_meta: RepoMetadata | None, hosts: list[str] | None = None,
    *, lab: LabDefinition | None = None,
) -> DoctorReport:
    """Construit le diagnostic pour le dépôt de labs situé en ``root``.

    Le classement requis/optionnel dépend de quatre faits du dépôt, et
    d'aucune connaissance de son domaine : a-t-il des labs ``vm``, déclare-t-il
    des hôtes, quel provider est actif, et lesquels déclare-t-il. Ces faits
    sont rassemblés dans :class:`_CeQueLeDepotDemande`, et chaque phase du
    diagnostic les lit plutôt que de les recalculer.

    ``hosts`` restreint le contrôle de ressources à ces FQDN. C'est
    ``start <lab>`` qui le passe, avec les hôtes de ce lab (issue #358) ; le
    ``doctor`` lancé seul ne le passe pas et garde le total du catalogue, qui
    est l'information utile hors d'un lab : « monter tout le catalogue demande
    tant ». Le reste du diagnostic ne dépend pas des hôtes retenus, et n'est
    donc pas restreint.

    ``lab`` restreint le CLASSEMENT à ce lab : ``start <lab>`` le passe. Un lab
    ``shell`` n'exige ni provider, ni clé SSH, ni hyperviseur, même dans un
    catalogue qui a par ailleurs des labs ``vm`` ; un lab sans service n'exige
    pas docker. ``hosts`` ne peut pas le dire : sa liste est vide aussi pour un
    lab ``vm`` dont les machines tournent déjà.
    """
    labs = get_all_labs(root)
    juges = _labs_juges(labs, lab)
    declare_des_hotes = bool(repo_meta and repo_meta.infra.hosts)
    ctx = _CeQueLeDepotDemande(
        root=root,
        repo_meta=repo_meta,
        declare_des_hotes=declare_des_hotes,
        # `terraform-training` est le contre-exemple qui tient cette ligne :
        # aucun bloc `infra:`, tous ses labs `shell`, donc aucun hyperviseur
        # requis. `doctor --strict` y sortait en 0 sur un environnement
        # incapable de monter quoi que ce soit (issue #230).
        needs_vm=_exige_des_machines(juges, lab, declare_des_hotes),
        active=repo_meta.infra.provider if repo_meta else "",
        candidates=list(repo_meta.infra.providers_available) if repo_meta else [],
        hotes_demandes=list(hosts) if hosts is not None else None,
    )
    hypervisors = _hypervisor_checks()

    report = DoctorReport(
        catalogue=repo_meta.id if repo_meta else None,
        nb_labs=len(labs),
        systeme=_systeme().nom,
    )
    report.required.extend([_check_python(), _check_pytest(root), _check_shell()])
    # git sert au parcours d'accueil (`catalog add` clone), quel que soit le
    # domaine du dépôt : il est requis partout.
    report.required.append(_check_git())
    _ranger_docker(report, juges)
    _ranger_sortie_reseau(report, ctx)
    _ranger_hyperviseurs(report, ctx, hypervisors)
    if ctx.needs_vm and not ctx.active and report.provider_a_confirmer:
        ctx = replace(ctx, active=provider_recommande(ctx.candidates, hypervisors))
    # Un catalogue sans machine n'a pas de provider à annoncer.
    report.provider = ctx.active if ctx.needs_vm else ""
    if ctx.needs_vm:
        _ranger_outillage_vm(report, ctx, hypervisors)
    elif repo_meta is None and any(hypervisors[h].ok for h in _LOCAL_HYPERVISORS):
        # Sans catalogue, un hyperviseur qui marche, c'est le poste de `dsoxlab
        # vm` (#401) : `vm create` provisionne par Terraform et écrit un fragment
        # SSH. Sans ces deux contrôles, `doctor --fix` laissait Terraform absent
        # et `ssh <nom>.lab` muet, et `vm create` le découvrait après coup.
        report.required.append(_check_terraform())
        report.required.append(_check_ssh_include())
        # Le démon Incus répond avec le seul paquet `incus`, mais une VM ne
        # démarre pas sans outil ISO : sans ce contrôle, `doctor --fix --all`
        # jugeait Incus vert et ne posait jamais genisoimage (2026-11-19).
        if hypervisors["incus"].ok:
            report.required.append(_check_iso_tool())

    report.required.append(_check_labs(
        root, labs, compter_fichiers_labs(root), infra_declaree=declare_des_hotes,
    ))
    report.required.append(_check_lab_home(root))
    return report
