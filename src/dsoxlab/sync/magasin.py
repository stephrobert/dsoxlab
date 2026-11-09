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
#: Combien de noms de contrôles ratés une preuve transporte au plus.
#:
#: Le portail s'en sert pour dire à l'apprenant sur quoi revenir, et une
#: vingtaine de noms y suffit largement : un lab du catalogue en porte quatre
#: ou cinq. La borne existe parce que ces noms viennent d'une sortie pytest, et
#: qu'une suite inattendue pourrait en rendre des centaines : le magasin
#: grossirait sans fin pour une information que personne ne lirait.
MAX_CONTROLES_NOMMES = 20
#: Combien de critères une preuve transporte au plus (0.8.0). Au-delà, le champ
#: vaut ``None`` (inconnu) : une liste tronquée dirait « voici les critères »
#: alors qu'il en manque, ce qui est pire que de ne rien dire.
MAX_CRITERES_POUSSES = 40
#: Les états de critère que le portail peut lire.
ETATS_DE_CRITERE = frozenset({"satisfied", "unsatisfied", "not_evaluated", "skipped"})
#: Forme d'un identifiant de critère ou d'indice : celle du contrat auteur.
_JETON = re.compile(r"[\w.:\[\]-]+")
_UUID = re.compile(r"[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}")
_EMPREINTE = re.compile(r"[0-9a-f]{16}")
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
    failed_checks: list[str]
    """Les contrôles ratés, pour que le portail puisse dire quoi réviser.

    Sans eux, il recevait « 3 sur 5 » et n'avait rien à proposer : le verdict
    était juste et inexploitable. Tronqué à ``MAX_CONTROLES_NOMMES``.
    """

    blocking_failed: list[str] | None
    """Ceux de ces contrôles qu'aucun total ne compense, ou ``None``.

    ``None`` veut dire INCONNU, et c'est le cas de toute tentative enregistrée
    avant dsoxlab 0.7.0 : la colonne n'existait pas. Une liste vide, elle, dit
    qu'aucun contrôle bloquant n'a échoué, ce qui n'est pas la même chose.

    Sans ce champ, un apprenant qui passe par son compte ne voyait jamais
    qu'une épreuve était refusée sur son exigence critique, alors que `submit`
    et l'export le savaient.
    """

    exam_passed: bool | None
    """Le verdict d'épreuve, ou ``None`` pour un lab qui n'en est pas une.

    C'est le PREMIER JUGEMENT que cette preuve transporte : tous ses autres
    champs sont des faits bruts. Il est donc calculé une seule fois, côté
    moteur, par ``exam_verdict``, et le portail le lit sans le recalculer.
    Deux calculs finiraient par diverger, et l'apprenant verrait deux verdicts
    pour une seule tentative.

    ``None`` couvre deux cas que le portail n'a pas à distinguer : un lab
    ordinaire, qui ne déclare aucun seuil, et une tentative d'avant 0.7.0,
    dont on ne sait rien.
    """

    attempted_at: str
    producer_version: str | None

    attempt_id: str | None
    """L'identifiant de la tentative (0.8.0), ou ``None`` : inconnu.

    Il sert à ``fusionner`` pour ENRICHIR une ligne déjà connue sans
    identifiant (même triplet catalogue, lab, date), jamais pour dédoublonner :
    la clé reste le triplet. ``None`` sur une tentative d'avant 0.8.0."""

    lab_digest: str | None
    """L'empreinte du lab telle qu'il était à la tentative (16 hexadécimaux)."""

    not_evaluated: list[str] | None
    """Les vérifications BLOQUÉES (fixture, collecte), ``MAX_CONTROLES_NOMMES`` au plus.

    ``None`` veut dire INCONNU, ``[]`` aucune."""

    hints_seen: list[dict[str, Any]] | None
    """Les indices vus : ``{index, id, criterion}``, vingt au plus, sinon ``None``."""

    criteria: list[dict[str, str]] | None
    """Les critères réduits à ``{id, state}``, ``MAX_CRITERES_POUSSES`` au plus.

    Ni observation, ni phase, ni mention : le portail n'a besoin que du verdict
    par critère, et chaque octet de plus se paie sur 5 000 lignes. Au-delà du
    plafond, ``None`` plutôt qu'une liste tronquée."""


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


def _controles_rates(valeur: object) -> list[str]:
    """Les noms des contrôles ratés d'une ligne d'export, nettoyés et bornés.

    Ils ne font PAS partie des champs obligatoires : une ligne d'un export
    antérieur n'en porte pas, et la refuser pour cela viderait le magasin de
    l'apprenant, ce que ce module existe pour éviter. Toute forme inattendue
    rend donc une liste vide, jamais un motif de rejet.

    La borne existe parce que ces noms viennent d'une sortie pytest : une suite
    inattendue en rendrait des centaines, et le magasin grossirait sans fin
    pour une information que personne ne lirait.

    Sortie de ``_reduire_une_ligne`` parce que le cliquet du dépôt l'a refusée
    à 21 de complexité cognitive.
    """
    if not isinstance(valeur, list):
        return []
    propres = (
        _identifiant_lisible(brut, LONGUEUR_MAX_IDENTIFIANT)
        for brut in valeur[:MAX_CONTROLES_NOMMES]
    )
    return [nom for nom in propres if nom]


def _indices_vus(valeur: object) -> list[dict[str, Any]] | None:
    """Les indices vus, ou ``None`` si le champ est absent, mal formé ou trop long."""
    if not isinstance(valeur, list) or len(valeur) > MAX_CONTROLES_NOMMES:
        return None
    propres: list[dict[str, Any]] = []
    for brut in valeur:
        if not isinstance(brut, dict) or _entier(brut.get("index"), MAX_TESTS) is None:
            return None
        identifiant = brut.get("id")
        critere = brut.get("criterion")
        propres.append({
            "index": brut["index"],
            "id": identifiant if _jeton(identifiant) else None,
            "criterion": critere if _jeton(critere) else None,
        })
    return propres


def _jeton(valeur: object) -> bool:
    return (
        isinstance(valeur, str)
        and len(valeur) <= LONGUEUR_MAX_IDENTIFIANT
        and _JETON.fullmatch(valeur) is not None
    )


def _criteres_pousses(valeur: object) -> list[dict[str, str]] | None:
    """``{id, state}`` par critère, ou ``None`` : mal formé, ou plus de quarante."""
    if not isinstance(valeur, list) or len(valeur) > MAX_CRITERES_POUSSES:
        return None
    propres: list[dict[str, str]] = []
    for brut in valeur:
        if not isinstance(brut, dict):
            return None
        identifiant, etat = brut.get("id"), brut.get("state")
        if not _jeton(identifiant) or etat not in ETATS_DE_CRITERE:
            return None
        propres.append({"id": cast("str", identifiant), "state": cast("str", etat)})
    return propres


def _champs_de_tentative(ligne: dict[str, Any]) -> dict[str, Any]:
    """Les champs ajoutés en 0.8.0, lus avec TOLÉRANCE.

    Aucun motif d'écart n'est ajouté : une ligne n'est jamais refusée pour l'un
    d'eux, puisqu'une ligne écartée vide le magasin de l'apprenant. Un champ
    absent ou mal formé devient ``None`` (inconnu) ; une liste mal formée ou
    trop longue aussi, jamais une liste tronquée ou à moitié lue.
    """
    brut_id, brut_digest = ligne.get("attempt_id"), ligne.get("lab_digest")
    non_evalues = ligne.get("not_evaluated")
    return {
        "attempt_id": brut_id if isinstance(brut_id, str) and _UUID.fullmatch(brut_id) else None,
        "lab_digest": (
            brut_digest
            if isinstance(brut_digest, str) and _EMPREINTE.fullmatch(brut_digest)
            else None
        ),
        "not_evaluated": (
            _controles_rates(non_evalues) if isinstance(non_evalues, list) else None
        ),
        "hints_seen": _indices_vus(ligne.get("hints_seen")),
        "criteria": _criteres_pousses(ligne.get("criteria")),
    }


def _refus_de_la_ligne(
    ligne: dict[str, Any]
) -> tuple[list[str] | None, bool | None]:
    """Ce qu'une ligne d'export dit du refus : les bloquants, et le verdict.

    LE CHAMP ABSENT ET LE CHAMP VIDE NE DISENT PAS LA MÊME CHOSE. Absent,
    c'est une tentative d'avant 0.7.0, dont la colonne n'existait pas : on ne
    SAIT pas, et envoyer `[]` affirmerait qu'aucun contrôle bloquant n'a
    échoué. Le portail lit ce `None` comme « inconnu », et la distinction se
    tranche chez lui sur le compte des tests : une liste vide avec un
    sans-faute est exacte, une liste vide avec un compte incomplet ne l'est
    pas.

    LE VERDICT VIENT DE L'EXPORT, donc d'``exam_verdict``, calculé une seule
    fois côté moteur. On ne le recalcule pas ici : deux calculs finiraient par
    diverger, et l'apprenant verrait deux verdicts pour une seule tentative.
    C'est le premier jugement que cette preuve transporte, tous ses autres
    champs étant des faits bruts.

    Aucune forme ne fait échouer cette lecture : une ligne écartée vide le
    magasin de l'apprenant, ce que ce module existe pour éviter.

    Sortie de ``_reduire_une_ligne`` parce que le cliquet du dépôt l'a
    refusée à quatre-vingt-cinq lignes.
    """
    brut = ligne.get("blocking_failed")
    bloquants = _controles_rates(brut) if isinstance(brut, list) else None
    examen = ligne.get("exam")
    verdict = examen.get("passed") if isinstance(examen, dict) else None
    return bloquants, (verdict if isinstance(verdict, bool) else None)


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
    noms = _controles_rates(ligne.get("failed_checks"))
    bloquants, verdict = _refus_de_la_ligne(ligne)
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

    return cast("Preuve", {
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
        "failed_checks": noms,
        "blocking_failed": bloquants,
        "exam_passed": verdict,
        "attempted_at": date,
        "producer_version": entete["version_producteur"],
        **_champs_de_tentative(ligne),
    })


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


def _richesse(preuve: Preuve) -> tuple[bool, int]:
    """Ce qu'une ligne sait de sa tentative : un identifiant, puis du détail."""
    detail = sum(
        1 for champ in ("criteria", "hints_seen", "not_evaluated")
        if preuve.get(champ) is not None
    )
    return (bool(preuve.get("attempt_id")), detail)


def _plus_riche(nouvelle: Preuve, connue: Preuve) -> bool:
    """La nouvelle ligne est-elle la MÊME tentative que la connue, en plus riche ?

    Même triplet (déjà garanti par l'appelant) et, si les deux portent un
    identifiant, le même : deux identifiants pour un même triplet sont deux
    tentatives que le portail ne distingue pas, on garde la sienne. Plus riche
    veut dire strictement : un identifiant que l'autre n'a pas, ou plus de
    champs de détail connus. À richesse égale, la ligne du portail reste.
    """
    id_nouvelle, id_connue = nouvelle.get("attempt_id"), connue.get("attempt_id")
    if id_nouvelle and id_connue and id_nouvelle != id_connue:
        return False
    return _richesse(nouvelle) > _richesse(connue)


def fusionner(distant: Magasin, nouvelles: list[Preuve]) -> tuple[Magasin, int, int]:
    """L'union dédoublonnée du magasin distant et des preuves locales.

    **Jamais un écrasement.** Les preuves sont la seule famille que le portail
    réunit sans rien demander à l'apprenant, et il attend de nous la même
    chose : il peut avoir des tentatives qu'on n'a pas, jouées depuis une autre
    machine ou importées à la main. Les perdre parce qu'on tient la dernière
    révision serait un défaut silencieux et irréversible.

    **La clé reste le triplet catalogue, lab, date.** ``attempt_id`` ne
    dédoublonne rien à lui seul : deux lignes de même identifiant et de dates
    différentes sont deux lignes (un document retouché ou rejoué ne doit pas
    faire disparaître une tentative sur la foi d'un champ que le portail ne
    garantit pas encore). Il sert à une seule chose : une ligne locale PLUS
    RICHE (un identifiant que l'autre n'a pas, ou plus de détail connu) REMPLACE
    la ligne du portail de même triplet et de même identifiant. La plus riche
    gagne, jamais la plus récente : une ligne allégée n'écrase pas un détail.

    Le tri par date de tentative reprend celui du portail : à magasin égal,
    même ordre, donc même empreinte des deux côtés.

    Returns:
        Le magasin fusionné, le nombre de preuves ajoutées, le nombre de
        doublons rencontrés.
    """
    total: list[Preuve] = list(distant["preuves"])
    position: dict[tuple[str, str, str], int] = {}
    for rang, preuve in enumerate(total):
        if isinstance(preuve, dict) and "lab_id" in preuve:
            position.setdefault(_cle(preuve), rang)
    ajoutees = 0
    doublons = 0
    for preuve in nouvelles:
        cle = _cle(preuve)
        connu = position.get(cle)
        if connu is None:
            position[cle] = len(total)
            total.append(preuve)
            ajoutees += 1
        elif _plus_riche(preuve, total[connu]):
            # LA MÊME TENTATIVE, PLUS RICHE. La ligne du portail date d'avant
            # 0.8.0, ou a été allégée pour tenir sous la limite d'octets : la
            # nôtre dit la même chose et davantage, elle la remplace. Jamais
            # l'inverse : une ligne locale plus pauvre n'écrase pas un détail
            # que le portail porte déjà.
            # Comptée parmi les doublons : la tentative était connue, et
            # `dernierImport` ne bouge pas. La charge, elle, diffère, donc elle
            # est bien écrite.
            total[connu] = preuve
            doublons += 1
        else:
            doublons += 1

    total.sort(key=lambda preuve: str(preuve.get("attempted_at", "")))
    fusion: Magasin = {
        "v": 1,
        "preuves": total,
        # `dernierImport` dit quand des preuves sont ENTRÉES, pas quand on a
        # parlé au portail : sans ajout, il ne bouge pas.
        "dernierImport": (
            datetime.now(UTC).isoformat() if ajoutees else distant["dernierImport"]
        ),
    }
    return fusion, ajoutees, doublons


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
