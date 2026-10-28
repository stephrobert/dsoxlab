"""Le magasin de preuves tel que le portail le relit, et rien d'autre.

POURQUOI CE MODULE EXISTE PLUTÔT QU'UN `json.dumps` DU DOCUMENT D'EXPORT

Le portail ne stocke pas le document que ``dsoxlab export`` produit : il en
**dérive** un modèle réduit, une ligne par tentative, puis le garde sous une
clé unique. Ce modèle a ses propres noms de champs (``catalog`` devient
``catalogue_id``), ses propres bornes, et surtout ses propres **exclusions**.

ET LA SEULE RÈGLE QUI COMPTE VRAIMENT : C'EST TOUT OU RIEN

À la relecture, le portail revalide chaque ligne du magasin. Si **une seule**
ligne est écartée, il ne garde pas les autres : il rend un magasin **vide**.
Mesuré dans son code, et c'est délibéré de sa part — un magasin relu amputé
dirait un fichier retouché, et ses index ne correspondraient plus.

Conséquence pour nous, et elle gouverne tout ce fichier : **il ne faut jamais
émettre une ligne que le portail écarterait.** Une seule suffirait à effacer
l'historique affiché de l'apprenant, sans message et sans retour possible.
Deux cas se présentent en pratique, tous deux ordinaires :

- un lab **disparu du catalogue** (renommé, déplacé, supprimé). ``export`` le
  garde, et c'est juste : la tentative a eu lieu. Mais son ``lab_type`` vaut
  alors ``null``, que le portail écarte ;
- un lab de type ``validation``. ``construire_document`` l'exclut déjà, mais
  s'en remettre à cette exclusion lointaine serait fragile : un document fourni
  autrement n'aurait pas la même garantie, et le contrôle coûte une ligne.

On filtre donc **ici**, et on compte ce qui est écarté pour pouvoir le dire :
un envoi qui laisse des tentatives derrière lui doit l'annoncer, sinon
l'apprenant cherchera pourquoi son compte ne montre pas tout.

CE QUE CE MODULE NE FAIT PAS

Aucun réseau, aucun jeton, aucun fichier. Il prend un document et rend une
chaîne, ce qui le rend éprouvable sans serveur ni compte.
"""

from __future__ import annotations

import json
import re
from datetime import UTC, datetime
from typing import Any, Literal, TypedDict, cast

from . import ChargeRefusee

#: La clé sous laquelle le portail garde les preuves. Fixée par son contrat
#: (``CLE_MAGASIN``), pas par nous : la changer ferait écrire à côté.
CLE_MAGASIN = "apprentissage:dsoxlab:v1"

#: La section du contrat de synchronisation qui accueille cette clé.
SECTION = "labs"

#: Les types que le portail sait lire. ``validation`` n'y est pas : un lab qui
#: défend un guide ne note personne, il n'est jamais une preuve d'apprenant.
TYPES_LISIBLES = frozenset({"lab", "challenge", "capstone"})

#: Tentatives gardées au total par le portail. Au-delà, il refuse **en bloc**
#: plutôt que de tronquer, donc il faut le savoir avant d'envoyer.
LIGNES_MAX = 5000

#: Bornes du portail, reprises de son contrat. Les dépasser vaut un refus.
LONGUEUR_MAX_IDENTIFIANT = 128
LONGUEUR_MAX_VERSION = 40
LONGUEUR_MAX_DATE = 40
MAX_TESTS = 10_000
MAX_SCORE = 1_000_000

#: Espaces de noms que le portail se réserve : un catalogue qui s'y nommerait
#: prétendrait être autre chose qu'un catalogue de labs, et tout le document
#: serait refusé. Repris de ``ESPACES_RESERVES``.
ESPACES_RESERVES = ("dossier",)

#: ISO 8601 avec fuseau, tel que le portail l'exige. Il accepte ``Z`` **et**
#: ``+00:00``, avec 1 à 9 chiffres de fraction : la forme que
#: ``datetime.now(UTC).isoformat()`` écrit passe donc telle quelle, et il ne
#: faut surtout pas la « normaliser ». La chaîne entre dans la clé de
#: dédoublonnage : la retoucher créerait un doublon pour la même tentative.
_ISO = re.compile(
    r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d{1,9})?(?:Z|[+-]\d{2}:\d{2})$"
)

#: Avant 2024, dsoxlab n'existait pas ; au-delà d'un jour dans le futur, la
#: date ment. Les deux bornes sont celles du portail.
_DATE_MIN = datetime(2024, 1, 1, tzinfo=UTC)
_UN_JOUR = 86_400.0


class Preuve(TypedDict):
    """Une tentative, dans la forme exacte que le portail garde."""

    source: Literal["dsoxlab"]
    schema: Literal[1]
    catalogue_id: str
    catalogue_revision: str | None
    lab_id: str
    lab_type: str
    validated: bool
    score: int
    max_score: int
    passed_tests: int
    total_tests: int
    hints_used: int
    attempted_at: str
    producer_version: str | None


class Magasin(TypedDict):
    """Ce que porte la clé ``apprentissage:dsoxlab:v1``."""

    v: Literal[1]
    preuves: list[Preuve]
    dernierImport: str | None


class Conversion(TypedDict):
    """Le résultat d'une conversion, et ce qu'elle a laissé derrière elle.

    ``ecartees`` n'est pas un détail de journal : une tentative non émise ne
    paraîtra jamais sur le compte, et l'apprenant doit l'apprendre de la CLI
    plutôt que de le déduire d'un total qui ne tombe pas juste.
    """

    preuves: list[Preuve]
    ecartees: dict[str, int]


def _cle(preuve: Preuve) -> tuple[str, str, str]:
    """La clé de dédoublonnage du portail : catalogue, lab, date de tentative.

    Le contrat ne fournit aucun identifiant de tentative. Ce triplet ne se
    répète pas pour une même personne, donc réenvoyer les mêmes preuves ne
    change rien — c'est ce qui rend ``push`` rejouable sans précaution.
    """
    return (preuve["catalogue_id"], preuve["lab_id"], preuve["attempted_at"])


def _identifiant_lisible(valeur: object, longueur: int) -> str | None:
    """La chaîne si le portail l'acceptera, ``None`` sinon.

    Volontairement muet sur la raison : l'appelant ne décide rien d'autre que
    « émettre ou écarter ». Les caractères interdits sont déjà refusés en amont
    par :func:`dsoxlab.security.identifiant_sur`, qui lève en nommant le champ ;
    ce contrôle-ci est la ceinture, pas la bretelle.
    """
    if not isinstance(valeur, str) or not valeur or len(valeur) > longueur:
        return None
    return valeur


def _entier(valeur: object, maximum: int) -> int | None:
    # `bool` est un `int` en Python : un `True` passerait pour 1 et le portail
    # refuserait la ligne entière. On l'écarte explicitement.
    if isinstance(valeur, bool) or not isinstance(valeur, int):
        return None
    return valeur if 0 <= valeur <= maximum else None


def _date_sure(valeur: object, maintenant: datetime) -> str | None:
    if not isinstance(valeur, str) or len(valeur) > LONGUEUR_MAX_DATE:
        return None
    if not _ISO.match(valeur):
        return None
    try:
        # `fromisoformat` lit le `Z` nativement depuis Python 3.11,
        # que `requires-python` impose : pas de substitution a faire.
        quand = datetime.fromisoformat(valeur)
    except ValueError:
        return None
    if quand.tzinfo is None:
        return None
    if quand < _DATE_MIN or quand.timestamp() > maintenant.timestamp() + _UN_JOUR:
        return None
    return valeur


def _espace_reserve(catalogue: str) -> bool:
    return any(
        catalogue == reserve or catalogue.startswith(f"{reserve}/")
        for reserve in ESPACES_RESERVES
    )


class _Entete(TypedDict):
    """Ce que le document dit de lui-même, lu une fois pour toutes ses lignes."""

    catalogue: str | None
    revision: object
    version_producteur: str | None


def _entete(document: dict[str, Any]) -> _Entete:
    catalogue_doc = document.get("catalog")
    producteur = document.get("producer")
    identifiant = catalogue_doc.get("id") if isinstance(catalogue_doc, dict) else None
    return {
        "catalogue": identifiant if isinstance(identifiant, str) else None,
        "revision": (
            catalogue_doc.get("version") if isinstance(catalogue_doc, dict) else None
        ),
        "version_producteur": (
            _identifiant_lisible(producteur.get("version"), LONGUEUR_MAX_VERSION)
            if isinstance(producteur, dict)
            else None
        ),
    }


def _motif_du_type(type_lab: object) -> str | None:
    """Le motif d'écart dû au type de lab, ou ``None`` si le type est lisible.

    Trois sorties pour trois situations, et la distinction sert l'apprenant :
    un lab de validation ne note personne et c'est normal ; un lab disparu du
    catalogue n'a rien à corriger de son côté ; un type inconnu dit un document
    produit par une autre version.
    """
    if type_lab == "validation":
        # Déjà exclu par `construire_document`. Compté quand même : un document
        # venu d'ailleurs n'a pas cette garantie.
        return "type_validation"
    if type_lab not in TYPES_LISIBLES:
        # Le cas ordinaire : un lab renommé, déplacé ou supprimé, dont `export`
        # rend `lab_type: null`. La tentative a eu lieu, mais le portail ne sait
        # pas la ranger, et l'émettre viderait le magasin entier.
        return "lab_absent_du_catalogue" if type_lab is None else "type_inconnu"
    return None


def _reduire_une_ligne(
    ligne: dict[str, Any], entete: _Entete, quand: datetime
) -> Preuve | str:
    """Une ligne d'export en preuve, ou le motif pour lequel elle n'en est pas.

    Rend l'un **ou** l'autre, jamais une preuve approximative : nettoyer un
    identifiant romprait le rattachement d'une preuve à son lab, et inventer un
    type dirait quelque chose que le moteur n'a pas mesuré.
    """
    motif = _motif_du_type(ligne.get("lab_type"))
    if motif is not None:
        return motif

    catalogue = _identifiant_lisible(ligne.get("catalog"), LONGUEUR_MAX_IDENTIFIANT)
    lab_id = _identifiant_lisible(ligne.get("lab_id"), LONGUEUR_MAX_IDENTIFIANT)
    total = _entier(ligne.get("total_tests"), MAX_TESTS)
    passes = _entier(ligne.get("passed_tests"), MAX_TESTS)
    bareme = _entier(ligne.get("max_score"), MAX_SCORE)
    score = _entier(ligne.get("score"), MAX_SCORE)
    indices = _entier(ligne.get("hints_used"), MAX_TESTS)
    date = _date_sure(ligne.get("attempted_at"), quand)
    valide = ligne.get("validated")

    obligatoires = (catalogue, lab_id, total, passes, bareme, score, indices, date)
    if any(champ is None for champ in obligatoires) or not isinstance(valide, bool):
        return "champ_hors_contrat"
    # Les `assert` disent à mypy ce que le `any` ci-dessus a déjà établi ; ils
    # ne contrôlent rien de neuf.
    assert catalogue is not None and lab_id is not None and date is not None
    assert total is not None and passes is not None
    assert bareme is not None and score is not None and indices is not None

    if _espace_reserve(catalogue):
        return "catalogue_reserve"
    if passes > total or score > bareme:
        return "compte_incoherent"
    if valide and (total == 0 or passes != total):
        # Le portail refuse le document ENTIER sur cette contradiction. Le
        # moteur ne peut pas la produire — sa règle est « tous les tests passés
        # ET au moins un joué » — mais un document retouché, oui.
        return "verdict_contradictoire"

    return {
        "source": "dsoxlab",
        "schema": 1,
        "catalogue_id": catalogue,
        # La révision décrit le catalogue DU DOCUMENT : une ligne venue d'un
        # autre catalogue, fondue dans le même export, ne la porte pas. Même
        # règle que le portail, sinon la ligne diffère selon qu'elle passe par
        # le navigateur ou par la CLI.
        "catalogue_revision": (
            _identifiant_lisible(entete["revision"], LONGUEUR_MAX_IDENTIFIANT)
            if catalogue == entete["catalogue"]
            else None
        ),
        "lab_id": lab_id,
        "lab_type": str(ligne["lab_type"]),
        "validated": valide,
        "score": score,
        "max_score": bareme,
        "passed_tests": passes,
        "total_tests": total,
        "hints_used": indices,
        "attempted_at": date,
        "producer_version": entete["version_producteur"],
    }


def convertir(
    document: dict[str, Any], *, maintenant: datetime | None = None
) -> Conversion:
    """Le document de ``dsoxlab export``, réduit à ce que le portail relira.

    Chaque ligne passe les contrôles du portail **avant** d'être émise, et ce
    qui échoue est compté plutôt que corrigé. Le détail vit dans
    :func:`_reduire_une_ligne` ; ici ne reste que la boucle et le décompte.

    Args:
        document: ce que rend
            :func:`dsoxlab.services.evidence.construire_document`.
        maintenant: injecté pour que le test soit reproductible.

    Returns:
        Les preuves émissibles, et le décompte par motif d'écart.
    """
    lignes = document.get("results")
    if not isinstance(lignes, list):
        return {"preuves": [], "ecartees": {"document_illisible": 1}}

    quand = maintenant or datetime.now(UTC)
    entete = _entete(document)
    preuves: list[Preuve] = []
    ecartees: dict[str, int] = {}

    for ligne in lignes:
        if not isinstance(ligne, dict):
            ecartees["ligne_illisible"] = ecartees.get("ligne_illisible", 0) + 1
            continue
        issue = _reduire_une_ligne(ligne, entete, quand)
        if isinstance(issue, str):
            ecartees[issue] = ecartees.get(issue, 0) + 1
        else:
            preuves.append(issue)

    return {"preuves": preuves, "ecartees": ecartees}


def lire(brut: str | None) -> Magasin:
    """Le magasin tel qu'il arrive du portail, ou un magasin vide.

    Tolérant à dessein : ce qu'on relit ici a été écrit par un navigateur, une
    autre version de la CLI, ou une restauration de sauvegarde. Une forme
    inattendue n'est pas une panne, c'est un magasin qu'on ne sait pas lire, et
    la suite le traitera comme vide — jamais comme une raison d'écraser.
    """
    vide: Magasin = {"v": 1, "preuves": [], "dernierImport": None}
    if not brut:
        return vide
    try:
        charge = json.loads(brut)
    except (TypeError, ValueError):
        return vide
    if not isinstance(charge, dict) or charge.get("v") != 1:
        return vide
    lignes = charge.get("preuves")
    if not isinstance(lignes, list):
        return vide
    dernier = charge.get("dernierImport")
    # `cast` et non une validation : ces lignes viennent du PORTAIL, et on les
    # retransmet telles quelles. Les revalider ici serait pire que tolérant, ce
    # serait destructeur : une ligne que notre version ne saurait pas lire
    # disparaîtrait de son compte à la première fusion. On ne lit que trois
    # champs, pour dédoublonner, et on ne touche à rien d'autre.
    gardees = cast("list[Preuve]", [ligne for ligne in lignes if isinstance(ligne, dict)])
    return {"v": 1, "preuves": gardees,
            "dernierImport": dernier if isinstance(dernier, str) else None}


def fusionner(distant: Magasin, nouvelles: list[Preuve]) -> tuple[Magasin, int, int]:
    """L'union dédoublonnée du magasin distant et des preuves locales.

    **Jamais un écrasement.** Les preuves sont la seule famille que le portail
    réunit sans rien demander à l'apprenant, et il attend de nous la même
    chose : il peut avoir des tentatives qu'on n'a pas, jouées depuis une autre
    machine ou importées à la main. Les perdre parce qu'on tient la dernière
    révision serait un défaut silencieux et irréversible.

    Le tri par date de tentative reprend celui du portail : à magasin égal,
    même ordre, donc même empreinte des deux côtés.

    Returns:
        Le magasin fusionné, le nombre de preuves ajoutées, le nombre de
        doublons rencontrés.
    """
    connues = {
        _cle(preuve)
        for preuve in distant["preuves"]
        if isinstance(preuve, dict) and "lab_id" in preuve
    }
    ajout: list[Preuve] = []
    doublons = 0
    for preuve in nouvelles:
        cle = _cle(preuve)
        if cle in connues:
            doublons += 1
            continue
        connues.add(cle)
        ajout.append(preuve)

    total = [*distant["preuves"], *ajout]
    total.sort(key=lambda preuve: str(preuve.get("attempted_at", "")))
    fusion: Magasin = {
        "v": 1,
        "preuves": total,
        # `dernierImport` dit quand des preuves sont ENTRÉES, pas quand on a
        # parlé au portail : sans ajout, il ne bouge pas.
        "dernierImport": (
            datetime.now(UTC).isoformat() if ajout else distant["dernierImport"]
        ),
    }
    return fusion, len(ajout), doublons


def serialiser(magasin: Magasin) -> str:
    """Le magasin en chaîne, dans la forme que la charge attend.

    ``donnees`` est un dictionnaire de **chaînes**, pas d'objets : le portail
    stocke la valeur déjà sérialisée et la recompresse telle quelle. Séparateurs
    compacts, parce que la limite porte sur les octets et qu'aucun humain ne lit
    cette chaîne.

    Lève :class:`ChargeRefusee` quand le plafond de lignes est dépassé. Le
    portail refuserait aussi, mais après un aller-retour et sans dire laquelle
    des limites a sauté.
    """
    if len(magasin["preuves"]) > LIGNES_MAX:
        raise ChargeRefusee(
            "sync_trop_de_lignes", lignes=len(magasin["preuves"]), max=LIGNES_MAX
        )
    return json.dumps(magasin, ensure_ascii=False, separators=(",", ":"))
