"""Modèle CourseManifest — structure d'un cours multi-sections."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import yaml


@dataclass
class CourseSection:
    id: str
    title: str
    file: str  # chemin relatif depuis la racine du lab


@dataclass
class CourseManifest:
    title: str
    sections: list[CourseSection] = field(default_factory=list)

    @classmethod
    def load(cls, lab_path: Path, lang: str = "en") -> "CourseManifest | None":
        """Charge course.yaml (EN) puis fusionne course.fr.yaml si lang == 'fr'."""
        course_yaml = lab_path / "course.yaml"
        if not course_yaml.exists():
            return None

        data = yaml.safe_load(course_yaml.read_text(encoding="utf-8")) or {}

        # Fusion des surcharges FR
        if lang == "fr":
            fr_yaml = lab_path / "course.fr.yaml"
            if fr_yaml.exists():
                fr_data = yaml.safe_load(fr_yaml.read_text(encoding="utf-8")) or {}
                if "title" in fr_data:
                    data["title"] = fr_data["title"]
                # Merge section overrides par id
                fr_sections_by_id = {
                    s["id"]: s
                    for s in fr_data.get("sections", [])
                    if "id" in s
                }
                for s in data.get("sections", []):
                    sid = s.get("id")
                    if sid and sid in fr_sections_by_id:
                        override = fr_sections_by_id[sid]
                        if "title" in override:
                            s["title"] = override["title"]
                        if "file" in override:
                            s["file"] = override["file"]

        sections = [
            CourseSection(
                id=s.get("id", str(i + 1)),
                title=s.get("title", ""),
                file=s.get("file", ""),
            )
            for i, s in enumerate(data.get("sections", []))
        ]
        return cls(title=data.get("title", ""), sections=sections)

    def resolve_section(self, key: str) -> CourseSection | None:
        """Retrouve une section par son id (str) ou son numéro (1-based)."""
        if key.isdigit():
            idx = int(key) - 1
            if 0 <= idx < len(self.sections):
                return self.sections[idx]
        for s in self.sections:
            if s.id == key:
                return s
        return None
