"""Modèle CourseManifest — structure d'un cours multi-sections."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import yaml


def _surcharger(data: dict[str, object], fichier: Path) -> None:
    """Applique les surcharges d'une langue sur le manifeste déjà chargé.

    Les sections sont appariées **par `id`**, jamais par position : un
    `course.fr.yaml` qui n'en traduit que deux sur six resterait sinon aligné
    par hasard, puis se décalerait silencieusement au premier ajout. Seuls
    `title` et `file` sont surchargeables ; tout autre champ d'une traduction
    est ignoré, comme pour `lab.fr.yaml` et `meta.fr.yml`.

    Le fichier absent n'est pas une erreur : une langue sans traduction retombe
    sur l'original, et c'est le cas des 374 labs d'aujourd'hui.
    """
    if not fichier.exists():
        return
    traduction = yaml.safe_load(fichier.read_text(encoding="utf-8")) or {}
    if "title" in traduction:
        data["title"] = traduction["title"]

    par_id = {s["id"]: s for s in traduction.get("sections", []) if "id" in s}
    sections = data.get("sections")
    if not par_id or not isinstance(sections, list):
        return
    for section in sections:
        surcharge = par_id.get(section.get("id"))
        if surcharge is None:
            continue
        for champ in ("title", "file"):
            if champ in surcharge:
                section[champ] = surcharge[champ]


@dataclass
class CourseSection:
    id: str
    title: str
    file: str  # chemin relatif depuis la racine du lab

    contenu: str | None = None
    """Le texte de la section, quand il ne vient pas d'un fichier.

    Un ``course.yaml`` pointe un fichier par section ; un découpage déduit des
    titres du cours (``services.course_service``) n'a aucun fichier à pointer
    et porte donc son texte. L'affichage préfère ce champ quand il est posé, et
    tout le reste de la mécanique de navigation ignore la différence.
    """


@dataclass
class CourseManifest:
    title: str
    sections: list[CourseSection] = field(default_factory=list)

    automatique: bool = False
    """Ce découpage a-t-il été déduit, faute de ``course.yaml`` ?

    L'affichage le dit à l'apprenant : un sommaire que personne n'a écrit peut
    tomber à côté, et il vaut mieux l'annoncer que laisser croire à un choix
    de l'auteur.
    """

    @classmethod
    def load(cls, lab_path: Path, lang: str = "en") -> CourseManifest | None:
        """Charge course.yaml (EN) puis fusionne course.fr.yaml si lang == 'fr'."""
        course_yaml = lab_path / "course.yaml"
        if not course_yaml.exists():
            return None

        data = yaml.safe_load(course_yaml.read_text(encoding="utf-8")) or {}
        if lang == "fr":
            _surcharger(data, lab_path / "course.fr.yaml")

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
