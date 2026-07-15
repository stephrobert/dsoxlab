"""Modèle de données principal : LabDefinition."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import yaml

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

        # Fusion des traductions
        if lang and lang != "en":
            lang_yaml = lab_yaml.parent / f"lab.{lang[:2].lower()}.yaml"
            if lang_yaml.exists():
                try:
                    with lang_yaml.open(encoding="utf-8") as fh:
                        overrides = yaml.safe_load(fh) or {}
                    for key in cls._TRANSLATABLE:
                        if key in overrides:
                            data[key] = overrides[key]
                except yaml.YAMLError:
                    pass  # fichier de traduction invalide — on garde les valeurs de base

        runtime_data = data.get("runtime", {}) or {}

        targets_raw = runtime_data.get("targets") or []
        targets: list[Target] = []
        for idx, t in enumerate(targets_raw):
            if not isinstance(t, dict):
                raise ValueError(
                    f"{lab_yaml}: runtime.targets[{idx}] doit être un dict, "
                    f"reçu : {type(t).__name__}"
                )
            if "name" not in t or "host" not in t:
                raise ValueError(
                    f"{lab_yaml}: runtime.targets[{idx}] doit contenir "
                    f"'name' et 'host'."
                )
            targets.append(Target(
                name=str(t["name"]),
                host=str(t["host"]),
                label_en=str(t.get("label_en", "")),
                label_fr=str(t.get("label_fr", "")),
            ))

        runtime = RuntimeConfig(
            type=RuntimeType(runtime_data.get("type", "shell")),
            targets=targets,
            default=str(runtime_data.get("default", "")),
            snapshot_required=bool(runtime_data.get("snapshot_required", False)),
            workdir=runtime_data.get("workdir", "challenge/work"),
            fixtures=list(runtime_data.get("fixtures") or []),
            topology=runtime_data.get("topology", "local"),
        )

        validation_data = data.get("validation", {})
        validation = ValidationConfig(
            functional=validation_data.get("functional", True),
            security=validation_data.get("security", False),
            persistence_after_reboot=validation_data.get("persistence_after_reboot", False),
        )

        return cls(
            id=data["id"],
            title=data["title"],
            level=data["level"],
            skills=data.get("skills", []),
            runtime=runtime,
            distros=data.get("distros", []),
            doc_url=data.get("doc_url", ""),
            validation=validation,
            path=lab_yaml.parent,
            section=data.get("section", "linux"),
            description=data.get("description", ""),
            track=data.get("track", []),
            difficulty=data.get("difficulty", "beginner"),
            estimated_time=data.get("estimated_time", "30m"),
            certification_tags=data.get("certification_tags", []),
            lab_type=data.get("lab_type", "lab"),
            bloc=int(data.get("bloc", 0)),
            bloc_order=int(data.get("bloc_order", 0)),
        )
