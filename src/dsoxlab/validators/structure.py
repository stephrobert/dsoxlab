"""Validation de la structure physique d'un lab.

Le validator vérifie le **contrat dsoxlab** que chaque lab doit
respecter. Le contrat dépend du type de runtime déclaré dans
``lab.yaml`` :

- ``runtime: vm`` (et alias ``kvm``/``incus``) → ``setup.yaml`` et
  ``cleanup.yaml`` à la racine du lab (playbooks Ansible).
- ``runtime: shell`` → préparation déclarée dans ``lab.yaml``
  (``runtime.workdir``, ``runtime.fixtures``). Aucun script bash
  requis ni accepté.

Dans les deux cas, ``challenge/tests/test_functional.py`` est
obligatoire pour la validation pytest+testinfra.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from ..models.lab import LabDefinition
from ..models.runtime import RuntimeType


@dataclass
class StructureIssue:
    path: Path
    message: str


@dataclass
class StructureReport:
    lab_id: str
    issues: list[StructureIssue] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return len(self.issues) == 0


def validate_structure(lab: LabDefinition) -> StructureReport:
    """Vérifie que le répertoire du lab respecte le contrat dsoxlab."""
    report = StructureReport(lab_id=lab.id)
    base = lab.path

    # ── Fichiers communs à tous les types de runtime ─────────────────
    _require_file(base / "lab.yaml", report)
    _require_file(base / "README.md", report)
    _require_file(base / "scenario.md", report)
    _require_dir(base / "challenge" / "tests", report)
    _require_file(base / "challenge" / "tests" / "test_functional.py", report)

    # ── Spécifique au type de runtime ────────────────────────────────
    rt_type = lab.runtime.type

    if rt_type in (RuntimeType.VM, RuntimeType.KVM, RuntimeType.INCUS):
        # Runtime VM : playbooks Ansible obligatoires, zéro bash.
        _require_file(base / "setup.yaml", report)
        _require_file(base / "cleanup.yaml", report)
        # runtime.targets[] non vide pour les VMs (l'apprenant doit
        # pouvoir choisir une target)
        if not lab.runtime.targets:
            report.issues.append(
                StructureIssue(
                    path=base / "lab.yaml",
                    message=(
                        "runtime.type est 'vm' mais runtime.targets[] "
                        "est vide. Déclare au moins une target avec "
                        "{name, host}."
                    ),
                )
            )
        # Si default défini, doit matcher un name de target
        if lab.runtime.default:
            target_names = [t.name for t in lab.runtime.targets]
            if lab.runtime.default not in target_names:
                report.issues.append(
                    StructureIssue(
                        path=base / "lab.yaml",
                        message=(
                            f"runtime.default='{lab.runtime.default}' "
                            f"ne matche aucun runtime.targets[].name. "
                            f"Disponibles : {target_names}"
                        ),
                    )
                )
        # runtime.session : énuméré. Une valeur libre passerait silencieusement
        # et retomberait sur la session SSH, soit l'inverse de l'intention.
        if lab.runtime.session not in ("target", "local"):
            report.issues.append(
                StructureIssue(
                    path=base / "lab.yaml",
                    message=(
                        f"runtime.session='{lab.runtime.session}' inconnu. "
                        "Valeurs acceptées : 'target' (session SSH sur "
                        "targets[].host, défaut) ou 'local' (sous-shell sur le "
                        "poste, pour un lab piloté depuis le dépôt)."
                    ),
                )
            )
        # Présence interdite de scripts bash legacy (signal de migration
        # incomplète vers le tout-déclaratif).
        _forbid_file(base / "cleanup.sh", report,
                     "cleanup.sh interdit pour runtime: vm — utilise cleanup.yaml.")
        _forbid_file(base / "runtime" / "kvm.sh", report,
                     "runtime/kvm.sh interdit — utilise setup.yaml.")
        _forbid_file(base / "runtime" / "incus.sh", report,
                     "runtime/incus.sh interdit — utilise setup.yaml.")
        _forbid_file(base / "Makefile", report,
                     "Makefile interdit dans un lab — dsoxlab pilote tout.")

    elif rt_type == RuntimeType.SHELL:
        # Runtime shell : tout déclaratif via lab.yaml, aucun script
        # bash dans le lab. workdir doit être défini (a une valeur par
        # défaut "challenge/work" mais on le valide explicite).
        if not lab.runtime.workdir:
            report.issues.append(
                StructureIssue(
                    path=base / "lab.yaml",
                    message=(
                        "runtime.type est 'shell' mais runtime.workdir "
                        "est vide. Déclare le répertoire de travail "
                        "(ex. workdir: challenge/work)."
                    ),
                )
            )
        # Idem : signaler les scripts bash résiduels.
        _forbid_file(base / "cleanup.sh", report,
                     "cleanup.sh interdit pour runtime: shell — déclare "
                     "fixtures dans lab.yaml.")
        _forbid_file(base / "runtime" / "shell.sh", report,
                     "runtime/shell.sh interdit — la préparation est "
                     "déclarée via runtime.workdir + runtime.fixtures.")
        _forbid_file(base / "Makefile", report,
                     "Makefile interdit dans un lab — dsoxlab pilote tout.")

    return report


def _require_file(path: Path, report: StructureReport) -> None:
    if not path.is_file():
        report.issues.append(
            StructureIssue(path=path, message=f"Fichier manquant : {path.name}")
        )


def _require_dir(path: Path, report: StructureReport) -> None:
    if not path.is_dir():
        report.issues.append(
            StructureIssue(path=path, message=f"Répertoire manquant : {path.name}/")
        )


def _forbid_file(path: Path, report: StructureReport, message: str) -> None:
    """Inverse de _require_file : signale la présence d'un fichier interdit."""
    if path.exists():
        report.issues.append(StructureIssue(path=path, message=message))
