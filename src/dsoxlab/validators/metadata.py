"""Lab metadata validation.

Comme les autres validators, ce module ne compose **aucune phrase** : chaque
anomalie porte une clé i18n et ses paramètres, que ``validate-structure`` rend
dans la langue de l'auteur. Les messages écrits ici en dur sortaient en
français quel que soit ``DSOXLAB_LANG``.
"""

from __future__ import annotations

import dataclasses
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlparse

from ..models.lab import LabDefinition

_VALID_LAB_TYPES = {"lab", "challenge", "capstone"}


@dataclass
class MetadataIssue:
    field: str
    key: str
    """Clé i18n du message, présente dans ``strings/en.py`` ET ``strings/fr.py``."""

    # `dataclasses.field`, en toutes lettres : la dataclass porte un attribut
    # nommé `field`, et le nom court désignerait alors le champ, pas la fonction.
    params: dict[str, Any] = dataclasses.field(default_factory=dict)
    """Paramètres de substitution du message."""


@dataclass
class MetadataReport:
    lab_id: str
    issues: list[MetadataIssue] = dataclasses.field(default_factory=list)

    @property
    def ok(self) -> bool:
        return len(self.issues) == 0


def validate_metadata(lab: LabDefinition) -> MetadataReport:
    """Check required fields and their consistency."""
    report = MetadataReport(lab_id=lab.id)

    for champ, valeur in (
        ("id", lab.id),
        ("title", lab.title),
        ("level", lab.level),
        ("doc_url", lab.doc_url),
    ):
        if not valeur:
            report.issues.append(
                MetadataIssue(champ, "metadata_field_empty", {"field": champ})
            )
    for champ, liste in (("skills", lab.skills), ("distros", lab.distros)):
        if not liste:
            report.issues.append(
                MetadataIssue(champ, "metadata_list_empty", {"field": champ})
            )

    if lab.doc_url:
        parsed = urlparse(lab.doc_url)
        if parsed.scheme not in ("http", "https"):
            report.issues.append(
                MetadataIssue(
                    "doc_url", "metadata_doc_url_scheme", {"url": lab.doc_url}
                )
            )
    if lab.lab_type not in _VALID_LAB_TYPES:
        report.issues.append(
            MetadataIssue(
                "lab_type",
                "metadata_lab_type_invalid",
                {
                    "value": lab.lab_type,
                    "expected": ", ".join(sorted(_VALID_LAB_TYPES)),
                },
            )
        )
    # Le seuil est un POURCENTAGE du barème. Hors de 1..100, il ne veut rien
    # dire : un examen qu'on ne peut jamais réussir, ou qu'on ne peut jamais
    # rater. Le champ absent vaut 0, ce qui est « pas un examen », pas un
    # seuil hors bornes.
    if lab.exam_passing_score and not 1 <= lab.exam_passing_score <= 100:
        report.issues.append(
            MetadataIssue(
                "exam_passing_score",
                "metadata_exam_score_invalid",
                {"value": lab.exam_passing_score},
            )
        )

    return report
