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
"""

from __future__ import annotations

import getpass
import os
import platform
import re
import shlex
import shutil
import socket
import subprocess
import sys
from collections.abc import Sequence
from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import Path

from ..discovery.scanner import compter_fichiers_labs
from ..i18n import _
from ..infra import ansible as ansible_infra
from ..infra import libvirt as libvirt_infra
from ..models import LabDefinition, RepoMetadata
from ..models.repo import InfraDefinition
from ..models.runtime import RuntimeType
from ..utils.shell import CommandError, CommandResult
from .lab_service import get_all_labs, resolve_pytest_cmd

#: Providers packagés qui reposent sur un hyperviseur **local**, donc
#: diagnosticables sur la machine de l'apprenant. ``outscale`` en est
#: absent volontairement : rien à vérifier localement pour un cloud.
_LOCAL_HYPERVISORS = ("kvm", "incus")

#: Types de runtime qui exigent une VM provisionnée. Les deux alias
#: historiques comptent autant que la valeur cible.
_VM_RUNTIMES = frozenset({RuntimeType.VM, RuntimeType.KVM, RuntimeType.INCUS})


#: Les trois états d'un contrôle, en **jetons stables**. Ce sont eux que lit un
#: programme : un tableau de bord qui devrait comparer « ok » à « présent » puis
#: à « installed » selon la langue et selon le tableau ne saurait jamais dire si
#: c'est vert ou rouge. Le libellé traduit accompagne, il ne décide pas.
STATE_OK = "ok"
STATE_FAILED = "failed"
STATE_CHOICE_REQUIRED = "choice_required"

#: ``doctor --strict`` : un contrôle requis a échoué, c'est établi.
EXIT_DOCTOR_REQUIS_KO = 9

#: ``doctor --strict`` : un contrôle requis n'a **pas pu** être mesuré. Ce n'est
#: pas un échec, et ce n'est surtout pas un succès : un appelant automatisé qui
#: valide un environnement ne peut rien conclure d'une sonde qui n'a pas
#: regardé. Le code se distingue du précédent parce que les gestes diffèrent —
#: réparer, ou refaire la mesure.
EXIT_DOCTOR_INDETERMINE = 10
STATE_UNKNOWN = "unknown"
"""La sonde n'a pas pu mesurer : ni vert, ni rouge.

Ce module combat deux mensonges symétriques. Le premier est le rouge affiché
devant une commande qui fonctionne ; le second, plus sournois, est le vert
affiché faute d'avoir mesuré — c'est exactement le défaut du contrôle du pool
qui rendait « ok » quand virsh ne répondait pas. Un contrôle en ``unknown``
n'entre pas dans :meth:`DoctorReport.failing` (il ne prouve aucune panne),
mais son jeton dit à un programme comme à un humain que rien n'est prouvé
dans l'autre sens non plus."""


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
) -> Check:
    """Un contrôle, dont l'identité stable engendre le libellé traduit.

    Le libellé n'est pas passé : il se déduit de ``key``. Les deux étaient
    écrits côte à côte à chaque appel, et rien n'aurait empêché un contrôle
    d'annoncer ``kvm`` à un programme et « Terraform » à un humain.
    """
    return Check(
        key=key,
        label=_(f"check_{key}"),
        ok=ok,
        detail=detail,
        fix=fix,
        hint=hint,
        forced_state=forced_state,
    )


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


# ── checks unitaires ──────────────────────────────────────────────────────────

def _check_python() -> Check:
    return _check("python", True, sys.version.split()[0])


def _check_pytest(root: Path) -> Check:
    """Diagnostique pytest par la résolution qu'utilise réellement ``check``."""
    cmd = resolve_pytest_cmd(root)
    if cmd is None:
        return _check(
            "pytest", False, _("detail_pytest_missing"),
            hint="uv tool install --force dsoxlab",
        )
    if cmd[0] == sys.executable:
        return _check("pytest", True, _("detail_pytest_bundled"))
    return _check("pytest", True, _("detail_pytest_via", cmd=" ".join(cmd)))


def _check_shell() -> Check:
    return _check("shell", True, _("detail_shell_always"))


def _sonder(
    commande: list[str], *, delai: float = 5, env: dict[str, str] | None = None
) -> subprocess.CompletedProcess[str] | None:
    """Joue une sonde, ou rend ``None`` si elle ne répond pas.

    Un diagnostic qui plante en diagnostiquant emporte toute la commande, et
    depuis que ``doctor --json`` est une interface, il emporte aussi le document
    de l'appelant : une ``TimeoutExpired`` remonte alors en trace Python là où
    l'appelant attendait du JSON. ``virsh version`` pend jusqu'au délai sur un
    hôte dont libvirt ne répond plus, et c'est un cas courant, pas un cas d'école.

    ``check=False`` : un code retour non nul EST le diagnostic. C'est l'absence
    de réponse, elle, qui vaut ``None``.
    """
    try:
        return subprocess.run(
            commande, capture_output=True, text=True, timeout=delai,
            check=False, env=env,
        )
    except (OSError, subprocess.SubprocessError):
        return None


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


def _current_user() -> str:
    """L'utilisateur à qui s'adresse un correctif de groupe.

    ``$USER`` d'abord, comme le faisait la chaîne shell d'avant ; à défaut,
    ``getpass.getuser()`` lit la table des comptes. L'ancien repli littéral
    ``$USER`` n'a plus de sens sans shell pour l'expanser.
    """
    return os.environ.get("USER") or getpass.getuser()


def _check_incus() -> Check:
    """Binaire + daemon + permissions user + init storage/network.

    Un simple ``which incus`` ne suffit pas : sans daemon actif ni
    appartenance au groupe ``incus``, le client ne peut rien faire
    (« permissions to talk to the incus daemon »).
    """
    if not shutil.which("incus"):
        return _check(
            "incus", False, _("detail_incus_missing"),
            fix=_fix(["sudo", "apt", "install", "incus"]),
        )

    # Le numéro de version n'est qu'un ornement du diagnostic. Le verdict vient
    # de la sonde suivante, qui, elle, lit son code retour.
    ver = _sonder(["incus", "--version"])
    version = (ver.stdout.strip() if ver else "") or "?"

    probe = _sonder(["incus", "list"])
    # Muette, elle ne prouve rien sinon que le daemon ne répond pas : c'est le
    # même geste de réparation que sur un daemon arrêté.
    if probe is None:
        return _check(
            "incus", False, _("detail_incus_daemon_down", version=version),
            fix=_fix(["sudo", "systemctl", "enable", "--now", "incus.service"]),
        )
    if probe.returncode == 0:
        return _check("incus", True, _("detail_incus_ok", version=version))

    err = (probe.stderr or "").lower()
    if "permission" in err or "socket" in err:
        # Soit daemon inactif, soit user hors du groupe : deux causes,
        # deux remédiations, que l'erreur seule ne distingue pas.
        # `is-active` répond par son code retour, c'est sa façon de dire non.
        etat = _sonder(["systemctl", "is-active", "--quiet", "incus.service"])
        daemon_active = etat is not None and etat.returncode == 0
        if not daemon_active:
            return _check(
                "incus", False,
                _("detail_incus_daemon_down", version=version),
                fix=_fix(["sudo", "systemctl", "enable", "--now", "incus.service"]),
            )
        # NEEDS_RELOGIN : l'appartenance à un groupe ne prend effet qu'à la
        # session suivante. Sans cette catégorie, l'utilisateur relançait
        # `doctor`, revoyait le rouge, et croyait le correctif en échec.
        return _check(
            "incus", False,
            _("detail_incus_no_group", version=version),
            fix=_fix(
                ["sudo", "usermod", "-aG", "incus,incus-admin", _current_user()],
                kind=FixKind.NEEDS_RELOGIN,
            ),
        )
    if "no storage pools" in err or "init" in err:
        return _check(
            "incus", False,
            _("detail_incus_no_init", version=version),
            fix=_fix(["sudo", "incus", "admin", "init", "--auto"]),
        )

    tail = (probe.stderr or probe.stdout).strip().splitlines()
    return _check("incus", False, tail[-1] if tail else _("detail_unknown_error"))


def _check_kvm() -> Check:
    if not shutil.which("virsh"):
        return _check(
            "kvm", False, _("detail_kvm_missing"),
            fix=_fix([
                "sudo", "apt", "install",
                "libvirt-clients", "libvirt-daemon-system", "qemu-kvm",
            ]),
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
    probe = _sonde_virsh(["version"])
    if probe is None or not probe.ok:
        return _check(
            "kvm", False, _("detail_kvm_daemon_err"),
            fix=_fix(["sudo", "systemctl", "start", "libvirtd"]),
        )
    first_line = probe.stdout.splitlines()[0] if probe.stdout else "ok"
    return _check("kvm", True, first_line)


def _check_terraform() -> Check:
    """Terraform provisionne les machines, quel que soit le provider.

    Il ne figurait dans aucun contrôle, alors que ``provision`` s'arrête net
    sans lui. Pire, son message renvoyait vers ``dsoxlab instructor bootstrap``,
    qui se contente de signaler l'absence sans jamais l'installer : l'apprenant
    tournait en rond entre deux commandes qui lui disaient la même chose.
    """
    if shutil.which("terraform") is None:
        return _check(
            "terraform", False, _("detail_terraform_missing"),
            hint="https://developer.hashicorp.com/terraform/install",
        )
    # Le binaire peut être dans le PATH sans être exécutable, ou disparaître
    # entre les deux appels. Un diagnostic qui plante en cherchant à
    # diagnostiquer est le pire des cas : il emporte toute la commande.
    result = _sonder(["terraform", "version"])
    if result is None:
        return _check(
            "terraform", False, _("detail_terraform_missing"),
            hint="https://developer.hashicorp.com/terraform/install",
        )
    # Un terraform présent mais qui sort en erreur passait pour vert : le code
    # retour n'était pas lu, et « ok » s'affichait faute de stdout. `provision`
    # échouait ensuite sur une machine que `doctor` venait de déclarer prête.
    if result.returncode != 0:
        detail = (result.stderr or result.stdout).strip().splitlines()
        return _check(
            "terraform", False,
            detail[-1] if detail else _("detail_terraform_broken"),
            hint="https://developer.hashicorp.com/terraform/install",
        )
    first = result.stdout.splitlines()[0] if result.stdout else "ok"
    return _check("terraform", True, first)


def _check_ansible() -> Check:
    """``run`` sur un lab vm joue un playbook : il faut ``ansible-playbook``.

    ``ansible-runner`` ne tire pas ``ansible-core``. Le contrôle portait sur
    l'import de la bibliothèque, donc il était vert sur une machine où aucun
    playbook ne pouvait tourner, et ``run`` sortait en ``rc=127`` sans que rien
    ne relie les deux.
    """
    if not ansible_infra.has_ansible_playbook():
        return _check(
            "ansible", False, _("detail_ansible_missing"),
            fix=_fix(["uv", "tool", "install", "ansible-core"]),
        )
    return _check("ansible", True, _("detail_ansible_ok"))


#: Le périphérique par lequel un hyperviseur local accède à la virtualisation
#: matérielle. Constante de module pour que les tests la déplacent : le point
#: du contrôle est justement de mesurer une machine où il n'existe pas.
_KVM_DEVICE = Path("/dev/kvm")


def _check_hw_virt() -> Check:
    """La virtualisation matérielle, lue là où qemu ira la chercher.

    ``virsh version`` répond parfaitement sur une machine sans virtualisation :
    le daemon tourne, le client cause, et ``provision`` échoue ensuite en
    langage Terraform (« could not find capabilities for domaintype=kvm »),
    ou pire, démarre en émulation logicielle et tout expire. Le premier
    contexte réel où le périphérique manque est une VM sans virtualisation
    imbriquée, et c'est machine éteinte, dans l'hyperviseur hôte, que ça se
    règle : aucun correctif exécutable, la consigne vit dans le détail.

    L'inaccessible est un état distinct de l'absent : le périphérique existe,
    seul le droit manque, et ``usermod -aG kvm`` le rend, à la session
    suivante seulement, d'où la catégorie.
    """
    if not _KVM_DEVICE.exists():
        return _check(
            "hw_virt", False, _("detail_hw_virt_missing", device=_KVM_DEVICE),
        )
    if not os.access(_KVM_DEVICE, os.R_OK | os.W_OK):
        return _check(
            "hw_virt", False, _("detail_hw_virt_denied", device=_KVM_DEVICE),
            fix=_fix(
                ["sudo", "usermod", "-aG", "kvm", _current_user()],
                kind=FixKind.NEEDS_RELOGIN,
            ),
        )
    return _check("hw_virt", True, str(_KVM_DEVICE))


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


def _mem_available_mb() -> int | None:
    """``MemAvailable`` de ``/proc/meminfo``, en MiB, ou ``None`` si illisible.

    ``MemAvailable`` plutôt que ``MemFree`` : c'est l'estimation du noyau de
    ce qu'une nouvelle charge peut réellement obtenir, cache compris.
    """
    try:
        contenu = Path("/proc/meminfo").read_text(encoding="ascii")
    except OSError:
        return None
    for ligne in contenu.splitlines():
        if ligne.startswith("MemAvailable:"):
            champs = ligne.split()
            if len(champs) >= 2 and champs[1].isdigit():
                return int(champs[1]) // 1024
    return None


def _pool_available_gb(pool: str) -> int | None:
    """L'espace disponible du pool libvirt visé, en GiB, ou ``None`` si non mesuré.

    ``pool-info --bytes`` rend la place telle que libvirt la voit, c'est-à-dire
    celle du répertoire cible réel du pool, où qu'il soit monté. ``LC_ALL=C``
    n'est pas décoratif : virsh traduit ses libellés, et « Available: » devient
    « Disponible : » sous une locale française.
    """
    probe = _sonder(
        ["virsh", "-c", "qemu:///system", "pool-info", pool, "--bytes"],
        env={**os.environ, "LC_ALL": "C"},
    )
    if probe is None or probe.returncode != 0:
        return None
    for ligne in probe.stdout.splitlines():
        if ligne.startswith("Available:"):
            champs = ligne.split()
            if len(champs) >= 2 and champs[1].isdigit():
                return int(champs[1]) // 2**30
    return None


def _check_resources(infra: InfraDefinition, provider: str) -> Check:
    """Ce que le poste offre, face à ce que le ``meta.yml`` déclare.

    Un provisionnement a déjà expiré sur un hôte à 2 vCPU / 4 Go (hôte prêt à
    181 secondes pour un délai de 180) sans que rien ne l'annonce. La somme
    des ``ram_mb`` et des ``disk_gb`` (+ ``extra_disk_gb``) du catalogue est la
    demande ; ``MemAvailable`` et le pool libvirt sont l'offre.

    Une sonde impossible ne vaut jamais « ok » : la portion non mesurée est
    nommée, et le contrôle sort en ``unknown``, sauf si une portion mesurée
    manque déjà, auquel cas le manque prouvé l'emporte.
    """
    besoin_ram = sum(h.ram_mb for h in infra.hosts)
    besoin_disk = sum(h.disk_gb + h.extra_disk_gb for h in infra.hosts)

    manque = False
    inconnu = False
    portions: list[str] = []

    dispo_ram = _mem_available_mb()
    if dispo_ram is None:
        inconnu = True
        portions.append(_("detail_resources_ram_unknown"))
    else:
        manque = manque or dispo_ram < besoin_ram
        portions.append(
            _("detail_resources_ram", avail=dispo_ram, need=besoin_ram)
        )

    if provider == "kvm":
        pool = str(infra.provider_config("kvm").get("storage_pool") or "default")
        dispo_disk = _pool_available_gb(pool)
        if dispo_disk is None:
            # Pool absent, inactif ou virsh muet : le contrôle du pool porte
            # déjà ce rouge-là, le redire ici empilerait deux échecs pour une
            # seule cause. Mais rien n'est mesuré, donc rien n'est vert.
            inconnu = True
            portions.append(_("detail_resources_disk_unknown", pool=pool))
        else:
            manque = manque or dispo_disk < besoin_disk
            portions.append(
                _(
                    "detail_resources_disk",
                    pool=pool, avail=dispo_disk, need=besoin_disk,
                )
            )
    else:
        # L'outil ne sait pas mesurer le stockage de ce provider : le dire
        # vaut mieux qu'un vert conclu sur la seule RAM.
        inconnu = True
        portions.append(_("detail_resources_disk_unprobed", provider=provider))

    # Le joint se traduit : la typographie française met une espace avant le
    # point-virgule, l'anglaise non.
    detail = _("detail_resources_join").join(portions)
    if manque:
        return _check("resources", False, detail)
    if inconnu:
        return _check(
            "resources", False, detail, forced_state=STATE_UNKNOWN,
        )
    return _check("resources", True, detail)


def creer_pool_fix(pool: str) -> Fix:
    """Le correctif qui crée un pool libvirt de bout en bout.

    Les quatre étapes comptent : ``pool-define-as`` seul laisse un pool défini
    mais **inactif**, dans lequel Terraform ne peut rien écrire.
    """
    return _fix(
        ["sudo", "virsh", "pool-define-as", pool, "dir",
         "--target", "/var/lib/libvirt/images"],
        ["sudo", "virsh", "pool-build", pool],
        ["sudo", "virsh", "pool-start", pool],
        ["sudo", "virsh", "pool-autostart", pool],
    )


def demarrer_pool_fix(pool: str) -> Fix:
    """Le correctif qui démarre un pool déjà défini, et le rend permanent."""
    return _fix(
        ["sudo", "virsh", "pool-start", pool],
        ["sudo", "virsh", "pool-autostart", pool],
    )


def creer_pool_command(pool: str) -> str:
    """La création du pool, en une ligne à copier après un échec de provision."""
    return creer_pool_fix(pool).display


def demarrer_pool_command(pool: str) -> str:
    """Le démarrage du pool, en une ligne à copier après un échec de provision."""
    return demarrer_pool_fix(pool).display


def _pools_libvirt(*, definis: bool) -> list[str] | None:
    """Noms des pools libvirt : les actifs seuls, ou tous ceux qui sont définis.

    Rendre ``None`` quand la sonde n'aboutit pas. ``virsh`` absent ou muet est
    l'affaire du contrôle KVM ; le redire ici empilerait deux rouges pour une
    seule cause. Mais ``None`` n'est pas un vert : le contrôle appelant doit le
    traduire en :data:`STATE_UNKNOWN`, jamais en « tout va bien ».

    La sonde passe par :func:`~dsoxlab.infra.libvirt.run_virsh` : invoquer
    ``virsh`` en direct échouait systématiquement sur les machines où l'URI
    système exige ``sudo``, et l'échec permanent de la sonde peignait le
    contrôle en vert permanent.
    """
    args = ["pool-list"]
    if definis:
        args.append("--all")
    args.append("--name")
    probe = _sonde_virsh(args)
    if probe is None or not probe.ok:
        return None
    return probe.stdout.split()


def _check_libvirt_pool(pool: str) -> Check:
    """Le template KVM écrit ses volumes dans un pool libvirt.

    Une Ubuntu fraîche avec ``libvirt-daemon-system`` n'en déclare aucun :
    ``virsh pool-list --all`` est vide, et ``provision`` échoue sur un « Pool
    Not Found » brut de Terraform, que rien n'explique.

    Le nom vient de ``meta.yml: infra.providers.kvm.storage_pool``, faute de
    quoi ``default``. Le contrôle porte donc sur le pool que le dépôt vise
    réellement, et non sur un nom présumé.

    Absent et inactif sont **deux états distincts**, et les confondre faisait
    mentir le diagnostic. ``virsh pool-list --name`` ne liste que les pools
    **actifs** : un pool défini mais jamais démarré n'y figure pas, le contrôle
    le déclarait donc introuvable et proposait un ``pool-define-as`` qui échoue
    aussitôt (« pool already exists »). Or Terraform, lui, sort sur une erreur
    entièrement différente (« storage pool 'x' is not active »), et le geste qui
    débloque est ``pool-start``, pas une création.
    """
    actifs = _pools_libvirt(definis=False)
    if actifs is None:
        # La sonde n'a pas pu regarder : ni vert, ni rouge. L'ancien code
        # rendait ``ok=True`` ici — le vert affiché faute d'avoir mesuré,
        # exactement le mensonge que STATE_UNKNOWN existe pour interdire.
        return _check(
            "libvirt_pool", False, _("detail_pool_unknown"),
            forced_state=STATE_UNKNOWN,
        )
    if pool in actifs:
        return _check("libvirt_pool", True, pool)

    definis = _pools_libvirt(definis=True)
    if definis is None:
        # Le pool n'est pas actif, mais sans la liste des pools définis on ne
        # sait pas si le geste est « créer » ou « démarrer » : proposer l'un
        # des deux au hasard ferait échouer la remédiation sur l'autre cas.
        return _check(
            "libvirt_pool", False, _("detail_pool_unknown"),
            forced_state=STATE_UNKNOWN,
        )
    if pool in definis:
        return _check(
            "libvirt_pool", False, _("detail_pool_inactive", pool=pool),
            fix=demarrer_pool_fix(pool),
        )
    return _check(
        "libvirt_pool", False, _("detail_pool_missing", pool=pool),
        fix=creer_pool_fix(pool),
    )


#: Fichier d'override AppArmor qui rend les images libvirt lisibles par qemu.
_APPARMOR_OVERRIDE = Path("/etc/apparmor.d/local/abstractions/libvirt-qemu")


def apparmor_override_absent() -> bool:
    """AppArmor est-il actif SANS l'override qui autorise les images libvirt ?

    Volontairement **pas** un ``Check``. Sur une Ubuntu 24.04 fraîche, l'absence
    de cet override fait échouer tout démarrage de domaine : ``virt-aa-helper``
    construit le profil à partir du XML, or terraform-provider-libvirt déclare
    ses disques par référence de pool (``<disk type='volume'>``), une forme
    qu'il ne sait pas résoudre en chemin. Aucun disque n'entre dans le profil,
    et qemu se voit tout refuser par un « Permission denied » qui ressemble à un
    problème de propriétaire sans en être un.

    Mais l'inverse n'est pas vrai, et c'est ce qui interdit d'en faire un
    diagnostic préventif : mesuré sur une machine où AppArmor est actif, où cet
    override est absent, et où huit domaines libvirt tournent pourtant sans
    incident. La version de ``virt-aa-helper``, le pilote de sécurité déclaré
    dans ``qemu.conf`` et l'emplacement réel des images changent la conclusion.

    Ce module s'interdit précisément ce genre d'affirmation : un rouge affiché
    devant une commande qui fonctionne est ce qui décourageait au premier
    lancement. On garde donc l'information pour le seul moment où elle est
    certaine, celui où le provisionnement a réellement échoué là-dessus.
    """
    if not Path("/sys/module/apparmor/parameters/enabled").is_file():
        return False
    try:
        return "/var/lib/libvirt/images/" not in _APPARMOR_OVERRIDE.read_text(
            encoding="utf-8"
        )
    except OSError:
        return True


def apparmor_fix_command() -> str:
    """La commande qui pose l'override. Le droit ``k`` n'est pas décoratif :
    avec ``r`` seul, l'erreur devient « Failed to lock byte 100 »."""
    return (
        "echo '  /var/lib/libvirt/images/** rwk,' | sudo tee "
        f"{_APPARMOR_OVERRIDE} && sudo systemctl restart libvirtd"
    )


#: Le nom du pool tel que libvirt le cite dans ses deux messages d'échec.
#: L'extraire évite de nommer « default » à un dépôt qui vise le sien via
#: ``meta.yml: infra.providers.kvm.storage_pool`` : la remédiation porterait
#: alors sur un pool que personne n'utilise.
_POOL_ABSENT = re.compile(
    r"no storage pool with matching name '([^']+)'"
    r"|storage pool '([^']+)' not found",
    re.IGNORECASE,
)
_POOL_INACTIF = re.compile(
    r"storage pool '([^']+)' is not active", re.IGNORECASE
)


def _pool_cite(motif: re.Pattern[str], message: str) -> str | None:
    """Le pool que ``message`` nomme, ou ``None`` si le motif ne mord pas."""
    trouve = motif.search(message)
    if trouve is None:
        return None
    return next((groupe for groupe in trouve.groups() if groupe), None)


def explique_echec_provision(message: str) -> tuple[str, str] | None:
    """Reconnaît une cause connue dans l'erreur brute d'un provisionnement.

    Terraform rend des messages exacts mais opaques pour qui découvre l'outil.
    Quelques-uns ont une cause connue et un correctif d'une ligne, et ce sont
    ceux qui arrêtent un débutant sur une machine fraîche.

    Rendre ``(explication, commande)``, ou ``None`` si rien n'est reconnu : on
    ne devine pas, on nomme ce qu'on sait nommer.
    """
    bas = message.lower()

    # « Permission denied » sur une image du pool : l'échec type d'AppArmor
    # décrit dans apparmor_override_absent(). On ne le propose QUE si
    # l'override manque effectivement, sans quoi ce serait une fausse piste.
    #
    # Depuis que le template déclare ses disques par chemin de fichier plutôt
    # que par référence de pool, une machine provisionnée par cette version ne
    # tombe plus là-dessus. La branche reste pour les domaines définis par une
    # version antérieure, qui portent encore la forme que virt-aa-helper ne sait
    # pas résoudre : eux ne guériront qu'en étant recréés.
    if (
        "permission denied" in bas
        and "/var/lib/libvirt/images" in bas
        and apparmor_override_absent()
    ):
        return _("explain_apparmor_denied"), apparmor_fix_command()

    # « is not active » : le pool existe mais n'a jamais été démarré. C'est un
    # état DIFFÉRENT de l'absence, et il appelle un autre geste. Un
    # `pool-define-as` proposé ici échouerait sur « pool already exists ».
    pool_inactif = _pool_cite(_POOL_INACTIF, message)
    if pool_inactif is not None:
        return _("explain_pool_inactive"), demarrer_pool_command(pool_inactif)

    # « Pool not found » : le pool visé n'existe pas. Une installation fraîche
    # n'en déclare aucun. Le contrôle de doctor l'attrape en amont, mais un
    # provisionnement lancé sans diagnostic préalable tombe directement ici.
    pool_absent = _pool_cite(_POOL_ABSENT, message)
    if pool_absent is not None or "pool not found" in bas:
        return _("explain_pool_not_found"), creer_pool_command(
            pool_absent or "default"
        )

    # « already exists » sur un domaine : un provisionnement précédent a échoué
    # APRÈS avoir défini la machine, qui n'est donc pas dans le state Terraform.
    # `destroy` ne peut pas la voir, et le message ne dit pas quoi faire.
    if "already exists with uuid" in bas:
        return _("explain_domain_exists"), (
            "virsh -c qemu:///system undefine --nvram <machine>"
        )

    return None


def _check_iso_tool() -> Check:
    """Incus fabrique le CD-ROM ``agent:config`` sur l'hôte.

    Sans ``mkisofs`` ni ``genisoimage``, aucune instance de type
    ``virtual-machine`` ne démarre : « Neither mkisofs nor genisoimage could be
    found in $PATH ». Rien ne le documentait, et la remédiation d'incus se
    limitait à installer incus.
    """
    for outil in ("genisoimage", "mkisofs", "xorrisofs"):
        if shutil.which(outil):
            return _check("iso_tool", True, outil)
    return _check(
        "iso_tool", False, _("detail_iso_tool_missing"),
        fix=_fix(["sudo", "apt", "install", "genisoimage"]),
    )


def _check_labs(root: Path, labs: list[LabDefinition], vus: int) -> Check:
    """Le compte des labs, et **ce qui manque** quand il ne colle pas.

    Un « 0 lab » muet oblige l'utilisateur à retrouver seul une information que
    `list-labs` possède déjà. Trois causes rendent un lab invisible : un
    `schema_version` trop récent, un `lab.yaml` qui lève au parsing, ou un lab
    déclaré dans le `meta.yml` mais absent du disque. Plutôt que de deviner
    laquelle s'applique, on compare les fichiers présents aux labs chargés :
    l'écart les couvre toutes les trois.
    """
    ecart = vus - len(labs)
    detail = _("detail_labs_count", count=len(labs), root=root)
    if ecart > 0:
        detail += " " + _("detail_labs_ecart", ecart=ecart, presents=vus)
    # Seul un écart POSITIF dit quelque chose : des fichiers présents que le
    # moteur n'a pas su charger. L'inverse ne peut pas venir d'un catalogue réel,
    # et vaut zéro information.
    return _check("labs", len(labs) > 0 and ecart <= 0, detail)


def _check_lab_home(root: Path) -> Check:
    return _check("lab_home", True, str(root))


# ── assemblage ────────────────────────────────────────────────────────────────

def uses_vm(labs: list[LabDefinition]) -> bool:
    """Ce dépôt a-t-il au moins un lab qui exige une VM provisionnée ?"""
    return any(lab.runtime.type in _VM_RUNTIMES for lab in labs)


def _check_git() -> Check:
    """``catalog add`` clone : sans git, la deuxième commande du parcours échoue.

    git n'est pas une dépendance Python — ``uv tool install`` ne l'apporte pas —
    et il ne figurait dans aucun contrôle. Son absence remontait en trace
    Python sur la commande d'accueil, ce qui est le plus mauvais moment pour
    montrer une trace à quelqu'un.
    """
    if shutil.which("git") is None:
        return _check(
            "git", False, _("detail_git_missing"),
            hint="https://git-scm.com/downloads",
        )
    result = _sonder(["git", "--version"])
    if result is None:
        # Présent dans le PATH mais muet : ni vert ni rouge, on ne sait pas.
        return _check("git", False, _("detail_git_muet"), forced_state=STATE_UNKNOWN)
    if result.returncode != 0:
        detail = (result.stderr or result.stdout).strip().splitlines()
        return _check("git", False, detail[-1] if detail else _("detail_git_muet"),
                      hint="https://git-scm.com/downloads")
    return _check("git", True, result.stdout.strip() or "ok")


def uses_services(labs: list[LabDefinition]) -> bool:
    """Ce dépôt a-t-il au moins un lab qui déclare des conteneurs ?

    Lit le contrat, et rien d'autre : le moteur ne sait pas quelles images un
    catalogue déclare, et n'a pas à le savoir.
    """
    return any(lab.runtime.services for lab in labs)


def _check_docker() -> Check:
    """Un lab qui déclare ``runtime.services`` ne démarre pas sans moteur.

    Trois situations, et elles appellent trois gestes différents : le binaire
    n'est pas là (installer), il est là mais le démon ne répond pas (démarrer
    le service, ou se mettre dans le groupe), ou la sonde elle-même n'aboutit
    pas — auquel cas on ne sait pas, et on le dit plutôt que de trancher.
    """
    if shutil.which("docker") is None:
        return _check(
            "docker", False, _("detail_docker_missing"),
            hint="https://docs.docker.com/engine/install/",
        )
    result = _sonder(["docker", "version", "--format", "{{.Server.Version}}"], delai=15)
    if result is None:
        return _check("docker", False, _("detail_docker_muet"), forced_state=STATE_UNKNOWN)
    if result.returncode != 0:
        # Le cas courant : le client répond, le démon non. Le message doit
        # nommer le démon, sinon on cherche un paquet déjà installé.
        detail = (result.stderr or result.stdout).strip().splitlines()
        return _check(
            "docker", False,
            detail[-1] if detail else _("detail_docker_daemon"),
            hint="https://docs.docker.com/engine/install/linux-postinstall/",
        )
    return _check("docker", True, result.stdout.strip() or "ok")


#: Les URL d'images des templates packagés. Le moteur ne **connaît** aucun
#: domaine : il les lit dans les templates, comme il lit le reste du contrat.
_URL_IMAGE = re.compile(r'https://([A-Za-z0-9.-]+)/[^"\s]*\.(?:qcow2|img)')

#: Une sonde d'accès sortant doit être brève : `doctor` en enchaîne déjà
#: plusieurs, et un réseau coupé se constate en deux secondes.
_DELAI_EGRESS = 2.0


def _hotes_images() -> list[str]:
    """Les hôtes que le provisionnement ira chercher, lus dans les templates."""
    racine = Path(__file__).resolve().parent.parent / "templates" / "terraform"
    hotes: list[str] = []
    for chemin in sorted(racine.rglob("*.tf")):
        try:
            contenu = chemin.read_text(encoding="utf-8")
        except OSError:
            continue
        for hote in _URL_IMAGE.findall(contenu):
            if hote not in hotes:
                hotes.append(hote)
    return hotes


def _check_egress() -> Check:
    """Le provisionnement télécharge une image, puis cloud-init des paquets.

    Sans accès sortant — salle de formation fermée, proxy d'entreprise — le
    téléchargement échoue ou cloud-init finit en `degraded`, et les labs
    échouent plus tard sur des commandes absentes. Le dire **avant** de
    provisionner coûte deux secondes et évite de chercher la panne au mauvais
    endroit.

    Un seul hôte joignable suffit à conclure : ce qui est en cause est l'accès
    sortant lui-même, pas la disponibilité d'un miroir en particulier.
    """
    hotes = _hotes_images()
    if not hotes:
        # Aucun template ne déclare d'image : rien à joindre, rien à conclure.
        return _check("egress", False, _("detail_egress_indetermine"),
                      forced_state=STATE_UNKNOWN)
    for hote in hotes:
        try:
            with socket.create_connection((hote, 443), timeout=_DELAI_EGRESS):
                return _check("egress", True, hote)
        except OSError:
            continue
    return _check("egress", False,
                  _("detail_egress_absent", hosts=", ".join(hotes)),
                  hint="https://docs.docker.com/network/proxy/")


def _hypervisor_checks() -> dict[str, Check]:
    return {"kvm": _check_kvm(), "incus": _check_incus()}


def _sort_hypervisors(names: list[str]) -> list[Check]:
    checks = _hypervisor_checks()
    return [checks[n] for n in names if n in checks]


def collect_checks(root: Path, repo_meta: RepoMetadata | None) -> DoctorReport:
    """Construit le diagnostic pour le dépôt de labs situé en ``root``.

    Le classement requis/optionnel dépend de trois faits du dépôt, et
    d'aucune connaissance de son domaine : a-t-il des labs ``vm``, quel
    provider est actif, et quels providers déclare-t-il.
    """
    labs = get_all_labs(root)
    report = DoctorReport()
    report.required.extend([_check_python(), _check_pytest(root), _check_shell()])
    # git sert au parcours d'accueil (`catalog add` clone), quel que soit le
    # domaine du dépôt : il est requis partout.
    report.required.append(_check_git())

    # docker, lui, dépend de ce que le catalogue déclare — jamais de son
    # domaine. Un dépôt sans `runtime.services` n'a aucune raison de voir du
    # rouge pour un moteur qu'il n'utilise pas.
    if uses_services(labs):
        report.required.append(_check_docker())
    else:
        report.optional.append(_check_docker())
        report.notes.append(_("reason_docker_no_services"))

    needs_vm = uses_vm(labs)
    # Le provisionnement télécharge une image puis laisse cloud-init installer
    # des paquets : sans accès sortant, l'hôte est déclaré prêt et les labs
    # échouent plus tard sur des commandes absentes. Un dépôt entièrement
    # `shell` ne provisionne rien, donc n'a pas à en voir du rouge.
    if needs_vm:
        report.required.append(_check_egress())
    else:
        report.optional.append(_check_egress())
        report.notes.append(_("reason_egress_sans_vm"))
    active = repo_meta.infra.provider if repo_meta else ""
    candidates = list(repo_meta.infra.providers_available) if repo_meta else []
    hypervisors = _hypervisor_checks()

    if not needs_vm:
        # Cas d'un catalogue entièrement `shell` : aucun hyperviseur n'est
        # requis, et le dire évite le rouge décourageant du premier lancement.
        report.optional.extend(_sort_hypervisors(list(_LOCAL_HYPERVISORS)))
        report.notes.append(_("doctor_note_no_vm"))
    elif active in hypervisors:
        report.required.append(_check("provider", True, active))
        report.required.append(hypervisors[active])
        report.optional.extend(
            _sort_hypervisors([n for n in _LOCAL_HYPERVISORS if n != active])
        )
        report.notes.append(_("doctor_note_other_providers", provider=active))
    elif active:
        # Provider distant (outscale…) : rien à vérifier localement.
        report.required.append(_check("provider", True, active))
        report.optional.extend(_sort_hypervisors(list(_LOCAL_HYPERVISORS)))
        report.notes.append(_("doctor_note_remote_provider", provider=active))
    else:
        # Plusieurs candidats déclarés, aucun choisi. On ne devine pas à la
        # place de l'apprenant : on nomme le choix qui reste à faire.
        #
        # On arrive ici avec `needs_vm` vrai : un hyperviseur EST indispensable.
        # Les checks restent pourtant hors du requis, et c'est délibéré : les y
        # mettre ferait proposer à `--fix` d'installer kvm **et** incus, pour un
        # choix que l'apprenant n'a pas encore fait. C'est le libellé du tableau
        # qui mentait, en annonçant « non requis ici » et « ces composants ne
        # bloquent rien » au-dessus du composant qui bloque 64 labs sur 84.
        first = candidates[0] if candidates else "kvm"
        report.required.append(_check(
            "provider", False,
            _("detail_provider_unresolved", candidates=", ".join(candidates) or "—"),
            hint=f"dsoxlab use --provider {first}",
            forced_state=STATE_CHOICE_REQUIRED,
        ))
        report.optional.extend(_sort_hypervisors(list(_LOCAL_HYPERVISORS)))
        report.optional_title_key = "doctor_choose_title"
        report.optional_hint_key = "doctor_choose_hint"
        report.notes.append(_("doctor_note_provider_unresolved"))

    # Outillage exigé par `provision` et `run` dès qu'un lab a besoin d'une VM,
    # quel que soit le provider. Ces deux-là manquaient au diagnostic, et leur
    # absence ne se manifestait qu'au premier échec, en langage Terraform ou en
    # `rc=127`.
    if needs_vm:
        report.required.append(_check_terraform())
        report.required.append(_check_ansible())
        # Prérequis matériels d'un hyperviseur local : virtualisation,
        # architecture, ressources. Ils ne dépendent d'aucun binaire installé
        # (/dev/kvm et /proc/meminfo se lisent sans virsh), donc ils parlent
        # même quand l'hyperviseur manque : c'est une cause DIFFÉRENTE, pas le
        # même rouge répété. Un provider distant (outscale…) provisionne
        # ailleurs : rien de tout cela ne concerne alors ce poste.
        if active in _LOCAL_HYPERVISORS:
            report.required.append(_check_hw_virt())
            report.required.append(_check_cpu_arch(active))
            if repo_meta is not None and repo_meta.infra.hosts:
                report.required.append(
                    _check_resources(repo_meta.infra, active)
                )
        # Contrôles propres à un hyperviseur : ils n'ont de sens qu'une fois le
        # provider choisi, sinon ils affichent du rouge pour un backend que ce
        # poste n'utilisera peut-être jamais.
        # Ces contrôles-ci portent sur la CONFIGURATION d'un hyperviseur déjà
        # installé. Les jouer quand l'hyperviseur lui-même manque empilerait
        # trois lignes rouges pour une seule cause, et noierait celle qui
        # compte : c'est exactement ce qui décourageait au premier lancement.
        if active == "kvm" and hypervisors["kvm"].ok:
            pool = "default"
            if repo_meta is not None:
                pool = str(repo_meta.infra.provider_config().get("storage_pool")
                           or "default")
            report.required.append(_check_libvirt_pool(pool))
        elif active == "incus" and hypervisors["incus"].ok:
            report.required.append(_check_iso_tool())

    report.required.append(_check_labs(root, labs, compter_fichiers_labs(root)))
    report.required.append(_check_lab_home(root))
    return report
