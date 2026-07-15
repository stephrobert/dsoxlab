"""Découverte automatique des labs dans le dépôt fournisseur.

Mode privilégié : lit le ``meta.yml`` racine, en déduit la catégorie et
l'ordre des sections, scanne les ``lab.yaml`` du système de fichiers,
et trie selon ``meta.sections.*.labs``.

Mode legacy (compat) : si aucun ``meta.yml`` racine, infère la section
depuis la position du ``lab.yaml`` dans l'arborescence (ancien
``linux-training`` pré-extraction).
"""

from __future__ import annotations

import logging
from pathlib import Path

import yaml

from ..models.lab import LabDefinition
from ..models.repo import RepoMetadata
from .repo import read_repo_metadata

logger = logging.getLogger(__name__)

# Niveaux connus utilisés en mode legacy uniquement, pour distinguer
# ``labs/<section>/<level>/<lab>`` de ``labs/<level>/<lab>``.
_KNOWN_LEVELS = {"l1", "l2", "l3", "lfcs", "rhcsa", "capstones"}


def discover_labs(
    root: Path,
    lang: str = "en",
    repo_meta: RepoMetadata | None = None,
) -> list[LabDefinition]:
    """Parcourt ``root`` à la recherche de labs valides.

    Args:
        root: Répertoire racine du dépôt fournisseur.
        lang: Langue préférée pour les surcharges ``lab.<lang>.yaml``.
        repo_meta: Métadonnées du dépôt déjà chargées. Si ``None``, lues
                   automatiquement depuis ``<root>/meta.yml``.

    Returns:
        Liste triée selon l'ordre déclaré dans ``meta.sections`` si
        présent, sinon par ``(section, level, id)``.
    """
    if repo_meta is None:
        repo_meta = read_repo_metadata(root)

    labs: list[LabDefinition] = []

    search_paths: list[Path] = []
    if (root / "labs").exists():
        search_paths += list((root / "labs").glob("**/*.yaml"))
    # Compat : tp-* à la racine (anciens dépôts)
    search_paths += list(root.glob("tp-*/lab.yaml"))

    for yaml_path in search_paths:
        if yaml_path.name != "lab.yaml":
            continue
        try:
            lab = LabDefinition.from_yaml(yaml_path, lang=lang)
            _assign_section(lab, yaml_path, root, repo_meta)
            labs.append(lab)
        except (KeyError, ValueError, yaml.YAMLError) as exc:
            logger.warning("lab.yaml ignoré (%s) : %s", yaml_path, exc)

    return _sort_labs(labs, root, repo_meta)


def _assign_section(
    lab: LabDefinition,
    yaml_path: Path,
    root: Path,
    repo_meta: RepoMetadata | None,
) -> None:
    """Affecte la section finale du lab.

    - Si ``meta.yml`` présent : valeur ``repo.category`` du dépôt prise par
      défaut quand le ``lab.yaml`` n'override pas la section.
    - Sinon (mode legacy) : infère depuis le chemin
      ``labs/<section>/<level>/<lab>``.
    """
    if repo_meta is not None:
        # En mode framework, le lab.yaml peut surcharger via ``section:`` ;
        # par défaut on prend la catégorie du dépôt.
        if not lab.section or lab.section == "linux":
            lab.section = repo_meta.category
        # Rattache le lab à sa section pédagogique du meta.yml (l1, l2, …) pour
        # que ``dsoxlab progress`` affiche un nom de bloc clair au lieu de « ? ».
        try:
            rel = yaml_path.parent.relative_to(root / "labs").as_posix()
        except ValueError:
            rel = ""
        for idx, section in enumerate(repo_meta.sections, start=1):
            if rel in section.labs:
                lab.bloc = lab.bloc or idx
                lab.bloc_name = section.title or section.id
                break
        return

    # Mode legacy : inférence depuis le chemin (compat ancienne
    # arborescence sans meta.yml racine).
    if lab.section == "linux":
        inferred = _infer_section_legacy(yaml_path, root)
        if inferred != "linux":
            lab.section = inferred


def _infer_section_legacy(yaml_path: Path, root: Path) -> str:
    """Infère la section depuis la position du lab.yaml (mode legacy)."""
    try:
        parts = yaml_path.relative_to(root / "labs").parts
    except ValueError:
        return "linux"
    if not parts:
        return "linux"
    # ``labs/<section>/<level>/<lab>/lab.yaml`` → parts[0] = section
    if len(parts) >= 3 and parts[0] not in _KNOWN_LEVELS:
        return parts[0]
    return "linux"


def _sort_labs(
    labs: list[LabDefinition],
    root: Path,
    repo_meta: RepoMetadata | None,
) -> list[LabDefinition]:
    """Trie les labs.

    Si ``meta.yml`` déclare des sections avec des labs ordonnés, l'ordre
    pédagogique du ``meta.yml`` prévaut. Sinon, tri par
    ``(section, level, id)``.
    """
    if repo_meta and repo_meta.sections:
        order = repo_meta.lab_order()
        labs_dir = root / "labs"

        def sort_key(lab: LabDefinition) -> tuple[int, str, str]:
            try:
                rel = lab.path.resolve().relative_to(labs_dir.resolve()).as_posix()
            except ValueError:
                rel = lab.id
            return (order.get(rel, 1_000_000), lab.level, lab.id)

        return sorted(labs, key=sort_key)

    return sorted(labs, key=lambda lab: (lab.section, lab.level, lab.id))
