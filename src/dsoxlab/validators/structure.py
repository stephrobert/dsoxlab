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
from typing import Any

from ..models.lab import LabDefinition
from ..models.runtime import RuntimeType


@dataclass
class StructureIssue:
    """Une anomalie de structure, prête à être traduite.

    Porte une **clé** et ses paramètres, jamais une phrase : ce rapport est
    affiché par ``validate-structure``, donc son texte suit ``DSOXLAB_LANG``.
    Les messages écrits ici en dur s'affichaient en français sous
    ``DSOXLAB_LANG=en``, c'est-à-dire au moment précis où un auteur découvre
    le contrat.
    """

    path: Path
    key: str
    """Clé i18n du message, présente dans ``strings/en.py`` ET ``strings/fr.py``."""

    params: dict[str, Any] = field(default_factory=dict)
    """Paramètres de substitution du message."""


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
                StructureIssue(path=base / "lab.yaml", key="struct_vm_targets_empty")
            )
        # Si default défini, doit matcher un name de target
        if lab.runtime.default:
            target_names = [t.name for t in lab.runtime.targets]
            if lab.runtime.default not in target_names:
                report.issues.append(
                    StructureIssue(
                        path=base / "lab.yaml",
                        key="struct_default_unknown",
                        params={
                            "default": lab.runtime.default,
                            "available": ", ".join(target_names),
                        },
                    )
                )
        # runtime.session : énuméré. Une valeur libre passerait silencieusement
        # et retomberait sur la session SSH, soit l'inverse de l'intention.
        if lab.runtime.session not in ("target", "local"):
            report.issues.append(
                StructureIssue(
                    path=base / "lab.yaml",
                    key="struct_session_unknown",
                    params={"session": lab.runtime.session},
                )
            )
        # Présence interdite de scripts bash legacy (signal de migration
        # incomplète vers le tout-déclaratif).
        _forbid_file(base / "cleanup.sh", report, "struct_forbidden_cleanup_sh_vm")
        _forbid_file(base / "runtime" / "kvm.sh", report, "struct_forbidden_kvm_sh")
        _forbid_file(base / "runtime" / "incus.sh", report, "struct_forbidden_incus_sh")
        _forbid_file(base / "Makefile", report, "struct_forbidden_makefile")

    elif rt_type == RuntimeType.SHELL:
        # Runtime shell : tout déclaratif via lab.yaml, aucun script
        # bash dans le lab. workdir doit être défini (a une valeur par
        # défaut "challenge/work" mais on le valide explicite).
        if not lab.runtime.workdir:
            report.issues.append(
                StructureIssue(path=base / "lab.yaml", key="struct_shell_workdir_empty")
            )
        # Idem : signaler les scripts bash résiduels.
        _forbid_file(base / "cleanup.sh", report, "struct_forbidden_cleanup_sh_shell")
        _forbid_file(base / "runtime" / "shell.sh", report, "struct_forbidden_shell_sh")
        _forbid_file(base / "Makefile", report, "struct_forbidden_makefile")

    return report


def _require_file(path: Path, report: StructureReport) -> None:
    if not path.is_file():
        report.issues.append(
            StructureIssue(
                path=path, key="struct_missing_file", params={"name": path.name}
            )
        )


def _require_dir(path: Path, report: StructureReport) -> None:
    if not path.is_dir():
        report.issues.append(
            StructureIssue(
                path=path, key="struct_missing_dir", params={"name": path.name}
            )
        )


def _forbid_file(path: Path, report: StructureReport, key: str) -> None:
    """Inverse de _require_file : signale la présence d'un fichier interdit.

    Prend une **clé**, pas une phrase : chaque fichier interdit a son message,
    et c'est la couche d'affichage qui le dit dans la langue de l'auteur.
    """
    if path.exists():
        report.issues.append(StructureIssue(path=path, key=key))
