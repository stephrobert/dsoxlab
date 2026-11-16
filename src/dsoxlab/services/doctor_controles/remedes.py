"""La table unique des remèdes du diagnostic : chaque commande à coller, par famille.

Une seule source pour trois lecteurs : l'affichage de ``doctor``, le playbook
de ``doctor --fix`` (qui joue les mêmes étapes) et la doc d'installation, que
``tests/test_doc_installation.py`` compare à cette table. Avant, chaque
contrôle écrivait sa remédiation à la main, et trois d'entre eux ne donnaient
qu'un lien (git, Terraform, Docker) : l'apprenant devait aller lire une page
pour trouver la commande (parcours mesuré le 2026-11-16 sur Ubuntu 24.04 et
AlmaLinux 10, ~/Projets/ckne-captures/doctor/).

Les commandes viennent des pages officielles, lues le 2026-11-16 :

- Terraform : https://developer.hashicorp.com/terraform/install (dépôt
  HashiCorp, jamais le paquet de la distribution, en retard d'une version) ;
- Docker : https://docs.docker.com/engine/install/ubuntu/ et /rhel/ ;
- libvirt, git, OVMF : les paquets des distributions, noms relevés sur les
  machines de mesure (``libvirt-clients libvirt-daemon-system qemu-kvm`` sur
  Ubuntu 24.04, ``libvirt qemu-kvm`` sur AlmaLinux 10).

La famille se lit dans ``/etc/os-release`` (``ID``, puis ``ID_LIKE``), et
retombe sur la présence d'``apt-get`` ou de ``dnf`` quand le fichier ne dit
rien d'utile.
"""

from __future__ import annotations

import shutil
from collections.abc import Callable
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path

OS_RELEASE = Path("/etc/os-release")


class Famille(StrEnum):
    """La famille de distribution du poste, qui décide des commandes."""

    DEBIAN = "debian"
    RHEL = "rhel"


@dataclass(frozen=True)
class Systeme:
    """Ce que dit ``/etc/os-release`` du poste, réduit à ce qui choisit une commande."""

    famille: Famille
    identifiant: str
    """``ID`` : ``ubuntu``, ``debian``, ``almalinux``, ``fedora``…"""

    nom: str
    """``PRETTY_NAME``, pour l'en-tête du diagnostic."""


def _champs(texte: str) -> dict[str, str]:
    champs: dict[str, str] = {}
    for ligne in texte.splitlines():
        cle, sep, valeur = ligne.partition("=")
        if sep:
            champs[cle.strip()] = valeur.strip().strip('"').strip("'")
    return champs


def systeme(chemin: Path | None = None) -> Systeme:
    """Le système du poste. Ne lève jamais : un poste illisible retombe sur apt ou dnf.

    ``OS_RELEASE`` est lu à l'appel, pas à la définition, pour que les tests
    simulent une autre distribution en déplaçant cette constante.
    """
    try:
        champs = _champs((chemin or OS_RELEASE).read_text(encoding="utf-8", errors="replace"))
    except OSError:
        champs = {}
    identifiant = champs.get("ID", "").lower()
    proches = set(champs.get("ID_LIKE", "").lower().split()) | {identifiant}
    if proches & {"rhel", "fedora", "centos"}:
        famille = Famille.RHEL
    elif proches & {"debian", "ubuntu"}:
        famille = Famille.DEBIAN
    elif shutil.which("apt-get") is None and shutil.which("dnf") is not None:
        famille = Famille.RHEL
    else:
        famille = Famille.DEBIAN
    return Systeme(famille=famille, identifiant=identifiant,
                   nom=champs.get("PRETTY_NAME", identifiant or "Linux"))


@dataclass(frozen=True)
class Remede:
    """Une étape à faire : ses commandes, et ce qu'elle engage.

    ``lignes`` sont des commandes de shell prêtes à coller, dans l'ordre, une par
    ligne : ce que l'apprenant lit, et ce que la doc d'installation reproduit
    mot pour mot. ``root`` dit qu'au moins une ligne passe par ``sudo`` : ces
    étapes, ``--fix`` les confie au playbook du poste, qui demande lui-même le
    mot de passe, et ne les lance jamais en silence. ``tag`` est l'étiquette de
    l'étape dans ce playbook.
    """

    cle: str
    lignes: tuple[str, ...]
    root: bool
    tag: str | None = None
    reconnexion: bool = False
    """L'effet n'existe qu'après une déconnexion puis une reconnexion."""


_TERRAFORM_DEBIAN = (
    ("wget -O - https://apt.releases.hashicorp.com/gpg | sudo gpg --dearmor -o "
    "/usr/share/keyrings/hashicorp-archive-keyring.gpg"),
    ('echo "deb [arch=$(dpkg --print-architecture) '
    "signed-by=/usr/share/keyrings/hashicorp-archive-keyring.gpg] "
    "https://apt.releases.hashicorp.com $(grep -oP '(?<=UBUNTU_CODENAME=).*' /etc/os-release "
    '|| lsb_release -cs) main" | sudo tee /etc/apt/sources.list.d/hashicorp.list'),
    "sudo apt update && sudo apt install terraform",
)
_TERRAFORM_RHEL = (
    "sudo dnf install -y yum-utils",
    "sudo yum-config-manager --add-repo https://rpm.releases.hashicorp.com/RHEL/hashicorp.repo",
    "sudo dnf -y install terraform",
)
_TERRAFORM_FEDORA = (
    ("wget -O- https://rpm.releases.hashicorp.com/fedora/hashicorp.repo | "
    "sudo tee /etc/yum.repos.d/hashicorp.repo"),
    "sudo dnf -y install terraform",
)


#: L'étape de la doc officielle « Linux post-installation » : sans le groupe
#: docker, le démon répond « permission denied » au compte de l'apprenant, et
#: dsoxlab lance ses conteneurs avec ce compte (mesuré sur Pop!_OS 24.04 le
#: 2026-11-16 : Docker installé par --fix, contrôle toujours rouge).
_GROUPE_DOCKER = "sudo usermod -aG docker $USER"


#: Le groupe qui donne à un compte le contrôle complet d'incus.
_GROUPE_INCUS = "sudo usermod -aG incus-admin $USER"


def _docker_debian(identifiant: str) -> tuple[str, ...]:
    distribution = "debian" if identifiant == "debian" else "ubuntu"
    return (
        "sudo apt update",
        "sudo apt install ca-certificates curl",
        "sudo install -m 0755 -d /etc/apt/keyrings",
        (f"sudo curl -fsSL https://download.docker.com/linux/{distribution}/gpg "
        "-o /etc/apt/keyrings/docker.asc"),
        "sudo chmod a+r /etc/apt/keyrings/docker.asc",
        "sudo tee /etc/apt/sources.list.d/docker.sources <<EOF",
        "Types: deb",
        f"URIs: https://download.docker.com/linux/{distribution}",
        'Suites: $(. /etc/os-release && echo "${UBUNTU_CODENAME:-$VERSION_CODENAME}")',
        "Components: stable",
        "Architectures: $(dpkg --print-architecture)",
        "Signed-By: /etc/apt/keyrings/docker.asc",
        "EOF",
        "sudo apt update",
        ("sudo apt install docker-ce docker-ce-cli containerd.io docker-buildx-plugin "
        "docker-compose-plugin"),
        _GROUPE_DOCKER,
    )


_DOCKER_RHEL = (
    "sudo dnf -y install dnf-plugins-core",
    "sudo dnf config-manager --add-repo https://download.docker.com/linux/rhel/docker-ce.repo",
    ("sudo dnf install docker-ce docker-ce-cli containerd.io docker-buildx-plugin "
    "docker-compose-plugin"),
    "sudo systemctl enable --now docker",
    _GROUPE_DOCKER,
)

#: L'ajout de la ligne Include en tête de ~/.ssh/config. Un ``sed -i '1i …'``
#: n'écrit RIEN dans un fichier vide, le cas d'un poste neuf (mesuré le
#: 2026-11-16 sur AlmaLinux 10) : cette forme marche sur un fichier vide,
#: absent ou déjà rempli. Le ``|| true`` compte : sans lui, le ``cat`` d'un
#: fichier absent fait sortir le groupe en 1, et le ``&&`` n'écrit rien. Le
#: test qui joue la commande telle qu'affichée l'a trouvé.
_INCLUDE_SSH = (
    "mkdir -p ~/.ssh && t=$(mktemp) && "
    "{ echo 'Include ~/.ssh/config.d/*.conf'; cat ~/.ssh/config 2>/dev/null || true; } "
    '> "$t" && mv "$t" ~/.ssh/config && chmod 600 ~/.ssh/config'
)


def _paquets(sys_: Systeme, apt: str, dnf: str) -> tuple[str, ...]:
    if sys_.famille is Famille.RHEL:
        return (f"sudo dnf install {dnf}",)
    return (f"sudo apt install {apt}",)


def _kvm(s: Systeme, v: dict[str, str]) -> Remede:
    lignes = _paquets(s, "libvirt-clients libvirt-daemon-system qemu-kvm", "libvirt qemu-kvm")
    if s.famille is Famille.RHEL:
        # Sur AlmaLinux 10, le paquet n'active aucun démon (mesuré le
        # 2026-11-16) : sans cette ligne, l'étape suivante n'apparaissait
        # qu'au passage d'après, en « libvirt ne répond pas ».
        lignes += ("sudo systemctl enable --now libvirtd",)
    return Remede("kvm", lignes, root=True, tag="libvirt")


def _pool(s: Systeme, v: dict[str, str]) -> Remede:
    pool = v.get("pool", "default")
    return Remede("libvirt_pool", (
        f"sudo virsh pool-define-as {pool} dir --target /var/lib/libvirt/images",
        f"sudo virsh pool-build {pool}",
        f"sudo virsh pool-start {pool}",
        f"sudo virsh pool-autostart {pool}",
    ), root=True, tag="pool")


def _terraform(s: Systeme, v: dict[str, str]) -> Remede:
    lignes: tuple[str, ...]
    if s.identifiant == "fedora":
        lignes = _TERRAFORM_FEDORA
    else:
        lignes = _TERRAFORM_RHEL if s.famille is Famille.RHEL else _TERRAFORM_DEBIAN
    return Remede("terraform", lignes, root=True, tag="terraform")


def _cle_ssh(s: Systeme, v: dict[str, str]) -> Remede:
    option = f" --lab-home {v['racine']}" if v.get("racine") else ""
    return Remede("cle_ssh", (f"dsoxlab instructor bootstrap{option}",), root=False)


def _docker(s: Systeme, v: dict[str, str]) -> Remede:
    lignes = _DOCKER_RHEL if s.famille is Famille.RHEL else _docker_debian(s.identifiant)
    return Remede("docker", lignes, root=True, tag="docker", reconnexion=True)


def _incus(s: Systeme, v: dict[str, str]) -> Remede | None:
    # Incus n'est dans aucun dépôt de base d'AlmaLinux 10 (dnf info incus :
    # « No matching Packages », mesuré le 2026-11-16) : pas de remède
    # plutôt qu'une commande qui échoue.
    if s.famille is Famille.RHEL:
        return None
    # Installé seul, incus refuse le compte (« needed permissions to talk to
    # the incus daemon ») et n'a ni pool ni réseau : la même étape pose le
    # groupe et l'initialisation (réévaluation du 2026-11-16, Ubuntu 24.04).
    return Remede("incus", ("sudo apt install incus", _GROUPE_INCUS, "sudo incus admin init --auto"),
                  root=True, tag="incus", reconnexion=True)


_Fabrique = Callable[[Systeme, dict[str, str]], "Remede | None"]

#: La table : une entrée par étape, dans l'ordre où le diagnostic les présente.
#: Cet ordre est aussi celui des dépendances (libvirt avant son pool, Ansible
#: avant ses collections), et :func:`rang` le rend aux autres modules.
TABLE: dict[str, _Fabrique] = {
    "git": lambda s, v: Remede("git", _paquets(s, "git", "git"), root=True, tag="git"),
    "provider": lambda s, v: Remede(
        "provider", (f"dsoxlab use --provider {v.get('provider', 'kvm')}",), root=False),
    "kvm": _kvm,
    "libvirtd": lambda s, v: Remede(
        "libvirtd", ("sudo systemctl enable --now libvirtd",), root=True, tag="libvirt"),
    "groupes": lambda s, v: Remede(
        "groupes", (f"sudo usermod -aG {v.get('groupes', 'kvm,libvirt')} $USER",),
        root=True, tag="groupes", reconnexion=True),
    "libvirt_pool": _pool,
    "efi": lambda s, v: Remede("efi", _paquets(s, "ovmf", "edk2-ovmf"), root=True, tag="libvirt"),
    "terraform": _terraform,
    "ansible": lambda s, v: Remede("ansible", ("uv tool install ansible-core",), root=False),
    "collections": lambda s, v: Remede(
        "collections",
        (f"ansible-galaxy collection install -r {v.get('fichier', 'requirements.yml')}",),
        root=False),
    "cle_ssh": _cle_ssh,
    "ssh_include": lambda s, v: Remede("ssh_include", (_INCLUDE_SSH,), root=False),
    "incus": _incus,
    "docker": _docker,
    # Docker installé, compte hors du groupe : la même étape « docker », sans
    # réinstaller.
    "incus_groupe": lambda s, v: Remede(
        "incus", (_GROUPE_INCUS,), root=True, tag="incus", reconnexion=True),
    "docker_groupe": lambda s, v: Remede(
        "docker", (_GROUPE_DOCKER,), root=True, tag="docker", reconnexion=True),
}


def rang(cle: str) -> int:
    """La place d'une étape dans l'ordre des dépendances ; les inconnues à la fin."""
    ordre = list(TABLE)
    return ordre.index(cle) if cle in ordre else len(ordre)


def remede(cle: str, sys_: Systeme, **valeurs: str) -> Remede | None:
    """Le remède de l'étape ``cle`` sur ce système, ou ``None`` s'il n'en existe pas.

    ``valeurs`` porte ce que la table ne peut pas savoir : le pool, le fichier de
    collections, la racine du catalogue, le provider, les groupes.
    """
    fabrique = TABLE.get(cle)
    return fabrique(sys_, valeurs) if fabrique is not None else None
