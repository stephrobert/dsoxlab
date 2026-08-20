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
from dataclasses import dataclass, field
from pathlib import Path

import yaml

from ..models.lab import LabDefinition
from ..models.repo import RepoMetadata
from ..models.schema_version import UnsupportedSchemaVersion
from .repo import read_repo_metadata

logger = logging.getLogger(__name__)

# Niveaux connus utilisés en mode legacy uniquement, pour distinguer
# ``labs/<section>/<level>/<lab>`` de ``labs/<level>/<lab>``.
_KNOWN_LEVELS = {"l1", "l2", "l3", "lfcs", "rhcsa", "capstones"}


@dataclass
class CatalogScan:
    """Ce qu'un balayage du catalogue a lu, **et** ce qu'il a dû écarter.

    ``discover_labs`` ne rendait que la liste des labs : un ``lab.yaml`` que le
    moteur ne sait pas lire disparaissait sans laisser de trace exploitable par
    la CLI. Le cas d'un contrat trop récent mérite mieux qu'une absence, parce
    que la réparation n'est pas dans le catalogue mais dans la version de
    l'outil — chose qu'un lab manquant ne dit à personne.
    """

    labs: list[LabDefinition] = field(default_factory=list)

    unsupported: list[UnsupportedSchemaVersion] = field(default_factory=list)
    """Les ``lab.yaml`` écartés parce qu'ils déclarent une version du contrat
    postérieure à celle que ce dsoxlab lit. Le reste du catalogue est servi
    normalement : un lab venu du futur ne doit pas rendre les 283 autres
    injouables, sans quoi aucun auteur ne pourrait jamais en publier un."""


def scan_catalog(
    root: Path,
    lang: str = "en",
    repo_meta: RepoMetadata | None = None,
) -> CatalogScan:
    """Parcourt ``root`` et rend les labs lus **et** ceux écartés faute de version.

    Args:
        root: Répertoire racine du dépôt fournisseur.
        lang: Langue préférée pour les surcharges ``lab.<lang>.yaml``.
        repo_meta: Métadonnées du dépôt déjà chargées. Si ``None``, lues
                   automatiquement depuis ``<root>/meta.yml``.

    Raises:
        UnsupportedSchemaVersion: si c'est le ``meta.yml`` qui déclare une
            version inconnue. Contrairement à un lab isolé, il décrit tout le
            catalogue : ne pas savoir le lire rend tout le reste douteux, donc
            l'erreur remonte au lieu d'être collectée.
    """
    if repo_meta is None:
        repo_meta = read_repo_metadata(root)

    scan = CatalogScan()

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
            scan.labs.append(lab)
        # AVANT le filet générique : UnsupportedSchemaVersion EST un
        # ValueError, et se ferait sinon avaler comme un lab.yaml malformé
        # de plus, alors que la réparation n'a rien à voir.
        except UnsupportedSchemaVersion as exc:
            # En DEBUG, pas en WARNING comme la ligne suivante : ce cas-ci est
            # rendu à l'utilisateur par la CLI, dans SA langue, depuis
            # `scan.unsupported`. Le journaliser plus haut afficherait deux fois
            # la même chose, dont une en français quel que soit DSOXLAB_LANG. La
            # trace reste dans le fichier de journal, qui garde tout le DEBUG.
            logger.debug(
                "lab.yaml écarté (%s) : il déclare schema_version %d, "
                "au-delà de la version %d que ce dsoxlab sait lire.",
                yaml_path, exc.found, exc.supported,
            )
            scan.unsupported.append(exc)
        except (KeyError, ValueError, yaml.YAMLError) as exc:
            logger.warning("lab.yaml ignoré (%s) : %s", yaml_path, exc)

    scan.labs = _sort_labs(scan.labs, root, repo_meta)
    return scan


def discover_labs(
    root: Path,
    lang: str = "en",
    repo_meta: RepoMetadata | None = None,
) -> list[LabDefinition]:
    """Les labs lisibles de ``root``, triés selon l'ordre du ``meta.yml``.

    Enveloppe de :func:`scan_catalog` pour les appelants à qui les fichiers
    écartés n'apprennent rien — la grande majorité. Ceux qui veulent en rendre
    compte à l'utilisateur appellent :func:`scan_catalog`.
    """
    return scan_catalog(root, lang=lang, repo_meta=repo_meta).labs


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
                # Position dans la section, d'où « dsoxlab next » tire l'ordre
                # pédagogique. Sans elle, le tri retombait sur l'id, donc sur
                # l'alphabet : « ansible-vault » était proposé avant
                # « premier-playbook », et « bash-script » avant
                # « discover-linux-map ». Le meta.yml est censé piloter cet
                # ordre ; il le pilote désormais vraiment, sans qu'aucun
                # lab.yaml n'ait à recopier l'information.
                # Un bloc_order explicite dans le lab.yaml reste prioritaire.
                lab.bloc_order = lab.bloc_order or (section.labs.index(rel) + 1)
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
