"""Le modèle du diagnostic : les états, ``Check``, ``Fix`` et ``DoctorReport``.

Extrait de ``services/doctor.py`` (issue #199), sans changement de
comportement. Voir ce module pour les principes du diagnostic.
"""

from __future__ import annotations

import shlex
from collections.abc import Sequence
from dataclasses import dataclass, field
from enum import StrEnum
from types import ModuleType

from ...exit_codes import ExitCode
from ...i18n import _
from .remedes import Remede

#: Les trois états d'un contrôle, en **jetons stables**. Ce sont eux que lit un
#: programme : un tableau de bord qui devrait comparer « ok » à « présent » puis
#: à « installed » selon la langue et selon le tableau ne saurait jamais dire si
#: c'est vert ou rouge. Le libellé traduit accompagne, il ne décide pas.
STATE_OK = "ok"
STATE_FAILED = "failed"
STATE_CHOICE_REQUIRED = "choice_required"

#: ``doctor --strict`` : un contrôle requis a échoué, c'est établi.
EXIT_DOCTOR_REQUIS_KO = ExitCode.DOCTOR_REQUIS_KO

#: ``doctor --strict`` : un contrôle requis n'a **pas pu** être mesuré. Ce n'est
#: pas un échec, et ce n'est surtout pas un succès : un appelant automatisé qui
#: valide un environnement ne peut rien conclure d'une sonde qui n'a pas
#: regardé. Le code se distingue du précédent parce que les gestes diffèrent —
#: réparer, ou refaire la mesure.
EXIT_DOCTOR_INDETERMINE = ExitCode.DOCTOR_INDETERMINE
STATE_UNKNOWN = "unknown"
"""La sonde n'a pas pu mesurer : ni vert, ni rouge.

Ce module combat deux mensonges symétriques. Le premier est le rouge affiché
devant une commande qui fonctionne ; le second, plus sournois, est le vert
affiché faute d'avoir mesuré — c'est exactement le défaut du contrôle du pool
qui rendait « ok » quand virsh ne répondait pas. Un contrôle en ``unknown``
n'entre pas dans :meth:`DoctorReport.failing` (il ne prouve aucune panne),
mais son jeton dit à un programme comme à un humain que rien n'est prouvé
dans l'autre sens non plus. Voir docs/decisions/0011-three-outcomes-for-a-check.md"""


class FixKind(StrEnum):
    """Ce qu'un correctif engage, au-delà de son exécution.

    La catégorie pilote deux décisions de ``--fix`` : exécuter ou seulement
    afficher (``MANUAL``), et surtout **ce qu'on dit après**. Un ``usermod
    -aG`` réussi laisse la ligne rouge jusqu'à la reconnexion : sans le dire,
    l'utilisateur relance ``doctor``, revoit le même rouge, et conclut que le
    correctif a échoué.
    """

    AUTOMATIC = "automatic"
    """Exécuté par ``--fix``, effet immédiat : relancer ``doctor`` suffit."""

    MANUAL = "manual"
    """Jamais exécuté : ``--fix`` l'affiche, le geste appartient à l'humain."""

    NEEDS_RELOGIN = "needs_relogin"
    """Exécuté, mais l'effet attend une déconnexion puis une reconnexion."""

    NEEDS_REBOOT = "needs_reboot"
    """Exécuté, mais l'effet attend un redémarrage de la machine."""


@dataclass(frozen=True)
class Fix:
    """Un correctif typé : des tokens, jamais une chaîne interprétée.

    ``commands`` est une séquence d'argv joués **dans l'ordre** et **sans
    shell**, la suite s'arrêtant au premier échec. C'est une séquence et non
    une commande unique parce que deux correctifs réels sont des chaînes
    (créer un pool libvirt prend quatre ``virsh``), et qu'une seule liste ne
    les porterait qu'en réintroduisant un ``&&``, donc un shell.

    ``requires_sudo`` se déduit des tokens plutôt que d'être déclaré : un
    champ séparé pourrait contredire la commande qu'il décrit.
    """

    commands: tuple[tuple[str, ...], ...]
    kind: FixKind = FixKind.AUTOMATIC

    @property
    def requires_sudo(self) -> bool:
        """Au moins une des commandes s'exécute par ``sudo``."""
        return any(cmd and cmd[0] == "sudo" for cmd in self.commands)

    @property
    def display(self) -> str:
        """La forme lisible du correctif, pour l'affichage seulement.

        ``shlex.join`` requote ce qui doit l'être : un argument portant une
        espace se relit tel qu'il s'exécute. Le ``&&`` est une convention de
        lecture, pas une promesse d'exécution par un shell.
        """
        return " && ".join(shlex.join(cmd) for cmd in self.commands)


def _fix(*commands: Sequence[str], kind: FixKind = FixKind.AUTOMATIC) -> Fix:
    """Un correctif, écrit en listes de tokens sans cérémonie de tuples."""
    return Fix(commands=tuple(tuple(cmd) for cmd in commands), kind=kind)


def _installer(apt: Sequence[str], dnf: Sequence[str]) -> list[str]:
    """La commande d'installation de paquets **du poste**, apt ou dnf.

    Toutes les remédiations proposaient ``sudo apt install``, y compris sur
    Fedora, où ``--fix`` lançait donc une commande introuvable (issue
    blog-roadmap #41). Les noms diffèrent aussi d'une famille à l'autre, d'où
    deux listes. Relevé le 2026-10-01 par ``dnf repoquery`` sur Fedora 43 et
    AlmaLinux 10 : ``virsh`` vient de ``libvirt-client``, tiré par ``libvirt`` ;
    ``qemu-utils`` s'appelle ``qemu-img`` ; ``genisoimage`` n'existe plus sur
    Fedora 43, ``xorriso`` fournit ``xorrisofs``, que le contrôle accepte.

    La famille vient de ``/etc/os-release`` (:func:`.remedes.systeme`), la même
    lecture que la table des remèdes : deux détections pouvaient se contredire
    sur un même poste. apt reste le choix par défaut quand rien ne se lit.
    """
    from .remedes import Famille

    if _doctor()._systeme().famille is Famille.RHEL:
        return ["sudo", "dnf", "install", *dnf]
    return ["sudo", "apt", "install", *apt]


@dataclass(frozen=True)
class Check:
    """Un composant diagnostiqué.

    ``fix`` est un correctif typé (:class:`Fix`) que ``--fix`` sait jouer,
    token par token et sans shell ; sa catégorie dit s'il s'exécute et ce
    qu'il faut annoncer ensuite. ``hint`` est une consigne affichée mais
    **jamais** exécutée : une URL d'installation ou un choix de provider
    sont des gestes que l'apprenant doit poser lui-même.
    """

    key: str
    """Identité stable du contrôle (``kvm``, ``pytest``, ``libvirt_pool``…).

    Elle ne change pas avec la langue, et c'est par elle qu'une intégration
    désigne un contrôle. Le ``label`` en dérive : ``_("check_<key>")``, une
    seule source pour les deux, faute de quoi ils divergent."""

    label: str
    ok: bool
    detail: str
    fix: Fix | None = None
    hint: str | None = None
    forced_state: str | None = None
    """État imposé, quand « en échec » serait faux. Un provider qui reste
    à choisir bloque bien le provisionnement, mais rien n'est cassé : le
    dire en rouge revient à traiter une décision comme une panne."""

    remede: Remede | None = None
    """Les commandes à coller, une par ligne, tirées de la table unique
    (:mod:`.remedes`). C'est ce que ``doctor`` affiche et ce que le playbook de
    ``--fix`` joue pour les étapes root. Dérivé de ``fix`` ou de ``hint``
    quand le contrôle n'en donne pas : voir :func:`_check`."""

    apres: str | None = None
    """La clé du contrôle qu'il faut réparer d'abord. Le contrôle n'a pas pu
    mesurer sans lui (le pool sans libvirt, les collections sans Ansible) :
    il reste listé, en ``unknown``, au lieu de disparaître jusqu'au passage
    suivant. C'était le défaut principal du parcours mesuré le 2026-11-16 :
    il fallait relancer ``doctor`` après chaque geste pour voir le suivant."""

    mise_en_garde: str | None = None
    """Une remarque sur une ligne verte (Terraform plus ancien que la dernière
    version). Affichée sous ``-v`` seulement, et jamais un échec."""

    @property
    def state(self) -> str:
        """L'état du contrôle, en jeton stable."""
        return self.forced_state or (STATE_OK if self.ok else STATE_FAILED)

    @property
    def remediation(self) -> str:
        """Ce qu'affiche la colonne « Remédiation »."""
        if self.fix is not None:
            return self.fix.display
        return self.hint or ""


def _check(
    key: str,
    ok: bool,
    detail: str,
    *,
    fix: Fix | None = None,
    hint: str | None = None,
    forced_state: str | None = None,
    remede: Remede | None = None,
    apres: str | None = None,
    mise_en_garde: str | None = None,
) -> Check:
    """Un contrôle, dont l'identité stable engendre le libellé traduit.

    Le libellé n'est pas passé : il se déduit de ``key``. Les deux étaient
    écrits côte à côte à chaque appel, et rien n'aurait empêché un contrôle
    d'annoncer ``kvm`` à un programme et « Terraform » à un humain.

    Sans ``remede`` explicite, il se déduit du correctif (une ligne par argv)
    ou d'une consigne qui est une commande. Une URL n'est jamais un remède :
    c'était le défaut de git, Terraform et Docker, qui renvoyaient lire une page.
    """
    if remede is None and not ok:
        remede = remede_derive(key, fix, hint)
    return Check(
        key=key,
        label=_(f"check_{key}"),
        ok=ok,
        detail=detail,
        fix=fix,
        hint=hint,
        forced_state=forced_state,
        remede=remede,
        apres=apres,
        mise_en_garde=mise_en_garde,
    )


def remede_derive(key: str, fix: Fix | None, hint: str | None) -> Remede | None:
    """Le remède d'un contrôle qui n'en donne pas : son correctif, ou sa consigne."""
    if fix is not None:
        return Remede(
            cle=key,
            lignes=tuple(shlex.join(cmd) for cmd in fix.commands),
            root=fix.requires_sudo,
            tag=key,
            reconnexion=fix.kind is FixKind.NEEDS_RELOGIN,
        )
    if hint and not hint.startswith(("http://", "https://")):
        return Remede(cle=key, lignes=(hint,), root=hint.startswith("sudo "))
    return None


@dataclass
class DoctorReport:
    """Le diagnostic, séparé en ce qui bloque et ce qui informe."""

    required: list[Check] = field(default_factory=list)
    optional: list[Check] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)
    """Phrases qui expliquent *pourquoi* un composant est informatif ici."""

    optional_title_key: str = "doctor_optional_title"
    optional_hint_key: str = "doctor_optional_hint"
    """Titre et pied du second tableau. Ils sont variables parce qu'ils
    mentaient dans un cas précis : sur un catalogue qui compte des labs ``vm``
    mais dont aucun provider n'est encore choisi, ce tableau s'intitulait
    « non requis ici » et affirmait « ces composants ne bloquent rien », sous
    les deux hyperviseurs dont l'un est indispensable pour jouer 64 labs sur
    84. Les checks restent hors du requis, sans quoi ``--fix`` proposerait
    d'installer kvm **et** incus pour un choix qui n'est pas fait ; c'est le
    libellé qui devait dire la vérité, pas le classement."""

    a_savoir: list[Check] = field(default_factory=list)
    """Ce qui mérite d'être lu sans bloquer : la mémoire qui ne suffit pas pour
    monter tout le catalogue d'un coup (décision du 2026-11-16). Un lab ne monte
    souvent qu'une machine, et ``provision --host`` le permet : peindre ce cas
    en rouge requis refusait des postes qui jouent parfaitement leurs labs.
    Hors de ``failing()``, donc hors du verdict de ``--strict``."""

    catalogue: str | None = None
    """L'``id`` du catalogue diagnostiqué, ou ``None`` hors de tout catalogue."""

    nb_labs: int = 0
    systeme: str = ""
    """Le nom du système (``PRETTY_NAME``), pour l'en-tête."""

    provider: str = ""
    """Le provider avec lequel le diagnostic a été fait."""

    provider_a_confirmer: bool = False
    """Le provider n'est pas choisi : le diagnostic a pris celui qu'il
    recommande, pour ne cacher aucun contrôle, sans l'enregistrer."""

    def failing(self) -> list[Check]:
        # Un contrôle ``unknown`` n'a rien prouvé : il ne peut pas peindre le
        # verdict en rouge. Son jeton suffit à dire qu'il n'est pas vert.
        return [
            c for c in self.required
            if not c.ok and c.state != STATE_UNKNOWN
        ]

    def indetermines(self) -> list[Check]:
        """Les requis dont la sonde n'a rien pu établir.

        Le pendant de :meth:`failing` : celle-ci écarte les ``unknown`` pour ne
        pas peindre l'affichage en rouge sur ce qu'on ignore, et c'est juste
        pour un humain qui lit un tableau. Un script, lui, doit distinguer
        « c'est bon » de « je n'ai pas pu voir », sans quoi il conclut au vert
        sur une mesure qui n'a pas eu lieu.
        """
        return [c for c in self.required if c.state == STATE_UNKNOWN]

    def fixable(self) -> list[Check]:
        return [c for c in self.required if not c.ok and c.fix]


def _doctor() -> ModuleType:
    """Le point d'entrée ``services.doctor``, relu à chaque appel.

    Les sondes (``_sonder``, ``_mem_available_mb``, ``_KVM_DEVICE``...) se
    lisent sur lui et non sur leur module : c'est là que les tests les
    remplacent, et le découpage de l'issue #199 ne devait réécrire aucun test.
    L'import est tardif parce que ``services.doctor`` importe ce paquet.
    """
    from .. import doctor

    return doctor
