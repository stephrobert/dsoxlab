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
import re
import shlex
import shutil
import subprocess
import sys
from collections.abc import Sequence
from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import Path

from ..discovery.scanner import compter_fichiers_labs
from ..i18n import _
from ..infra import ansible as ansible_infra
from ..models import LabDefinition, RepoMetadata
from ..models.runtime import RuntimeType
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
        return [c for c in self.required if not c.ok]

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
    commande: list[str], *, delai: float = 5
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
            commande, capture_output=True, text=True, timeout=delai, check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return None


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
    result = _sonder(["virsh", "version"])
    if result is None or result.returncode != 0:
        return _check(
            "kvm", False, _("detail_kvm_daemon_err"),
            fix=_fix(["sudo", "systemctl", "start", "libvirtd"]),
        )
    first_line = result.stdout.splitlines()[0] if result.stdout else "ok"
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
    seule cause.
    """
    cmd = ["virsh", "-c", "qemu:///system", "pool-list"]
    if definis:
        cmd.append("--all")
    cmd.append("--name")
    probe = _sonder(cmd)
    if probe is None or probe.returncode != 0:
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
        return _check("libvirt_pool", True, _("detail_pool_unknown"))
    if pool in actifs:
        return _check("libvirt_pool", True, pool)

    definis = _pools_libvirt(definis=True)
    if definis is not None and pool in definis:
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

    needs_vm = uses_vm(labs)
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
