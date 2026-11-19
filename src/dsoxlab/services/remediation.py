"""Ce que ``doctor --fix`` va jouer, dans quel ordre, et par quel moyen.

Refondu le 2026-11-16 avec le diagnostic en étapes (maquettes validées). Quatre
règles portent le module, et chacune vient d'un défaut mesuré :

1. **Le plan se lit en entier avant toute action**, et rien ne part sans
   ``[y/N]`` ou ``--yes``. Sans terminal et sans ``--yes``, rien n'est lancé.
2. **Une étape root n'est jamais lancée en silence.** Elles passent toutes par
   LE playbook du poste, statique et embarqué (``templates/ansible/poste.yml``,
   brief de la PR #392), joué par ``ansible-playbook --ask-become-pass -c
   local`` : une seule demande de mot de passe, faite par Ansible. Python ne
   lui passe que des variables (les composants, le compte de l'apprenant) et
   ne génère plus aucune commande d'installation. Sans terminal, les étapes
   s'affichent en bloc à coller (décision 2).
3. **Chaque étape est revérifiée juste après, et la première qui échoue
   arrête tout.** L'ancienne règle (« un échec n'arrête pas la cascade »)
   lançait des étapes qui dépendaient de celle qui venait d'échouer : un pool
   créé sans libvirt, des collections sans Ansible.
4. **Un succès à effet différé le dit.** Un ``usermod -aG`` réussi ne vaut
   qu'après une reconnexion : sans ce message, le ``doctor`` suivant ressemble
   à un échec.

Trois profils décident de ce qui entre au plan quand le catalogue ne l'exige
pas : le socle KVM (``--fix``), plus Docker et Incus (``--fix --clients``),
plus Terraform, Ansible et ses collections (``--fix --all``).
"""

from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

from .doctor import DoctorReport, Fix, FixKind
from .doctor_controles.modele import STATE_OK, Check
from .doctor_etapes import Etape, construire

#: Signature d'un exécuteur de correctif sans shell : il rend le code de retour.
#: Injectable, pour que les tests décrivent une cascade sans toucher la machine.
Executeur = Callable[[Fix], int]

#: Une étape que dsoxlab fait lui-même, sans commande externe : choisir le
#: provider, créer la clé du catalogue, ajouter la ligne Include. Rend ``None``
#: en cas de succès, le message d'échec sinon.
Action = Callable[[], str | None]


@dataclass
class PlanCorrection:
    """Les étapes de ``--fix``, rangées par ce qu'on a le droit d'en faire."""

    sans_sudo: list[Etape] = field(default_factory=list)
    """Lancées par dsoxlab, sans privilège."""

    root: list[Etape] = field(default_factory=list)
    """Confiées au playbook du poste."""

    manuelles: list[Etape] = field(default_factory=list)
    """Jamais lancées : dsoxlab les nomme, l'humain les fait."""

    @property
    def vide(self) -> bool:
        return not (self.sans_sudo or self.root or self.manuelles)

    @property
    def executables(self) -> int:
        return len(self.sans_sudo) + len(self.root)


def _correctif(etape: Etape) -> Fix | None:
    """Le correctif sans shell d'une étape, s'il en existe un."""
    return next((c.fix for c in etape.controles if c.fix is not None), None)


def _est_manuelle(etape: Etape, actions: dict[str, Action]) -> bool:
    if etape.manuelle:
        return True
    correctif = _correctif(etape)
    if correctif is not None and correctif.kind is FixKind.MANUAL:
        return True
    if etape.remede is not None and etape.remede.root:
        return False
    return etape.cle not in actions and correctif is None


#: Les profils de ``--fix`` : les contrôles qu'un profil fait entrer au plan
#: même quand ce catalogue ne les exige pas (brief TODO/doctor-ansible.md).
#: Chaque profil contient le précédent.
PROFILS: dict[str, frozenset[str]] = {
    "socle": frozenset({"git", "kvm", "groupes", "libvirt_pool", "efi"}),
}
PROFILS["clients"] = PROFILS["socle"] | {"docker", "incus"}
PROFILS["tout"] = PROFILS["clients"] | {"terraform", "ansible", "collections"}


def profil_de(*, clients: bool, tout: bool) -> str:
    """Le profil que demandent les options : ``--all`` contient ``--clients``."""
    return "tout" if tout else ("clients" if clients else "socle")


def planifier(
    report: DoctorReport, *, clients: bool = False, profil: str | None = None,
    actions: dict[str, Action] | None = None,
) -> PlanCorrection:
    """Partage les étapes du diagnostic entre « à lancer », « au playbook », « à dire »."""
    actions = actions or {}
    nom = profil or profil_de(clients=clients, tout=False)
    etapes = construire(report, facultatives=PROFILS[nom])
    plan = PlanCorrection()
    toutes = etapes.etapes + etapes.facultatives
    for etape in toutes:
        if _est_manuelle(etape, actions):
            plan.manuelles.append(etape)
        elif etape.remede is not None and etape.remede.root:
            plan.root.append(etape)
        else:
            plan.sans_sudo.append(etape)
    return plan


# ── le playbook du poste ──────────────────────────────────────────────────────

#: Un nom de compte, tel que ``useradd`` l'accepte : rien d'autre ne part au
#: playbook comme compte à qui donner des groupes.
_COMPTE = re.compile(r"^[a-z_][a-z0-9_-]*[$]?$")

#: La clé de remède d'une étape root, vers le composant du playbook qui la
#: réalise. Deux étapes peuvent tomber sur le même composant (libvirtd est
#: démarré par le composant kvm, le groupe docker par le composant docker).
_COMPOSANTS: dict[str, str] = {
    "git": "git",
    "kvm": "kvm",
    "libvirtd": "kvm",
    "groupes": "groupes",
    "libvirt_pool": "pool",
    "efi": "efi",
    "docker": "docker",
    "incus": "incus",
    # L'outil ISO des VM Incus : le composant `incus` du playbook installe
    # genisoimage. Sans cette entrée, `doctor --fix` levait « root step without a
    # playbook component » dès que le contrôle était rouge (2026-11-19).
    "iso_tool": "incus",
    "terraform": "terraform",
}

#: Ordre du playbook, pour un affichage stable.
_ORDRE = ("git", "kvm", "efi", "groupes", "pool", "docker", "incus", "terraform")


def playbook_du_poste() -> Path:
    """Le playbook du poste, statique, embarqué dans le paquet.

    Python ne génère plus aucune commande d'installation (brief
    TODO/doctor-ansible.md, PR #392) : ce fichier est la seule source de ce
    que ``--fix`` installe, et il se lit avant d'être joué.
    """
    return Path(__file__).resolve().parents[1] / "templates" / "ansible" / "poste.yml"


def composants(etapes: list[Etape]) -> list[str]:
    """Les composants du playbook que réalisent ces étapes root, dans l'ordre du playbook.

    Une étape root sans composant connu est une erreur de programmation : la
    table des remèdes a gagné une entrée que le playbook ne sait pas servir.
    """
    trouves = set()
    for etape in etapes:
        cle = etape.remede.cle if etape.remede is not None else etape.cle
        if cle not in _COMPOSANTS:
            msg = f"root step without a playbook component: {cle!r}"
            raise ValueError(msg)
        trouves.add(_COMPOSANTS[cle])
    return [c for c in _ORDRE if c in trouves]


def _valeur(etapes: list[Etape], cle: str, motif: str) -> str | None:
    """Une valeur que le diagnostic a déjà calculée, lue dans les lignes de l'étape ``cle``."""
    expression = re.compile(motif)
    for etape in etapes:
        if etape.remede is None or etape.remede.cle != cle:
            continue
        for ligne in etape.remede.lignes:
            if (m := expression.search(ligne)) is not None:
                return m.group(1)
    return None


def composants_du_profil(profil: str) -> list[str]:
    """Les composants du playbook que couvre un profil, dans l'ordre du playbook."""
    return [c for c in _ORDRE if c in {_COMPOSANTS[k] for k in PROFILS[profil] if k in _COMPOSANTS}]


def variables_du_poste(etapes: list[Etape], utilisateur: str, profil: str = "socle") -> dict[str, object]:
    """Les variables passées au playbook : ses composants, et le compte de l'apprenant.

    Les composants sont ceux des étapes à faire PLUS tout le profil : un pool
    ou des groupes qui « attendent libvirt » ne comptent pas encore comme à
    faire, et sans le profil il fallait relancer --fix (mesuré le 2026-11-19 sur
    Ubuntu 24.04 : playbook joué avec git et kvm seulement). Le playbook étant
    idempotent, ce qui est déjà en place n'est pas modifié.

    Le pool et les groupes ne sont pas redevinés : ce sont ceux que le
    diagnostic a calculés pour ce poste et ce catalogue, et qu'il affiche.
    """
    if not _COMPTE.match(utilisateur):
        msg = f"refusing an unusual account name for the workstation playbook: {utilisateur!r}"
        raise ValueError(msg)
    voulus = set(composants(etapes)) | set(composants_du_profil(profil))
    variables: dict[str, object] = {
        "composants": [c for c in _ORDRE if c in voulus], "utilisateur": utilisateur,
    }
    if (pool := _valeur(etapes, "libvirt_pool", r"pool-define-as\s+(\S+)")) is not None:
        variables["pool"] = pool
    if (groupes := _valeur(etapes, "groupes", r"usermod -aG\s+(\S+)\s+\$USER")) is not None:
        variables["groupes"] = groupes.split(",")
    return variables


# ── revérification ────────────────────────────────────────────────────────────

def _reussi(check: Check) -> bool:
    """Un contrôle revenu au vert, ou qui n'attend plus qu'une reconnexion."""
    if check.state == STATE_OK:
        return True
    remede = check.remede
    return remede is not None and remede.reconnexion and not remede.lignes


def etape_verifiee(etape: Etape, apres: DoctorReport) -> bool:
    """L'étape a-t-elle produit son effet ? On le lit dans un diagnostic refait.

    Un code de retour nul ne suffit pas : ``apt install`` sort en 0 sur un
    paquet déjà présent qui ne règle rien, et un ``uv tool install`` peut
    poser un binaire hors du PATH. C'est le contrôle qui fait foi.
    """
    cles = {c.key for c in etape.controles}
    nouveaux = [c for c in [*apres.required, *apres.optional] if c.key in cles]
    return bool(nouveaux) and all(_reussi(c) for c in nouveaux)


@dataclass(frozen=True)
class Application:
    """Une étape jouée, et ce qu'il faut en dire."""

    etape: Etape
    code: int
    verifiee: bool
    message: str | None = None

    @property
    def ok(self) -> bool:
        return self.code == 0 and self.verifiee

    @property
    def avis_differe(self) -> str | None:
        """La clé du message à afficher quand l'effet n'est pas immédiat."""
        if not self.ok:
            return None
        if self.etape.remede is not None and self.etape.remede.reconnexion:
            return "fix_needs_relogin"
        correctif = _correctif(self.etape)
        if correctif is not None and correctif.kind is FixKind.NEEDS_RELOGIN:
            return "fix_needs_relogin"
        if correctif is not None and correctif.kind is FixKind.NEEDS_REBOOT:
            return "fix_needs_reboot"
        return None
