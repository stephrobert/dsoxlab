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

import base64
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from urllib.parse import urlparse, urlunparse

from ..models.lab import LabDefinition
from ..reporting import machine
from ..security import identifiant_sur
from ..security.urls import url_de_portail
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


# ── le lien de remise ────────────────────────────────────────────────────────

#: Ce qu'un portail accepte dans un fragment, encodé. Mesuré côté site, pas
#: deviné, et contrôlé **avant** tout décodage par le consommateur. Une preuve
#: unitaire pèse quelques centaines de caractères : cette borne n'est pas là
#: pour le cas courant, elle est là pour dire le jour où il cesse de l'être.
LIMITE_FRAGMENT = 32 * 1024

#: Le nom du paramètre dans le fragment. Un nom, pas un verbe : le portail lit
#: une donnée, il ne reçoit pas un ordre.
CLE_FRAGMENT = "dsoxlab"


class ChargeTropGrande(ValueError):
    """La preuve ne tient pas dans un fragment d'URL.

    Le lien n'est alors pas affiché : un lien tronqué par un navigateur ou par
    un serveur est pire qu'un lien absent, parce qu'il échoue chez le
    destinataire, longtemps après le geste. ``dsoxlab export --out`` reste le
    chemin universel, et c'est lui que la commande propose.
    """

    def __init__(self, taille: int) -> None:
        self.taille = taille
        self.limite = LIMITE_FRAGMENT
        super().__init__(f"{taille} > {LIMITE_FRAGMENT}")


def charge_utile(document: dict[str, Any]) -> str:
    """Le document en **base64url sans remplissage**, prêt pour un fragment.

    Chaque décision de cet encodage répond à une contrainte du consommateur, et
    aucune n'est esthétique :

    - **base64url** (RFC 4648 §5) parce que le base64 standard emploie ``+`` et
      ``/``, qui ne traversent pas une URL sans être réencodés ;
    - **sans remplissage**, parce qu'un ``=`` en fin de fragment se fait ronger
      par les outils qui recopient des liens ;
    - **JSON compact**, séparateurs serrés : l'indentation n'a aucun lecteur ici ;
    - **aucune compression**. Une preuve unitaire tient en moins d'un kilo-octet
      — mesuré : 434 caractères de JSON, 579 encodés. Un décompresseur chez le
      destinataire ajouterait une surface d'attaque (une charge pathologique se
      décompresse en gigaoctets) pour ne rien gagner.

    Lève :class:`ChargeTropGrande` au-delà de :data:`LIMITE_FRAGMENT`.
    """
    compact = json.dumps(document, ensure_ascii=False, separators=(",", ":"))
    charge = base64.urlsafe_b64encode(compact.encode("utf-8")).decode("ascii").rstrip("=")
    if len(charge) > LIMITE_FRAGMENT:
        raise ChargeTropGrande(len(charge))
    return charge


def lien_de_remise(portal_url: str, document: dict[str, Any]) -> str:
    """L'URL à afficher pour remettre cette preuve, et rien de plus.

    **Un fragment, jamais une query string.** Le fragment reste côté navigateur :
    il ne part pas dans la requête HTTP, donc ni dans les journaux du serveur, ni
    dans ceux d'un reverse proxy, ni dans un CDN. Avec ``?dsoxlab=…``, les
    résultats d'un apprenant seraient écrits dans des fichiers que personne n'a
    décidé de garder.

    Ce choix ne rend pas le portail digne de confiance pour autant : son
    JavaScript lit le fragment. C'est pourquoi la preuve ne porte que des données
    pédagogiques — c'est la liste blanche d'Evidence v1, et c'est ce qui rend ce
    lien anodin.

    Un fragment déjà présent dans l'URL déclarée est **remplacé** : une URL n'en
    porte qu'un, et un catalogue qui en déclarerait un ne dirait rien d'utile ici.

    L'URL passe par :func:`dsoxlab.security.urls.url_de_portail`, donc par la
    politique unique du projet. Rien ici n'ouvre de navigateur, n'appelle
    ``xdg-open``, ne résout le nom du portail ni ne l'interroge : la commande
    affiche un lien, et l'apprenant décide. Lève
    :class:`~dsoxlab.security.urls.URLRefusee` sur une URL que la politique
    refuse.
    """
    valide = url_de_portail(portal_url)
    parties = urlparse(valide)
    return urlunparse(parties._replace(
        fragment=f"{CLE_FRAGMENT}={charge_utile(document)}"
    ))


def hote_du_portail(portal_url: str) -> str:
    """Le nom d'hôte du portail, pour l'afficher à part du lien.

    Un lien long finit tronqué par l'œil : ce qu'on lit d'une URL de plusieurs
    centaines de caractères, c'est son début, et c'est précisément ce qu'un
    attaquant contrôle le moins mal. Nommer l'hôte séparément, en clair, est ce
    qui permet à l'apprenant de voir **où** il enverrait sa preuve.
    """
    return urlparse(url_de_portail(portal_url)).hostname or ""
