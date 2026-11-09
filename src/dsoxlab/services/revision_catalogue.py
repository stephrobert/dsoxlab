"""La révision du catalogue : un seul endroit, deux usages.

Elle servait d'abord à l'export, qui la lit au moment de construire le document
(``catalog.version``). Elle sert aussi, depuis 0.8.0, à `check` : la révision AU
MOMENT de la tentative est consignée sur la ligne d'historique, parce que celle
de l'export peut avoir changé depuis (un ``git pull`` du catalogue entre deux).
"""

from __future__ import annotations

from pathlib import Path

from ..utils.shell import run_command


def revision_du_catalogue(root: Path) -> str | None:
    """La révision du catalogue, quand il en a une.

    Un score obtenu sur une version antérieure d'un lab se reconnaît alors, au
    lieu d'être comparé à un énoncé qui a changé depuis. Absente d'un répertoire
    qui n'est pas un dépôt git, et ce n'est pas une anomalie.
    """
    resultat = run_command(
        ["git", "-C", str(root), "rev-parse", "HEAD"], check=False, timeout=5,
    )
    return resultat.stdout.strip() if resultat.ok else None
