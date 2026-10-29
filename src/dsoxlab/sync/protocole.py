"""Le transport vers le portail : l'enveloppe, les codes, la reprise.

AUCUNE DÉPENDANCE NOUVELLE

Tout passe par ``urllib.request`` de la bibliothèque standard. Ajouter un
client HTTP pour deux appels aurait pesé sur chaque installation de l'outil,
alors que les dépendances d'exécution se comptent sur une main et que
``ansible-core`` en représente déjà une centaine de mégaoctets.

L'ENVELOPPE NE SE DEVINE PAS, ET ELLE EST STRICTE

Le portail valide le corps avec ``additionalProperties: false`` et exige six
champs, dont trois qu'on oublie naturellement parce qu'ils paraissent
redondants : ``schema``, ``version``, et ``section`` — qui doit valoir celle du
chemin. Un corps réduit à ``baseRevision``, ``operationId`` et ``charge`` est
refusé en **400**, sans autre explication que « enveloppe ».

``operationId`` est un **UUID**, et le portail en vérifie la forme par une
expression régulière stricte. Un ULID, souvent cité pour cet usage parce qu'il
est trié, serait refusé. On émet donc ``uuid4``.

LES TROIS 409 NE SE RESSEMBLENT PAS

- ``revision`` : quelqu'un a écrit entre notre lecture et notre écriture. Se
  reprend, et **par une fusion**, jamais par un écrasement ;
- ``operation-reutilisee`` : le même ``operationId`` pour un autre contenu.
  C'est un défaut de la CLI, pas une course : boucler l'aggraverait ;
- un ``200`` avec ``rejoue: true`` n'est pas un conflit : c'est notre propre
  requête, rejouée après une coupure. C'est un **succès**, et c'est précisément
  ce que l'``operationId`` achète.
"""

from __future__ import annotations

import gzip
import json
import logging
import urllib.error
import urllib.request
import uuid
from typing import Any, TypedDict

from . import ChargeRefusee, ErreurPortail, SansSession, transport
from .magasin import CLE_MAGASIN, SECTION

logger = logging.getLogger(__name__)

#: Version du contrat de synchronisation. Le portail refuse toute autre valeur.
SCHEMA = "learner-sync"
VERSION = 1
VERSION_CHARGE = 1

#: Limites du portail, reprises de son contrat (``LIMITES``). Contrôlées ici
#: pour refuser avant l'aller-retour : la passerelle, elle, répond un 413 qui
#: ne dit pas laquelle a sauté.
BRUT_PAR_SECTION = 1_500_000
COMPRESSE_PAR_SECTION = 350_000
CORPS_REQUETE = 1_600_000

#: Délai d'un appel. Court à dessein : `push` est interactif, et un portail qui
#: ne répond pas en vingt secondes se réessaie mieux à la main.
DELAI = 20.0


class EtatSection(TypedDict):
    """Ce que le portail dit d'une section sans en donner la charge."""

    revision: int
    empreinte: str


class Ecriture(TypedDict):
    """Le résultat d'une écriture acceptée."""

    revision: int
    empreinte: str
    rejoue: bool


def _corps_erreur(brut: bytes) -> tuple[str, str]:
    """Le code stable et son détail, lus dans le corps d'erreur du portail.

    Forme attendue : ``{"erreur": {"code": "..."}}``. Un corps vide ou non JSON
    veut dire que la **passerelle** a répondu, pas l'application : on le dit
    par un code à part plutôt que d'inventer un sens.
    """
    try:
        charge = json.loads(brut.decode("utf-8", "replace"))
    except (TypeError, ValueError):
        return "http", ""
    if not isinstance(charge, dict):
        return "http", ""
    erreur = charge.get("erreur")
    if not isinstance(erreur, dict):
        return "http", ""
    code = erreur.get("code")
    detail = erreur.get("message") or erreur.get("detail") or ""
    return (
        code if isinstance(code, str) else "http",
        detail if isinstance(detail, str) else "",
    )


class ClientPortail:
    """Les deux appels dont `push` a besoin, et rien de plus.

    L'instance ne garde **pas** le jeton : elle le demande à chaque appel, par
    ``jeton()``. C'est ce qui permet de renouveler un jeton expiré sans
    reconstruire le client, et d'éviter qu'un objet de longue vie porte un
    secret plus longtemps que nécessaire.
    """

    def __init__(self, base: str, jeton: object) -> None:
        self._base = base.rstrip("/")
        # Callable typé largement : l'appelant passe une fermeture qui sait
        # renouveler. Vérifié à l'usage plutôt que par une signature qui
        # obligerait à importer le module d'identité ici.
        self._jeton = jeton

    def _acces(self) -> str:
        appel = self._jeton
        if not callable(appel):  # pragma: no cover — garde de programmation
            raise SansSession()
        valeur = appel()
        if not isinstance(valeur, str) or not valeur:
            raise SansSession()
        return valeur

    def _appeler(
        self, methode: str, chemin: str, corps: dict[str, Any] | None = None
    ) -> tuple[int, bytes]:
        donnees = None
        entetes = {
            "authorization": f"Bearer {self._acces()}",
            "accept": "application/json",
            "user-agent": "dsoxlab",
        }
        if corps is not None:
            donnees = json.dumps(corps, ensure_ascii=False).encode("utf-8")
            entetes["content-type"] = "application/json"
            if len(donnees) > CORPS_REQUETE:
                raise ChargeRefusee(
                    "sync_corps_trop_gros", taille=len(donnees), max=CORPS_REQUETE
                )

        requete = urllib.request.Request(  # noqa: S310 — le schéma est contrôlé
            f"{self._base}{chemin}", data=donnees, headers=entetes, method=methode
        )
        logger.info("Portal call %s %s", methode, chemin)
        try:
            return transport.ouvrir(requete, DELAI)
        except urllib.error.HTTPError as erreur:
            brut = transport.lire_erreur(erreur)
            code, detail = _corps_erreur(brut)
            if erreur.code == 404:
                # Pas une erreur pour nous : une section jamais écrite, donc
                # l'état de départ d'un compte neuf. En `info`, pas en
                # `warning` : le premier `push` de chaque apprenant passe par
                # là, et un avertissement y ferait chercher une panne.
                logger.info("Portal has no %s section yet (new account).", chemin)
                return 404, brut
            logger.warning(
                "Portal refused %s %s: %s %s", methode, chemin, erreur.code, code
            )
            raise ErreurPortail(int(erreur.code), code, detail=detail) from None
        except urllib.error.URLError as erreur:
            # Le portail n'a pas répondu : injoignable, DNS, TLS, délai. Un
            # geste opposé à celui d'un refus, donc un code à part.
            logger.warning("Portal unreachable: %s", erreur.reason)
            raise ErreurPortail(0, "injoignable", detail=str(erreur.reason)) from None

    def lire(self) -> tuple[EtatSection, str | None]:
        """L'état de la section ``labs`` et son magasin, brut.

        Une section jamais écrite rend ``(revision 0, None)`` : c'est l'état de
        départ d'un compte neuf, et il ne se distingue pas d'un compte vide.
        """
        statut, brut = self._appeler("GET", f"/v1/learning-state/{SECTION}")
        if statut == 404:
            return {"revision": 0, "empreinte": ""}, None
        charge = json.loads(brut.decode("utf-8"))
        donnees = charge.get("charge", {}).get("donnees", {})
        magasin = donnees.get(CLE_MAGASIN)
        return (
            {
                "revision": int(charge.get("revision", 0)),
                "empreinte": str(charge.get("empreinte", "")),
            },
            magasin if isinstance(magasin, str) else None,
        )

    def ecrire(
        self, base_revision: int, magasin: str, *, operation: str | None = None
    ) -> Ecriture:
        """Écriture conditionnelle de la section ``labs``.

        ``operation`` sert au **réessai** : rejouer la même écriture avec le
        même identifiant rend ``rejoue: true`` sans second effet. L'appelant qui
        réessaie après une coupure doit donc le repasser, et celui qui écrit
        autre chose doit en changer.
        """
        self._verifier_taille(magasin)
        corps = {
            "schema": SCHEMA,
            "version": VERSION,
            # La section figure dans le corps ET dans le chemin, et le portail
            # vérifie qu'elles coïncident. Redondant en apparence, mais c'est
            # ce qui empêche une écriture dirigée sur une autre section par un
            # intermédiaire qui réécrirait l'URL.
            "section": SECTION,
            "baseRevision": base_revision,
            "operationId": operation or str(uuid.uuid4()),
            "charge": {"v": VERSION_CHARGE, "donnees": {CLE_MAGASIN: magasin}},
        }
        _, brut = self._appeler("PUT", f"/v1/learning-state/{SECTION}", corps)
        charge = json.loads(brut.decode("utf-8"))
        return {
            "revision": int(charge.get("revision", 0)),
            "empreinte": str(charge.get("empreinte", "")),
            "rejoue": bool(charge.get("rejoue", False)),
        }

    @staticmethod
    def _verifier_taille(magasin: str) -> None:
        """Les deux limites du portail, mesurées comme il les mesure.

        La seconde demande de **compresser pour de vrai** : c'est ce que le
        portail stocke, et le rapport de compression d'un JSON de preuves n'est
        pas devinable. Mieux vaut quelques millisecondes de gzip ici qu'un 413
        après l'envoi d'un mégaoctet et demi.
        """
        charge = json.dumps(
            {"v": VERSION_CHARGE, "donnees": {CLE_MAGASIN: magasin}},
            ensure_ascii=False,
            separators=(",", ":"),
        ).encode("utf-8")
        if len(charge) > BRUT_PAR_SECTION:
            raise ChargeRefusee(
                "sync_charge_trop_grosse", taille=len(charge), max=BRUT_PAR_SECTION
            )
        compresse = len(gzip.compress(charge))
        if compresse > COMPRESSE_PAR_SECTION:
            raise ChargeRefusee(
                "sync_charge_compressee_trop_grosse",
                taille=compresse,
                max=COMPRESSE_PAR_SECTION,
            )
