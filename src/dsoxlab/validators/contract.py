"""Contrôle de la version du contrat, lue **à la source**.

Les autres validators itèrent sur ``discover_labs()``, donc sur ce qui a déjà
été chargé avec succès : un ``lab.yaml`` qui lève au parsing traverse toute la
validation sans un mot. C'est exactement le sort d'un fichier dont le
``schema_version`` est illisible ou trop récent : il n'existe plus pour le reste
de la chaîne, et le seul symptôme est un lab absent de ``list-labs``.

Ce contrôle-ci relit donc les fichiers du catalogue directement, avant toute
découverte, et ne regarde qu'une chose : le numéro de version du contrat. Il
voit ce que les autres ne peuvent pas voir.

Il ne compose aucune phrase : chaque anomalie porte une **clé i18n** et ses
paramètres, que la CLI rend dans la langue de l'apprenant. Un validator qui
écrirait ses messages en dur les afficherait dans une seule langue.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

from ..models.schema_version import (
    SUPPORTED_SCHEMA_VERSION,
    UnsupportedSchemaVersion,
    read_schema_version,
)


@dataclass(frozen=True)
class ContractIssue:
    """Une anomalie de version de contrat, prête à être traduite."""

    path: Path
    key: str
    """Clé i18n du message, présente dans ``strings/en.py`` ET ``strings/fr.py``."""

    params: dict[str, Any] = field(default_factory=dict)
    """Paramètres de substitution du message."""


@dataclass
class ContractReport:
    issues: list[ContractIssue] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.issues

    @property
    def meta_is_unreadable(self) -> bool:
        """Le ``meta.yml`` lui-même est-il en cause ?

        Il décrit tout le catalogue : ne pas savoir le lire rend chaque
        contrôle suivant douteux, alors qu'un lab isolé n'empêche pas de
        valider les autres. La CLI s'arrête dans un cas, poursuit dans l'autre.
        """
        return any(issue.path.name == "meta.yml" for issue in self.issues)


def _documents(root: Path) -> list[Path]:
    """Les fichiers du contrat, ``meta.yml`` puis les ``lab.yaml``.

    Même parcours que ``discovery/scanner.py``, y compris les ``tp-*`` de
    rétro-compat : un contrôle qui regarderait moins de fichiers que le moteur
    laisserait passer précisément ceux qu'il faut signaler.
    """
    documents: list[Path] = []
    meta = root / "meta.yml"
    if meta.is_file():
        documents.append(meta)
    if (root / "labs").exists():
        documents += sorted(
            chemin
            for chemin in (root / "labs").glob("**/*.yaml")
            if chemin.name == "lab.yaml"
        )
    documents += sorted(root.glob("tp-*/lab.yaml"))
    return documents


def validate_schema_versions(root: Path) -> ContractReport:
    """Signale tout ``schema_version`` non entier ou inconnu du catalogue.

    Un document illisible pour une autre raison (YAML cassé, racine qui n'est
    pas un mapping) n'est **pas** rapporté ici : ce n'est pas le sujet de ce
    contrôle, et les validators de structure le signalent déjà à leur manière.
    """
    report = ContractReport()

    for chemin in _documents(root):
        try:
            data = yaml.safe_load(chemin.read_text(encoding="utf-8"))
        except (OSError, yaml.YAMLError):
            continue  # hors sujet : ce contrôle ne parle que de version
        if not isinstance(data, dict):
            continue

        try:
            read_schema_version(data, chemin)
        except UnsupportedSchemaVersion as exc:
            report.issues.append(ContractIssue(
                path=chemin,
                key="schema_version_too_new",
                params={"found": exc.found, "supported": exc.supported},
            ))
        except ValueError:
            # Le message du modèle est technique et non traduit : on ne le
            # relaie pas, on nomme la valeur fautive et la CLI dit le reste.
            report.issues.append(ContractIssue(
                path=chemin,
                key="schema_version_invalid",
                params={
                    "got": repr(data.get("schema_version")),
                    "supported": SUPPORTED_SCHEMA_VERSION,
                },
            ))

    return report
