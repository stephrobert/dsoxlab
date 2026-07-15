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

    return report
