"""Une VM en une commande : la stack implicite derrière ``dsoxlab vm`` (issue #401).

dsoxlab sait déjà servir de fournisseur de VM sans labs (``docs/infra-only``),
mais il fallait écrire un ``meta.yml``, choisir un sous-réseau libre, créer une
clé, puis provisionner depuis le bon dossier. Ce module écrit lui-même ce
``meta.yml``, dans un dossier à part, et le reste du chemin est celui de
``provision``, ``ssh`` et ``destroy``, inchangé : aucun template, aucun
cloud-init de plus.

Une VM vit sous ``~/.local/share/dsoxlab/vms/<nom>/`` : son ``meta.yml`` et sa
clé ``ssh/id_ed25519``. Ce sont des données que l'utilisateur garde tant que la
VM existe, pas de l'état recalculable, d'où ``XDG_DATA_HOME``. L'état Terraform,
lui, suit la règle commune : ``~/.local/state/dsoxlab/vm-<nom>/``.

LE RÉSEAU porte le numéro de son sous-réseau (``vm-137`` pour
``10.10.137.0/24``), et pas le nom de la VM. Sous KVM, le pont s'appelle
``virbr-<réseau>`` et le noyau refuse plus de 15 caractères : ``vm-<nom>``
aurait limité le nom de la VM à six caractères. Le numéro est court, et unique
puisque le sous-réseau l'est.
"""

from __future__ import annotations

import ipaddress
import json
import re
import shutil
from dataclasses import dataclass
from pathlib import Path

import yaml

from ..config import xdg_data_home
from ..utils.shell import run_command

#: Les distributions que les templates packagés savent démarrer. Un test les
#: confronte au ``distro_to_template`` des trois providers.
DISTROS = ("alma10", "alma9", "ubuntu26", "ubuntu24", "ubuntu22", "debian13", "debian12")

#: Les providers qui créent une VM sur ce poste. outscale est un cloud : une VM
#: « en une commande » y demanderait un compte et des identifiants, hors sujet ici.
PROVIDERS = ("kvm", "incus")

#: Un nom court et sans surprise : il devient un nom d'hôte (``<nom>.lab``), un
#: nom de domaine libvirt ou d'instance Incus, un identifiant de dépôt et un nom
#: de dossier. Minuscules, chiffres et tirets, comme un nom d'hôte.
_NOM = re.compile(r"^[a-z](?:[a-z0-9-]{0,30}[a-z0-9])?$")

#: Les sous-réseaux proposés, de 10.10.100.0/24 à 10.10.199.0/24. Les catalogues
#: prennent les leurs sous 10.10.100 (lab-k8s : 10.10.50.0/24), et cette plage
#: les laisse de côté même quand leur réseau est éteint, donc invisible.
_PLAGE = range(100, 200)

#: L'adresse de la VM dans son sous-réseau : la même que celle du premier hôte
#: d'un catalogue, que les templates calculent depuis l'index.
_PREMIER_HOTE = 11


class NomRefuse(ValueError):
    """Le nom ne peut pas devenir un nom d'hôte."""


class AucunSousReseauLibre(RuntimeError):
    """Les cent sous-réseaux de la plage sont tous pris."""


@dataclass(frozen=True)
class DemandeVM:
    nom: str
    distro: str = "ubuntu24"
    ram_mb: int = 2048
    vcpu: int = 2
    disk_gb: int = 20
    extra_disk_gb: int = 0
    provider: str = "kvm"


@dataclass(frozen=True)
class VMConnue:
    nom: str
    dossier: Path
    distro: str
    ram_mb: int
    vcpu: int
    disk_gb: int
    provider: str
    cidr: str


def verifier_nom(nom: str) -> str:
    if not _NOM.match(nom):
        raise NomRefuse(nom)
    return nom


def dossier_des_vm() -> Path:
    return xdg_data_home() / "dsoxlab" / "vms"


def dossier(nom: str) -> Path:
    return dossier_des_vm() / verifier_nom(nom)


def fqdn(nom: str) -> str:
    return f"{nom}.lab"


def provider_par_defaut() -> str | None:
    """kvm si l'hyperviseur est là, sinon incus, sinon rien.

    kvm d'abord : c'est le provider par défaut de tout le contrat, et celui que
    ``doctor --fix`` installe. Rien n'est lancé ici, on regarde seulement si les
    binaires et ``/dev/kvm`` existent : ``doctor`` reste le juge de ce qui marche.
    """
    if shutil.which("virsh") and Path("/dev/kvm").exists():
        return "kvm"
    if shutil.which("incus"):
        return "incus"
    return None


def nom_de_machine(nom: str, provider: str) -> str:
    """Le nom que l'hyperviseur donne à la VM, d'après les templates."""
    return fqdn(nom).replace(".", "-") if provider == "incus" else fqdn(nom)


def machine_existe(nom: str, provider: str) -> bool:
    """Une machine de ce nom existe-t-elle déjà sur l'hyperviseur ?

    Un catalogue peut avoir monté un hôte du même nom : Terraform échouerait
    une minute plus tard, après le téléchargement de l'image, sur un conflit de
    nom qu'il dirait mal.
    """
    machine = nom_de_machine(nom, provider)
    if provider == "incus":
        cmd = ["incus", "info", machine]
    else:
        cmd = ["virsh", "-c", "qemu:///system", "dominfo", machine]
    return run_command(cmd, check=False, timeout=15).ok


# ── les sous-réseaux déjà pris ────────────────────────────────────────────────

def _reseaux_du_poste() -> list[ipaddress.IPv4Network]:
    """Les réseaux IPv4 que le poste route déjà : interfaces, ponts, VPN."""
    res = run_command(["ip", "-4", "-o", "route", "show"], check=False, timeout=10)
    trouves: list[ipaddress.IPv4Network] = []
    for ligne in res.stdout.splitlines():
        premier = ligne.split(maxsplit=1)[0] if ligne.strip() else ""
        if "/" in premier:
            try:
                trouves.append(ipaddress.IPv4Network(premier, strict=False))
            except ValueError:
                continue
    return trouves


def _reseaux_libvirt() -> list[ipaddress.IPv4Network]:
    """Les réseaux libvirt, éteints compris : un réseau éteint ne se voit pas
    dans les routes, et se rallumerait sur le même sous-réseau qu'une VM neuve."""
    if not shutil.which("virsh"):
        return []
    noms = run_command(["virsh", "-c", "qemu:///system", "net-list", "--all", "--name"],
                       check=False, timeout=15)
    trouves: list[ipaddress.IPv4Network] = []
    for nom in (n.strip() for n in noms.stdout.splitlines()):
        if not nom:
            continue
        xml = run_command(["virsh", "-c", "qemu:///system", "net-dumpxml", nom],
                          check=False, timeout=15).stdout
        for adresse, masque in re.findall(
            r"<ip[^>]*address=['\"]([\d.]+)['\"][^>]*(?:netmask|prefix)=['\"]([\d.]+)['\"]", xml
        ):
            try:
                trouves.append(ipaddress.IPv4Network(f"{adresse}/{masque}", strict=False))
            except ValueError:
                continue
    return trouves


def _reseaux_incus() -> list[ipaddress.IPv4Network]:
    if not shutil.which("incus"):
        return []
    res = run_command(["incus", "network", "list", "--format", "json"], check=False, timeout=15)
    try:
        reseaux = json.loads(res.stdout or "[]")
    except ValueError:
        return []
    trouves: list[ipaddress.IPv4Network] = []
    for reseau in reseaux:
        adresse = (reseau.get("config") or {}).get("ipv4.address") or ""
        if "/" in adresse:
            try:
                trouves.append(ipaddress.IPv4Network(adresse, strict=False))
            except ValueError:
                continue
    return trouves


def reseaux_occupes() -> list[ipaddress.IPv4Network]:
    """Tout ce qu'un sous-réseau neuf ne doit pas croiser."""
    occupes = _reseaux_du_poste() + _reseaux_libvirt() + _reseaux_incus()
    occupes += [ipaddress.IPv4Network(v.cidr) for v in lister()]
    return occupes


def choisir_cidr(occupes: list[ipaddress.IPv4Network]) -> ipaddress.IPv4Network:
    for troisieme in _PLAGE:
        candidat = ipaddress.IPv4Network(f"10.10.{troisieme}.0/24")
        if not any(candidat.overlaps(o) for o in occupes):
            return candidat
    raise AucunSousReseauLibre()


# ── le meta.yml ───────────────────────────────────────────────────────────────

def meta(demande: DemandeVM, cidr: ipaddress.IPv4Network) -> dict[str, object]:
    """Le ``meta.yml`` qu'on écrirait à la main pour cette VM."""
    hote: dict[str, object] = {
        "name": fqdn(demande.nom),
        "distro": demande.distro,
        "ram_mb": demande.ram_mb,
        "vcpu": demande.vcpu,
        "disk_gb": demande.disk_gb,
    }
    if demande.extra_disk_gb:
        hote["extra_disk_gb"] = demande.extra_disk_gb
    return {
        "repo": {"id": f"vm-{demande.nom}", "title": f"VM {demande.nom}"},
        "infra": {
            "provider": demande.provider,
            "network": f"vm-{cidr.network_address.packed[2]}",
            "cidr": str(cidr),
            "hosts": [hote],
        },
    }


def ecrire(demande: DemandeVM, cidr: ipaddress.IPv4Network) -> Path:
    """Crée le dossier de la VM et y écrit son ``meta.yml``."""
    racine = dossier(demande.nom)
    racine.mkdir(parents=True, exist_ok=False)
    entete = (
        f"# Écrit par `dsoxlab vm create {demande.nom}` : la stack d'une seule VM.\n"
        f"# Elle se retire avec `dsoxlab vm destroy {demande.nom}`.\n"
    )
    (racine / "meta.yml").write_text(
        entete + yaml.safe_dump(meta(demande, cidr), sort_keys=False, allow_unicode=True),
        encoding="utf-8",
    )
    return racine


def adresse(cidr: str) -> str:
    """L'adresse que les templates donnent au premier (et seul) hôte."""
    return str(ipaddress.IPv4Network(cidr).network_address + _PREMIER_HOTE)


def lister() -> list[VMConnue]:
    """Les VM créées par ``vm create``, d'après leurs dossiers."""
    base = dossier_des_vm()
    if not base.is_dir():
        return []
    connues: list[VMConnue] = []
    for racine in sorted(p for p in base.iterdir() if (p / "meta.yml").is_file()):
        try:
            contenu = yaml.safe_load((racine / "meta.yml").read_text(encoding="utf-8")) or {}
            infra = contenu["infra"]
            hote = infra["hosts"][0]
            connues.append(VMConnue(
                nom=racine.name, dossier=racine, distro=str(hote.get("distro", "")),
                ram_mb=int(hote.get("ram_mb", 0)), vcpu=int(hote.get("vcpu", 0)),
                disk_gb=int(hote.get("disk_gb", 0)), provider=str(infra.get("provider", "")),
                cidr=str(infra["cidr"]),
            ))
        except (OSError, KeyError, IndexError, TypeError, ValueError, yaml.YAMLError):
            # Un dossier abîmé ne doit pas cacher les autres VM : il se dit dans
            # la liste de la CLI comme illisible, plutôt que de tout faire tomber.
            continue
    return connues
