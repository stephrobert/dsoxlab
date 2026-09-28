"""Le document de preuve, construit en un seul endroit pour trois usages.

Trois chemins portent la même chose : ``dsoxlab export`` (l'historique entier),
``dsoxlab export --lab <id>`` (une preuve unitaire, pour un fichier ou un
copier-coller) et, demain, le lien de remise vers un portail. **Un seul format**,
donc une seule construction : deux producteurs du même document divergent, et
c'est le consommateur qui découvre l'écart, souvent des mois plus tard.

Ce que le document porte, champ par champ, est décrit dans ``docs/machine-output``
— et il est construit par **liste blanche**, jamais en sérialisant un objet
interne dont on retirerait ensuite quelques clés : le prochain champ ajouté à cet
objet partirait sinon en silence.

Une preuve unitaire est le **même** document, avec un seul élément dans
``results`` et ``count: 1``. Pas de second schéma : un consommateur qui sait lire
l'un sait lire l'autre.
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from ..models.lab import LabDefinition
from ..reporting import machine
from ..security import identifiant_sur
from ..sessions.store import get_all_results
from ..utils.shell import run_command

#: Le nom du format, tel qu'il voyage. Une **chaîne**, et c'est le seul endroit
#: du projet où c'est le cas : ce document quitte dsoxlab, atterrit dans un
#: navigateur, un LMS, un fichier qu'on retrouve trois mois plus tard — des
#: endroits où ``{"schema": 1}`` ne dit pas de quoi il est le schéma 1.
SCHEMA = "dsoxlab-evidence-v1"


class PreuveIntrouvable(LookupError):
    """Aucun résultat enregistré pour ce lab : il n'y a pas de preuve à rendre.

    Ce n'est pas un défaut mais un état, et il se distingue d'un lab inconnu :
    l'un se joue, l'autre se cherche. D'où la clé i18n portée par l'exception,
    que la commande traduit.
    """

    def __init__(self, lab_id: str, *, cle: str) -> None:
        self.lab_id = lab_id
        self.cle = cle
        super().__init__(f"{lab_id}: {cle}")


def _maintenant() -> str:
    return datetime.now(UTC).isoformat()


def _version_outil() -> str:
    from .. import __version__

    return __version__


def _revision(root: Path) -> str | None:
    """La révision du catalogue, quand il en a une.

    Un score obtenu sur une version antérieure d'un lab se reconnaît alors, au
    lieu d'être comparé à un énoncé qui a changé depuis. Absente d'un répertoire
    qui n'est pas un dépôt git, et ce n'est pas une anomalie.
    """
    resultat = run_command(
        ["git", "-C", str(root), "rev-parse", "HEAD"], check=False, timeout=5,
    )
    return resultat.stdout.strip() if resultat.ok else None


def identifiant_de_catalogue(root: Path, repo_id: str | None) -> str:
    """L'identifiant du catalogue, validé parce qu'il va quitter la machine.

    Le repli sur le nom du répertoire mérite autant de méfiance que le
    ``repo.id`` du catalogue : un nom de dossier est libre, il peut porter des
    espaces, un retour chariot ou une surcharge de direction. Les deux
    traversent la même frontière de confiance, donc les deux se valident.

    Lève :class:`~dsoxlab.security.IdentifiantRefuse`, que la commande traduit.
    """
    return identifiant_sur(repo_id or root.name, champ="catalog.id")


def construire_document(
    root: Path,
    labs: dict[str, LabDefinition],
    *,
    catalog_id: str,
    lab_id: str | None = None,
) -> dict[str, Any]:
    """Le document de preuve : tout l'historique, ou la dernière tentative d'un lab.

    ``lab_id`` restreint à **une** ligne, la plus récente enregistrée pour ce
    lab : c'est ce qu'un portail attend d'un lien de remise, et ce qu'un
    formateur attend d'un fichier remis. Sans lui, l'historique entier, sans
    troncature — un export borné est pire qu'absent, parce que celui qui le lit
    croit tout avoir.

    Lève :class:`PreuveIntrouvable` quand ``lab_id`` n'a aucun résultat, ou
    quand ce lab est de type ``validation`` : celui-là défend un guide et ne note
    personne, sa place n'est pas dans les preuves de pratique de quelqu'un.
    """
    lignes_brutes = get_all_results(root)

    for row in lignes_brutes:
        identifiant_sur(row["lab_id"], champ="lab_id")
        identifiant_sur(row["section"], champ="section", vide_permis=True)

    if lab_id is not None:
        lab = labs.get(lab_id)
        if lab is not None and not lab.is_exercise:
            raise PreuveIntrouvable(lab_id, cle="preuve_lab_validation")
        # Les résultats arrivent du plus ancien au plus récent : la dernière
        # ligne est donc la dernière tentative. On ne prend pas la meilleure —
        # une preuve atteste ce qui s'est passé, pas ce qu'on préfère montrer.
        pour_ce_lab = [row for row in lignes_brutes if row["lab_id"] == lab_id]
        if not pour_ce_lab:
            raise PreuveIntrouvable(lab_id, cle="preuve_sans_tentative")
        lignes_brutes = [pour_ce_lab[-1]]
    else:
        lignes_brutes = [
            row for row in lignes_brutes
            if (lab := labs.get(row["lab_id"])) is None or lab.is_exercise
        ]

    lignes = [
        machine.export_result_dict(row, labs.get(row["lab_id"]), catalog_id)
        for row in lignes_brutes
    ]
    return {
        "schema": SCHEMA,
        "generated_at": _maintenant(),
        "producer": {"name": "dsoxlab", "version": _version_outil()},
        # `version` et non `commit` : c'est la révision quand le catalogue est un
        # dépôt git, et ce pourrait être autre chose ailleurs. Le consommateur
        # n'a pas à savoir laquelle, seulement à distinguer deux états du même
        # catalogue.
        #
        # Le chemin local N'Y EST PAS. Ce document est fait pour être transmis :
        # `/home/marie/Projets/…` y publierait un nom d'utilisateur, parfois un
        # nom de famille, et l'arborescence d'une machine — à un destinataire qui
        # n'en a aucun usage, puisque `id` et `version` identifient déjà le
        # catalogue.
        "catalog": {"id": catalog_id, "version": _revision(root)},
        "results": lignes,
        "count": len(lignes),
    }
