"""Ce que ``doctor --fix`` va jouer, dans quel ordre, et par quel moyen.

Refondu le 2026-11-16 avec le diagnostic en étapes (maquettes validées). Quatre
règles portent le module, et chacune vient d'un défaut mesuré :

1. **Le plan se lit en entier avant toute action**, et rien ne part sans
   ``[y/N]`` ou ``--yes``. Sans terminal et sans ``--yes``, rien n'est lancé.
2. **Une étape root n'est jamais lancée en silence.** Elles passent toutes par
   un playbook généré depuis la table des remèdes, joué par ``ansible-playbook
   --ask-become-pass -c local`` : une seule demande de mot de passe, faite par
   Ansible. Sans terminal, elles s'affichent en bloc à coller (décision 2).
3. **Chaque étape est revérifiée juste après, et la première qui échoue
   arrête tout.** L'ancienne règle (« un échec n'arrête pas la cascade »)
   lançait des étapes qui dépendaient de celle qui venait d'échouer : un pool
   créé sans libvirt, des collections sans Ansible.
4. **Un succès à effet différé le dit.** Un ``usermod -aG`` réussi ne vaut
   qu'après une reconnexion : sans ce message, le ``doctor`` suivant ressemble
   à un échec.

Docker et Incus, quand le catalogue ne les exige pas, n'entrent dans le plan
qu'avec ``--clients`` (décision 1).
"""

from __future__ import annotations

import os
import re
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

import yaml

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


def planifier(
    report: DoctorReport, *, clients: bool = False, actions: dict[str, Action] | None = None,
) -> PlanCorrection:
    """Partage les étapes du diagnostic entre « à lancer », « au playbook », « à dire »."""
    actions = actions or {}
    etapes = construire(report)
    plan = PlanCorrection()
    toutes = etapes.etapes + (etapes.facultatives if clients else [])
    for etape in toutes:
        if _est_manuelle(etape, actions):
            plan.manuelles.append(etape)
        elif etape.remede is not None and etape.remede.root:
            plan.root.append(etape)
        else:
            plan.sans_sudo.append(etape)
    return plan


# ── le playbook du poste ──────────────────────────────────────────────────────

#: ``sudo`` en tête de commande, ou après un tube ou un ``&&`` : le playbook
#: tourne déjà en root (``become``), le préfixe n'a plus d'objet.
_SUDO = re.compile(r"(^|[|&;]\s*|\s)sudo\s+")

#: ``apt install`` ou ``dnf install`` sans ``-y`` attend une réponse qu'aucun
#: playbook ne donnera : le paquet n'est jamais installé.
_INSTALL = re.compile(r"\b(apt|apt-get|dnf|yum)\s+install\b(?!\s+-y)")

#: Un nom de compte, tel que ``useradd`` l'accepte : rien d'autre n'entre
#: dans une commande jouée en root.
_COMPTE = re.compile(r"^[a-z_][a-z0-9_-]*[$]?$")


def lignes_root(lignes: tuple[str, ...], utilisateur: str) -> str:
    """Les lignes d'un remède, telles que le playbook les joue en root.

    Trois transformations, et aucune autre : ``sudo`` retiré (le playbook est
    déjà root), ``-y`` ajouté aux installations, et ``$USER`` remplacé par le
    compte de l'apprenant. Sous ``become``, ``$USER`` vaudrait ``root`` :
    ``usermod -aG libvirt $USER`` ajouterait root au groupe, et rien ne
    changerait pour l'apprenant.
    """
    if not _COMPTE.match(utilisateur):
        msg = f"refusing an unusual account name in a root command: {utilisateur!r}"
        raise ValueError(msg)
    jouees = []
    for ligne in lignes:
        sans_sudo = _SUDO.sub(lambda m: m.group(1), ligne)
        sans_question = _INSTALL.sub(lambda m: f"{m.group(0)} -y", sans_sudo)
        jouees.append(sans_question.replace("$USER", utilisateur))
    return "\n".join(["set -e", *jouees]) + "\n"


def playbook_du_poste(etapes: list[Etape], utilisateur: str) -> str:
    """Le playbook qui joue les étapes root, une tâche par étape, dans l'ordre.

    Généré depuis la table des remèdes, jamais écrit à la main : ce qu'il joue
    est exactement ce que ``doctor`` affiche, aux trois transformations près de
    :func:`lignes_root`.
    """
    taches = []
    for etape in etapes:
        assert etape.remede is not None
        taches.append({
            "name": f"{etape.numero}. {etape.cle}",
            "ansible.builtin.shell": lignes_root(etape.remede.lignes, utilisateur),
            "args": {"executable": "/bin/bash"},
            "environment": {"DEBIAN_FRONTEND": "noninteractive"},
            "tags": [etape.remede.tag or etape.cle],
        })
    jeu = [{
        "name": "dsoxlab doctor --fix",
        "hosts": "localhost",
        "gather_facts": False,
        "become": True,
        # Sans cette variable, Ansible avertit qu'il a « découvert » python3 :
        # vrai, sans objet ici, et c'est la seule ligne jaune que l'apprenant
        # voyait (réévaluation du 2026-11-16 sur AlmaLinux 10).
        "vars": {"ansible_python_interpreter": "auto_silent"},
        "tasks": taches,
    }]
    return yaml.safe_dump(jeu, sort_keys=False, allow_unicode=True, width=1000)


def chemin_du_playbook() -> Path:
    base = Path(os.environ.get("XDG_CACHE_HOME") or Path.home() / ".cache")
    return base / "dsoxlab" / "poste.yml"


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
