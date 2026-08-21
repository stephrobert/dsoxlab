"""Lab metadata validation."""

from __future__ import annotations

from dataclasses import dataclass, field
from urllib.parse import urlparse

from ..models.lab import LabDefinition

_VALID_LAB_TYPES = {"lab", "challenge", "capstone"}


@dataclass
class MetadataIssue:
    field: str
    message: str


@dataclass
class MetadataReport:
    lab_id: str
    issues: list[MetadataIssue] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return len(self.issues) == 0


def validate_metadata(lab: LabDefinition) -> MetadataReport:
    """Check required fields and their consistency."""
    report = MetadataReport(lab_id=lab.id)

    if not lab.id:
        report.issues.append(MetadataIssue("id", "Le champ 'id' est vide"))
    if not lab.title:
        report.issues.append(MetadataIssue("title", "Le champ 'title' est vide"))
    if not lab.level:
        report.issues.append(MetadataIssue("level", "Le champ 'level' est vide"))
    if not lab.skills:
        report.issues.append(MetadataIssue("skills", "La liste 'skills' est vide"))
    if not lab.distros:
        report.issues.append(MetadataIssue("distros", "La liste 'distros' est vide"))
    if not lab.doc_url:
        report.issues.append(MetadataIssue("doc_url", "Le champ 'doc_url' est vide"))
    else:
        parsed = urlparse(lab.doc_url)
        if parsed.scheme not in ("http", "https"):
            report.issues.append(
                MetadataIssue("doc_url", f"URL invalide (scheme attendu http/https) : {lab.doc_url}")
            )
    if lab.lab_type not in _VALID_LAB_TYPES:
        report.issues.append(
            MetadataIssue(
                "lab_type",
                f"Invalid value '{lab.lab_type}'. Expected one of: {', '.join(sorted(_VALID_LAB_TYPES))}",
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
                f"Invalid value '{lab.exam_passing_score}'. Expected a percentage "
                f"of the lab scale, between 1 and 100 (omit the field for a lab "
                f"that is not an exam).",
            )
        )

    return report
