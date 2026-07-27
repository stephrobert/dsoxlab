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

import os
import shutil
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path

from ..i18n import _
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


@dataclass(frozen=True)
class Check:
    """Un composant diagnostiqué.

    ``fix`` est une commande shell que ``--fix`` peut exécuter telle quelle.
    ``hint`` est une consigne affichée mais **jamais** exécutée : réinstaller
    l'outil ou choisir un provider sont des gestes que l'apprenant doit
    poser lui-même.
    """

    label: str
    ok: bool
    detail: str
    fix: str | None = None
    hint: str | None = None
    status_key: str | None = None
    """Clé i18n du statut, quand « KO » serait faux. Un provider qui reste
    à choisir bloque bien le provisionnement, mais rien n'est cassé : le
    dire en rouge revient à traiter une décision comme une panne."""

    @property
    def remediation(self) -> str:
        """Ce qu'affiche la colonne « Remédiation »."""
        return self.fix or self.hint or ""


@dataclass
class DoctorReport:
    """Le diagnostic, séparé en ce qui bloque et ce qui informe."""

    required: list[Check] = field(default_factory=list)
    optional: list[Check] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)
    """Phrases qui expliquent *pourquoi* un composant est informatif ici."""

    def failing(self) -> list[Check]:
        return [c for c in self.required if not c.ok]

    def fixable(self) -> list[Check]:
        return [c for c in self.required if not c.ok and c.fix]


# ── checks unitaires ──────────────────────────────────────────────────────────

def _check_python() -> Check:
    return Check(_("check_python"), True, sys.version.split()[0])


def _check_pytest(root: Path) -> Check:
    """Diagnostique pytest par la résolution qu'utilise réellement ``check``."""
    cmd = resolve_pytest_cmd(root)
    if cmd is None:
        return Check(
            _("check_pytest"), False, _("detail_pytest_missing"),
            hint="uv tool install --force dsoxlab",
        )
    if cmd[0] == sys.executable:
        return Check(_("check_pytest"), True, _("detail_pytest_bundled"))
    return Check(_("check_pytest"), True, _("detail_pytest_via", cmd=" ".join(cmd)))


def _check_shell() -> Check:
    return Check(_("check_shell"), True, _("detail_shell_always"))


def _check_incus() -> Check:
    """Binaire + daemon + permissions user + init storage/network.

    Un simple ``which incus`` ne suffit pas : sans daemon actif ni
    appartenance au groupe ``incus``, le client ne peut rien faire
    (« permissions to talk to the incus daemon »).
    """
    if not shutil.which("incus"):
        return Check(
            _("check_incus"), False, _("detail_incus_missing"),
            fix="sudo apt install incus",
        )

    ver = subprocess.run(
        ["incus", "--version"], capture_output=True, text=True, timeout=5,
    )
    version = ver.stdout.strip() or "?"

    probe = subprocess.run(
        ["incus", "list"], capture_output=True, text=True, timeout=5,
    )
    if probe.returncode == 0:
        return Check(_("check_incus"), True, _("detail_incus_ok", version=version))

    err = (probe.stderr or "").lower()
    if "permission" in err or "socket" in err:
        # Soit daemon inactif, soit user hors du groupe : deux causes,
        # deux remédiations, que l'erreur seule ne distingue pas.
        daemon_active = subprocess.run(
            ["systemctl", "is-active", "--quiet", "incus.service"],
        ).returncode == 0
        if not daemon_active:
            return Check(
                _("check_incus"), False,
                _("detail_incus_daemon_down", version=version),
                fix="sudo systemctl enable --now incus.service",
            )
        return Check(
            _("check_incus"), False,
            _("detail_incus_no_group", version=version),
            fix=f"sudo usermod -aG incus,incus-admin {os.environ.get('USER', '$USER')}",
        )
    if "no storage pools" in err or "init" in err:
        return Check(
            _("check_incus"), False,
            _("detail_incus_no_init", version=version),
            fix="sudo incus admin init --auto",
        )

    tail = (probe.stderr or probe.stdout).strip().splitlines()
    return Check(_("check_incus"), False, tail[-1] if tail else _("detail_unknown_error"))


def _check_kvm() -> Check:
    if not shutil.which("virsh"):
        return Check(
            _("check_kvm"), False, _("detail_kvm_missing"),
            fix="sudo apt install libvirt-clients libvirt-daemon-system qemu-kvm",
        )
    result = subprocess.run(
        ["virsh", "version"], capture_output=True, text=True, timeout=5,
    )
    if result.returncode != 0:
        return Check(
            _("check_kvm"), False, _("detail_kvm_daemon_err"),
            fix="sudo systemctl start libvirtd",
        )
    first_line = result.stdout.splitlines()[0] if result.stdout else "ok"
    return Check(_("check_kvm"), True, first_line)


def _check_labs(root: Path, labs: list[LabDefinition]) -> Check:
    return Check(
        _("check_labs"), len(labs) > 0,
        _("detail_labs_count", count=len(labs), root=root),
    )


def _check_lab_home(root: Path) -> Check:
    return Check(_("check_lab_home"), True, str(root))


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
        report.required.append(Check(_("check_provider"), True, active))
        report.required.append(hypervisors[active])
        report.optional.extend(
            _sort_hypervisors([n for n in _LOCAL_HYPERVISORS if n != active])
        )
        report.notes.append(_("doctor_note_other_providers", provider=active))
    elif active:
        # Provider distant (outscale…) : rien à vérifier localement.
        report.required.append(Check(_("check_provider"), True, active))
        report.optional.extend(_sort_hypervisors(list(_LOCAL_HYPERVISORS)))
        report.notes.append(_("doctor_note_remote_provider", provider=active))
    else:
        # Plusieurs candidats déclarés, aucun choisi. On ne devine pas à la
        # place de l'apprenant : on nomme le choix qui reste à faire.
        first = candidates[0] if candidates else "kvm"
        report.required.append(Check(
            _("check_provider"), False,
            _("detail_provider_unresolved", candidates=", ".join(candidates) or "—"),
            hint=f"dsoxlab use --provider {first}",
            status_key="status_choose",
        ))
        report.optional.extend(_sort_hypervisors(list(_LOCAL_HYPERVISORS)))
        report.notes.append(_("doctor_note_provider_unresolved"))

    report.required.append(_check_labs(root, labs))
    report.required.append(_check_lab_home(root))
    return report
