"""KVM et l'hôte : virsh, la version de libvirt, la virtualisation matérielle, l'architecture.

Extrait de ``services/doctor.py`` (issue #199), sans changement de
comportement. Voir ce module pour les principes du diagnostic.
"""

from __future__ import annotations

import os
import platform
import re
import shutil
from dataclasses import dataclass
from pathlib import Path

from ...i18n import _
from ...infra import libvirt as libvirt_infra
from ...utils.shell import CommandError, CommandResult
from .incus import _current_user
from .modele import STATE_UNKNOWN, Check, FixKind, _check, _doctor, _fix, _installer


def _sonde_virsh(args: list[str], *, delai: int = 5) -> CommandResult | None:
    """Joue une sonde ``virsh`` sur l'URI système, ou rend ``None`` si impossible.

    Le chemin est celui de :func:`~dsoxlab.infra.libvirt.run_virsh` — même URI,
    même détection du préfixe ``sudo -n`` — parce qu'un diagnostic qui
    n'emprunte pas le chemin des commandes qu'il couvre mesure autre chose
    qu'elles. ``check=False`` : un code retour non nul EST une réponse ; seul
    l'appel qui ne peut pas aboutir (binaire absent, timeout) vaut ``None``.
    """
    try:
        result = libvirt_infra.run_virsh(args, check=False, timeout=delai)
    except CommandError:
        return None
    return result


#: Version minimale de libvirt que dsoxlab prend en charge.
#:
#: **Redescendu de 9.0 à 8.0** : le plancher de la 0.1.91 écartait libvirt 8
#: parce que l'autoselect EFI y échouait (issue #234). La cause est corrigée
#: depuis — le template désigne son loader au lieu de laisser libvirt le choisir,
#: et le chemin est découvert dans ``virsh domcapabilities`` — donc refuser cette
#: version reviendrait à punir des postes pour un défaut qui n'existe plus.
#:
#: Refermer un plancher dès que la cause tombe compte autant que de l'ouvrir :
#: un seuil qui survit à sa raison exclut sans rien protéger, et devient une
#: dette que plus personne n'ose lever.
#:
#: Mesuré : 8.0.0 provisionne avec le loader désigné, dans une VM Ubuntu 22.04
#: où le défaut avait d'abord été reproduit à l'identique ; 10.0.0 provisionne
#: aussi, sur la machine de référence. Rien en dessous de 8.0 n'a été éprouvé.
_LIBVIRT_MINIMUM = (8, 0)

#: `virsh version` rend « Using library: libvirt 10.0.0 » : c'est la ligne qui
#: compte, celle de la bibliothèque **qui tourne**.
_VERSION_UTILISEE = re.compile(r"Using library:\s*libvirt\s*(\d+)\.(\d+)")

#: Repli sur « Compiled against library: libvirt 10.0.0 », ce contre quoi le
#: binaire a été bâti. Les deux diffèrent après une mise à jour de la
#: bibliothèque sans redémarrage du client, d'où l'ordre ; mais une sortie
#: abrégée ne porte parfois que celle-ci, et la refuser rendrait `unknown` un
#: virsh parfaitement sain.
_VERSION_COMPILEE = re.compile(
    r"Compiled against(?:\s+library)?:?\s*(?:libvirt\s*)?(\d+)\.(\d+)"
)


def _version_libvirt(sortie: str) -> tuple[int, int] | None:
    """La version de libvirt, ou ``None`` si la réponse n'en porte aucune."""
    for motif in (_VERSION_UTILISEE, _VERSION_COMPILEE):
        correspondance = motif.search(sortie or "")
        if correspondance is not None:
            return int(correspondance.group(1)), int(correspondance.group(2))
    return None


def _check_kvm() -> Check:
    if not shutil.which("virsh"):
        return _check(
            "kvm", False, _("detail_kvm_missing"),
            fix=_fix(_installer(
                ["libvirt-clients", "libvirt-daemon-system", "qemu-kvm"],
                ["libvirt", "qemu-kvm"],
            )),
        )
    # Un virsh qui sort en erreur est justement ce que ce contrôle cherche à
    # rapporter ; un virsh qui ne répond pas dit la même chose plus fort.
    #
    # L'interrogation vise **l'URI système**, celle où ``provision`` crée ses
    # domaines : ``virsh version`` nu peut viser l'URI session selon la
    # distribution, et répondre parfaitement à un utilisateur que l'URI système
    # refuse — deux lignes vertes au-dessus d'un provisionnement mort.
    # ``run_virsh`` porte le ``--connect qemu:///system`` et la détection du
    # préfixe ``sudo -n``, exactement comme les commandes qu'il couvre.
    probe = _doctor()._sonde_virsh(["version"])
    if probe is None or not probe.ok:
        return _check(
            "kvm", False, _("detail_kvm_daemon_err"),
            fix=_fix(["sudo", "systemctl", "start", "libvirtd"]),
        )
    first_line = probe.stdout.splitlines()[0] if probe.stdout else "ok"

    version = _version_libvirt(probe.stdout)
    if version is None:
        # La sonde a répondu, mais pas de façon lisible. On ne peint ni en vert
        # ni en rouge ce qu'on n'a pas su mesurer : `--strict` a son code (10).
        return _check(
            "kvm", False, _("detail_kvm_version_illisible", sortie=first_line),
            forced_state=STATE_UNKNOWN,
        )
    if version < _LIBVIRT_MINIMUM:
        return _check("kvm", False, _(
            "detail_kvm_trop_ancien",
            trouve=".".join(str(n) for n in version),
            minimum=".".join(str(n) for n in _LIBVIRT_MINIMUM),
        ))
    return _check("kvm", True, first_line)


#: Le périphérique par lequel un hyperviseur local accède à la virtualisation
#: matérielle. Constante de module pour que les tests la déplacent : le point
#: du contrôle est justement de mesurer une machine où il n'existe pas.
_KVM_DEVICE = Path("/dev/kvm")

#: ``/proc/cpuinfo``, le repli portable quand ``systemd-detect-virt`` manque.
#: Constante de module pour la même raison que ``_KVM_DEVICE``.
_CPUINFO = Path("/proc/cpuinfo")


@dataclass(frozen=True)
class Hebergement:
    """Où ce système tourne : dans une VM, sur du matériel nu, ou indéterminé.

    ``dans_une_vm`` vaut ``None`` quand aucune des deux sondes n'a abouti. Ce
    troisième état n'est pas du zèle : il décide de la consigne affichée, et
    inventer « matériel nu » par défaut enverrait dans un BIOS inexistant.
    """

    dans_une_vm: bool | None
    hyperviseur: str = ""


#: Les noms que ``systemd-detect-virt`` rend pour un conteneur, non pour une VM.
#: ``--vm`` les exclut déjà, mais il n'existe pas partout et le repli, lui, ne
#: distingue rien : un conteneur voit le ``flags`` de l'hôte.
_SANS_VM = frozenset({"none", ""})


def _hebergement() -> Hebergement:
    """Dit si ce système tourne lui-même dans une machine virtuelle.

    Deux sondes, dans cet ordre. ``systemd-detect-virt --vm`` **nomme**
    l'hyperviseur (``kvm``, ``vmware``, ``oracle``, ``microsoft``…), ce qui vaut
    mieux qu'un booléen : la consigne d'activation diffère d'un produit à
    l'autre, et l'utilisateur doit savoir dans lequel aller cliquer. Il sort en
    1 avec ``none`` sur du matériel nu, ce qui est une mesure, pas un échec.

    À défaut — le binaire n'est pas universel, et une image minimale s'en passe
    — le drapeau ``hypervisor`` de ``/proc/cpuinfo``, que tout hyperviseur x86
    pose dans ses invités. Il ne nomme personne, mais il tranche la question qui
    change le message.
    """
    sonde = _doctor()._sonder(["systemd-detect-virt", "--vm"])
    if sonde is not None:
        nom = sonde.stdout.strip().lower()
        if nom not in _SANS_VM:
            return Hebergement(dans_une_vm=True, hyperviseur=nom)
        if sonde.returncode != 0 or nom == "none":
            return Hebergement(dans_une_vm=False)

    try:
        cpuinfo = _doctor()._CPUINFO.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return Hebergement(dans_une_vm=None)
    for ligne in cpuinfo.splitlines():
        if ligne.startswith("flags") or ligne.startswith("Features"):
            return Hebergement(dans_une_vm="hypervisor" in ligne.split())
    return Hebergement(dans_une_vm=None)


def _check_hw_virt() -> Check:
    """La virtualisation matérielle, lue là où qemu ira la chercher.

    ``virsh version`` répond parfaitement sur une machine sans virtualisation :
    le daemon tourne, le client cause, et ``provision`` échoue ensuite en
    langage Terraform (« could not find capabilities for domaintype=kvm »),
    ou pire, démarre en émulation logicielle et tout expire. Le premier
    contexte réel où le périphérique manque est une VM sans virtualisation
    imbriquée, et c'est machine éteinte, dans l'hyperviseur hôte, que ça se
    règle : aucun correctif exécutable, la consigne vit dans le détail.

    **Le détail dépend donc d'où l'on tourne** (issue #91). Le message unique
    disait « active VT-x/AMD-V dans le BIOS, ou la virtualisation imbriquée dans
    ton hyperviseur » : un « ou » qui laisse chercher lequel des deux s'applique,
    et qui envoie dans le BIOS d'une machine qui n'en a pas dès que dsoxlab
    tourne dans une VM — le cas de toute image prête à l'emploi. Quand la sonde
    sait, elle nomme l'hyperviseur et ne donne que la consigne utile ; quand
    elle ne sait pas, le « ou » reste, parce qu'il est vrai.

    L'inaccessible est un état distinct de l'absent : le périphérique existe,
    seul le droit manque, et ``usermod -aG kvm`` le rend, à la session
    suivante seulement, d'où la catégorie.
    """
    if not _doctor()._KVM_DEVICE.exists():
        hote: Hebergement = _doctor()._hebergement()
        if hote.dans_une_vm is True:
            cle = (
                "detail_hw_virt_nested_named" if hote.hyperviseur
                else "detail_hw_virt_nested"
            )
            detail = _(cle, device=_doctor()._KVM_DEVICE, hypervisor=hote.hyperviseur)
        elif hote.dans_une_vm is False:
            detail = _("detail_hw_virt_bare_metal", device=_doctor()._KVM_DEVICE)
        else:
            detail = _("detail_hw_virt_missing", device=_doctor()._KVM_DEVICE)
        return _check("hw_virt", False, detail)
    if not os.access(_doctor()._KVM_DEVICE, os.R_OK | os.W_OK):
        return _check(
            "hw_virt", False, _("detail_hw_virt_denied", device=_doctor()._KVM_DEVICE),
            fix=_fix(
                ["sudo", "usermod", "-aG", "kvm", _current_user()],
                kind=FixKind.NEEDS_RELOGIN,
            ),
        )
    return _check("hw_virt", True, str(_doctor()._KVM_DEVICE))


#: Architectures des images que chaque provider packagé sait fournir.
#: ``kvm`` : les URL de ``templates/terraform/kvm/main.tf`` sont toutes des
#: images x86_64/amd64, avec ``q35``, firmware EFI x86 et ``host-passthrough``.
#: ``incus`` en est absent volontairement : le registre ``images:`` résout
#: chaque alias dans l'architecture de l'hôte.
_PROVIDER_IMAGE_ARCHS: dict[str, frozenset[str]] = {
    "kvm": frozenset({"x86_64", "amd64"}),
}


def _check_cpu_arch(provider: str) -> Check:
    """L'architecture du poste, confrontée aux images du provider actif.

    Sur un processeur aarch64, les images amd64 du template kvm ne booteront
    jamais, et rien ne le disait avant l'échec. Un provider hors du tableau
    n'impose aucune contrainte : le contrôle rend alors l'architecture
    mesurée, pas un verdict inventé.
    """
    machine = platform.machine().lower()
    if not machine:
        # Rien mesuré : ni vert ni rouge, et surtout pas un « ok » par défaut.
        return _check(
            "cpu_arch", False, _("detail_cpu_arch_unknown"),
            forced_state=STATE_UNKNOWN,
        )
    archs = _PROVIDER_IMAGE_ARCHS.get(provider)
    if archs is None or machine in archs:
        return _check("cpu_arch", True, machine)
    return _check(
        "cpu_arch", False,
        _(
            "detail_cpu_arch_mismatch",
            machine=machine, provider=provider,
            archs="/".join(sorted(archs, reverse=True)),
        ),
    )
