"""Lecture du meta.yml racine du dépôt fournisseur.

Le ``meta.yml`` racine est le contrat déclaratif que chaque dépôt
fournisseur de labs doit respecter. Voir
``dsoxlab/models/repo.py`` pour le schéma complet.
"""

from __future__ import annotations

import logging
from pathlib import Path

from ..models.repo import RepoMetadata

logger = logging.getLogger(__name__)


def find_meta_yml(start: Path) -> Path | None:
    """Remonte les parents pour trouver un ``meta.yml``.

    Cherche d'abord dans ``start``, puis dans ses parents jusqu'à la
    racine du système. Retourne ``None`` si aucun ``meta.yml`` trouvé.
    """
    current = start.resolve()
    while True:
        candidate = current / "meta.yml"
        if candidate.is_file():
            return candidate
        parent = current.parent
        if parent == current:
            return None
        current = parent


def read_repo_metadata(root: Path | None = None) -> RepoMetadata | None:
    """Lit le ``meta.yml`` du dépôt fournisseur.

    Le provider courant est résolu en cascade :
    ``DSOXLAB_PROVIDER`` env > ``active_provider`` du contexte session
    > singleton du ``meta.yml`` > erreur si plusieurs candidats sans
    choix explicite. Voir ``models.repo._resolve_provider``.

    Args:
        root: Si fourni, cherche ``<root>/meta.yml``. Sinon, remonte
              depuis le CWD vers les parents.

    Returns:
        ``RepoMetadata`` chargé, ou ``None`` si aucun ``meta.yml``
        trouvé (ce qui active le mode legacy du scanner).
    """
    if root is None:
        meta_path = find_meta_yml(Path.cwd())
    else:
        candidate = root / "meta.yml"
        meta_path = candidate if candidate.is_file() else None

    if meta_path is None:
        return None

    # Lit le provider actif depuis le contexte session du repo (si
    # ``dsoxlab use <name>`` a été exécuté). Best-effort : si le
    # fichier de contexte n'existe pas ou est illisible, on passe
    # ``None`` et la résolution se rabat sur les autres règles.
    context_provider: str | None = None
    try:
        from ..config import read_context

        ctx = read_context(meta_path.parent)
        context_provider = ctx.active_provider
    except Exception:  # noqa: BLE001 — best-effort
        context_provider = None

    try:
        return RepoMetadata.from_yaml(
            meta_path, context_provider=context_provider
        )
    except (ValueError, KeyError) as exc:
        # Erreur de résolution provider : on remonte le message
        # complet à l'utilisateur via stderr (la CLI catch et
        # affiche), au lieu d'un simple warning silencieux.
        logger.error("meta.yml : %s", exc)
        # Re-raise pour que l'erreur de provider ambigu remonte au
        # CLI (qui guidera vers ``dsoxlab use``).
        raise
