"""Modèle de données principal : LabDefinition."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import yaml

from ._contract import as_int, as_mapping, as_mapping_list, as_str_list
from .runtime import RuntimeConfig, RuntimeType, Target


@dataclass
class ValidationConfig:
    functional: bool = True
    security: bool = False
    persistence_after_reboot: bool = False


@dataclass
class LabDefinition:
    id: str
    title: str
    level: str
    skills: list[str]
    runtime: RuntimeConfig
    distros: list[str]
    doc_url: str
    validation: ValidationConfig
    path: Path = field(default_factory=lambda: Path("."))
    section: str = "linux"
    description: str = ""
    track: list[str] = field(default_factory=list)
    difficulty: str = "beginner"
    estimated_time: str = "30m"
    certification_tags: list[str] = field(default_factory=list)

    lab_type: str = "lab"       # "lab" | "challenge" | "capstone"
    bloc: int = 0               # bloc number 1-8; 0 = unassigned
    bloc_order: int = 0         # position within the bloc; 0 = unassigned
    bloc_name: str = ""         # nom lisible du bloc (section meta.yml), ex. "Fondamentaux (l1)"

    # Translatable fields — overridden by lab.<lang>.yaml when available
    _TRANSLATABLE = ("title", "description")

    @classmethod
    def from_yaml(cls, lab_yaml: Path, lang: str = "en") -> "LabDefinition":
        """Load a LabDefinition from a lab.yaml file.

        If ``lang`` != "en" and a ``lab.<lang>.yaml`` file exists in the same
        directory, translatable fields (title, description) are overridden by
        that file.
        """
        with lab_yaml.open(encoding="utf-8") as fh:
            data = yaml.safe_load(fh)

        # Un fichier vide ou réduit à des commentaires donne None ; une racine
        # en liste ou en scalaire donne un list/int. Sans ce garde-fou, l'accès
        # suivant lèverait AttributeError, hors du contrat (KeyError,
        # ValueError, YAMLError) que discovery/scanner.py rattrape : le lab
        # ferait planter la CLI au lieu d'être ignoré avec un warning.
        if not isinstance(data, dict):
            raise ValueError(
                f"{lab_yaml}: le document doit être un mapping YAML "
                f"(reçu : {type(data).__name__})."
            )

        # Fusion des traductions
        if lang and lang != "en":
            lang_yaml = lab_yaml.parent / f"lab.{lang[:2].lower()}.yaml"
            if lang_yaml.exists():
                try:
                    with lang_yaml.open(encoding="utf-8") as fh:
                        overrides = yaml.safe_load(fh)
                    if not isinstance(overrides, dict):
                        overrides = {}
                    for key in cls._TRANSLATABLE:
                        if key in overrides:
                            data[key] = overrides[key]
                except yaml.YAMLError:
                    pass  # fichier de traduction invalide — on garde les valeurs de base

        # `runtime: vm` au lieu du bloc `runtime:\n  type: vm` est la faute la
        # plus naturelle du contrat : elle donne une str, pas un mapping.
        runtime_data = as_mapping(data.get("runtime"), "runtime", lab_yaml)

        targets_raw = as_mapping_list(runtime_data.get("targets"), "runtime.targets", lab_yaml)
        targets: list[Target] = []
        for idx, t in enumerate(targets_raw):
            if "name" not in t or "host" not in t:
                raise ValueError(
                    f"{lab_yaml}: runtime.targets[{idx}] doit contenir "
                    f"'name' et 'host'."
                )
            roles_raw = as_mapping(
                t.get("roles"), f"runtime.targets[{idx}].roles", lab_yaml
            )
            targets.append(Target(
                name=str(t["name"]),
                host=str(t["host"]),
                label_en=str(t.get("label_en", "")),
                label_fr=str(t.get("label_fr", "")),
                roles={str(k): str(v) for k, v in roles_raw.items()},
            ))

        runtime = RuntimeConfig(
            type=RuntimeType(runtime_data.get("type", "shell")),
            targets=targets,
            default=str(runtime_data.get("default", "")),
            snapshot_required=bool(runtime_data.get("snapshot_required", False)),
            session=str(runtime_data.get("session", "target")),
            workdir=runtime_data.get("workdir", "challenge/work"),
            fixtures=as_str_list(runtime_data.get("fixtures"), "runtime.fixtures", lab_yaml),
            topology=runtime_data.get("topology", "local"),
        )

        validation_data = as_mapping(data.get("validation"), "validation", lab_yaml)
        validation = ValidationConfig(
            functional=validation_data.get("functional", True),
            security=validation_data.get("security", False),
            persistence_after_reboot=validation_data.get("persistence_after_reboot", False),
        )

        return cls(
            id=data["id"],
            title=data["title"],
            level=data["level"],
            skills=as_str_list(data.get("skills"), "skills", lab_yaml),
            runtime=runtime,
            distros=as_str_list(data.get("distros"), "distros", lab_yaml),
            doc_url=data.get("doc_url", ""),
            validation=validation,
            path=lab_yaml.parent,
            section=data.get("section", "linux"),
            description=data.get("description", ""),
            track=as_str_list(data.get("track"), "track", lab_yaml),
            difficulty=data.get("difficulty", "beginner"),
            estimated_time=data.get("estimated_time", "30m"),
            certification_tags=as_str_list(
                data.get("certification_tags"), "certification_tags", lab_yaml
            ),
            lab_type=data.get("lab_type", "lab"),
            bloc=as_int(data.get("bloc"), 0, "bloc", lab_yaml),
            bloc_order=as_int(data.get("bloc_order"), 0, "bloc_order", lab_yaml),
        )
