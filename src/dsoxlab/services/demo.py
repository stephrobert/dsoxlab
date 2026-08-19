"""Installer le catalogue de démonstration, et rien de plus.

Entre `uv tool install dsoxlab` et le premier lab joué, il y avait une
connaissance implicite : savoir que les labs vivent dans d'autres dépôts, savoir
lesquels, savoir qu'il faut se placer dedans. Qui installait l'outil et le
lançait là où il se trouvait n'obtenait rien, avec un code de retour 0 pour dire
que tout allait bien.

Ce module copie un catalogue d'un seul lab dans le répertoire de données de
l'utilisateur. Deux principes :

1. **On n'écrase jamais un travail en cours.** Le catalogue installé contient la
   progression de l'apprenant (`.dsoxlab.db`) et ses réponses. Une réinstallation
   silencieuse effacerait un lab en cours de résolution, ce qui est exactement ce
   qu'on ne pardonne pas à un outil.
2. **La marche à suivre vient de la CLI, pas d'un texte recopié.** Les commandes
   affichées sont construites à partir du catalogue réellement installé, donc
   elles ne peuvent pas dériver de ce qu'il contient.
"""

from __future__ import annotations

import shutil
from dataclasses import dataclass
from pathlib import Path

from ..config import xdg_data_home
from ..templates import demo_catalog


class DemoExistante(RuntimeError):
    """Le catalogue est déjà installé, et il porte peut-être du travail."""


@dataclass(frozen=True)
class Installation:
    """Ce qu'une installation a produit, pour que la CLI le raconte."""

    racine: Path
    labs: list[str]
    reinstallee: bool


def destination() -> Path:
    """Où le catalogue de démonstration est installé."""
    return xdg_data_home() / "dsoxlab" / "demo"


def _labs_du_catalogue(racine: Path) -> list[str]:
    """Identifiants des labs installés, lus sur le disque.

    On lit le catalogue plutôt que de coder la liste en dur : le jour où le
    catalogue de démonstration gagne un second lab, ce qui s'affiche suit.
    """
    ids: list[str] = []
    for lab_yaml in sorted((racine / "labs").rglob("lab.yaml")):
        for ligne in lab_yaml.read_text(encoding="utf-8").splitlines():
            if ligne.startswith("id:"):
                ids.append(ligne.split(":", 1)[1].strip())
                break
    return ids


def installer(*, force: bool = False) -> Installation:
    """Copie le catalogue packagé vers le répertoire de données.

    Args:
        force: réinstalle par-dessus une installation existante. Sans lui, une
            installation déjà en place lève : elle peut contenir la progression
            et les réponses de l'apprenant.

    Raises:
        DemoExistante: si le catalogue est déjà là et que ``force`` est faux.
        OSError: si la copie échoue (disque plein, droits).
    """
    cible = destination()
    existait = cible.exists()

    if existait and not force:
        raise DemoExistante(str(cible))

    if existait:
        shutil.rmtree(cible)

    cible.parent.mkdir(parents=True, exist_ok=True)
    # `dirs_exist_ok` n'est pas utilisé : on vient de supprimer la cible, et
    # fusionner deux catalogues laisserait des fichiers d'une version
    # antérieure au milieu de la nouvelle.
    shutil.copytree(demo_catalog(), cible)

    return Installation(
        racine=cible, labs=_labs_du_catalogue(cible), reinstallee=existait
    )
