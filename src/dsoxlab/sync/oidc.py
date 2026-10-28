"""La connexion de l'apprenant : authorization code + PKCE S256.

POURQUOI PAS LE DEVICE FLOW, QUI AURAIT ÉTÉ PLUS BEAU

Un code court affiché par la CLI, validé dans un navigateur déjà connecté :
c'est le schéma des CLI comparables, et il règle d'un coup le cas de la machine
sans navigateur. Il a été écarté par la **mesure**, pas par préférence : le
document de découverte du pool ne publie aucun ``device_authorization_endpoint``
et l'appel direct rend 404. Cognito ne sait pas le faire pour ce pool.

PKCE S256, lui, a été vérifié contre l'émetteur réel : la requête
d'autorisation répond et sert la page de connexion.

PKCE SANS SECRET, ET C'EST TOUT L'INTÉRÊT

Le client est **public**. Un secret dans une CLI distribuée n'est pas un
secret, et PKCE existe précisément pour s'en passer : le vérificateur est tiré
au hasard à chaque connexion, ne quitte jamais la machine, et seul son
condensat voyage dans l'URL d'autorisation. Un tiers qui intercepterait le code
d'autorisation ne pourrait rien en faire.

LE PORT DE RETOUR EST FIXE, ET CE N'EST PAS UN CHOIX D'ERGONOMIE

Cognito compare les ``redirect_uri`` à l'identique, port compris : un port
éphémère obligerait à enregistrer soixante mille URL de retour. Le port est donc
déclaré par le portail dans son ``meta.yml``, et il doit figurer tel quel dans
la configuration du client OAuth. S'il est déjà pris sur la machine, la
connexion le dit et propose le repli, plutôt que d'écouter ailleurs et d'échouer
sur une URL que le portail refuse.

LE REPLI SANS NAVIGATEUR

Sur un serveur distant, aucun navigateur n'ouvrira l'URL et aucune boucle locale
ne recevra le retour. ``--sans-navigateur`` affiche alors l'URL, que l'apprenant
ouvre **sur un autre poste**, et redemande l'URL de retour, qu'il recopie. Le
vérificateur PKCE ne bouge pas de la machine, et aucun jeton ne passe par
l'historique du shell : seul le code d'autorisation, à usage unique et inutile
sans le vérificateur, est recopié.
"""

from __future__ import annotations

import base64
import hashlib
import http.server
import json
import logging
import secrets
import socket
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from . import ErreurPortail, transport
from .jetons import Session

logger = logging.getLogger(__name__)

#: Les portées demandées. Les mêmes que le navigateur du portail, à
#: ``email`` près : dsoxlab n'affiche aucune identité, donc ne la demande pas.
PORTEES = "openid learner-sync/read learner-sync/write"

#: Délai d'attente du retour du navigateur. Large : l'apprenant peut avoir à
#: s'authentifier, voire créer son compte.
DELAI_RETOUR = 300.0

#: Délai d'un échange de jetons, qui est une requête serveur à serveur.
DELAI_ECHANGE = 20.0

_PAGE = b"""<!doctype html>
<html lang="fr"><meta charset="utf-8"><title>dsoxlab</title>
<body style="font-family:system-ui;max-width:32rem;margin:4rem auto">
<h1>Connexion terminee</h1>
<p>Vous pouvez fermer cet onglet et revenir au terminal.</p>
</body></html>"""


@dataclass
class Configuration:
    """Ce que le portail déclare pour qu'on sache lui parler.

    Aucun secret : ni mot de passe client, ni clé. Le seul champ sensible du
    contrat OAuth, le vérificateur PKCE, est tiré ici à chaque connexion.
    """

    emetteur: str
    """L'``issuer`` OIDC, qui nomme la session enregistrée."""

    domaine: str
    """La racine des points d'entrée OAuth (``/oauth2/authorize``, ``/oauth2/token``).

    Distinct de l'émetteur : chez Cognito, un **domaine personnalisé** sert les
    points d'entrée OAuth alors que l'émetteur reste l'URL du pool. Les
    confondre mène à un 404 sur l'autorisation."""

    client_id: str
    api: str = ""
    """La racine d'API de ce portail, scellée dans la session.

    Elle ne sert à aucune requête de ce module : elle est ici pour que la
    session enregistrée sache **à quel hôte** son jeton peut être présenté.
    Sans elle, la session n'était liée qu'à l'émetteur, qu'un catalogue
    quelconque peut déclarer."""

    port_retour: int = 0
    url_retour: str = ""
    """L'adresse de retour déclarée, quand le portail n'accepte pas de boucle.

    Prioritaire sur ``port_retour`` : les deux ne se cumulent pas, et le point
    d'usage refuse un catalogue qui déclarerait les deux."""


def _verificateur() -> str:
    """Un vérificateur PKCE : 43 à 128 caractères, base64url sans remplissage."""
    return base64.urlsafe_b64encode(secrets.token_bytes(64)).decode("ascii").rstrip("=")


def _condensat(verificateur: str) -> str:
    digest = hashlib.sha256(verificateur.encode("ascii")).digest()
    return base64.urlsafe_b64encode(digest).decode("ascii").rstrip("=")


def _retour(config: Configuration) -> str:
    """L'adresse de retour exacte, telle qu'elle est enregistrée chez le portail.

    Déclarée, ou la boucle locale. `127.0.0.1` et non `localhost` pour cette
    dernière : le nom peut résoudre en IPv6, et le `redirect_uri` enregistré ne
    correspondrait plus à la lettre.
    """
    if config.url_retour:
        return config.url_retour
    return f"http://127.0.0.1:{config.port_retour}/"


def url_autorisation(config: Configuration, verificateur: str, etat: str) -> str:
    """L'URL à ouvrir, avec le condensat du vérificateur et l'état."""
    params = {
        "response_type": "code",
        "client_id": config.client_id,
        "redirect_uri": _retour(config),
        "scope": PORTEES,
        "state": etat,
        "code_challenge": _condensat(verificateur),
        "code_challenge_method": "S256",
    }
    return f"{config.domaine.rstrip('/')}/oauth2/authorize?{urllib.parse.urlencode(params)}"


def _premier(params: dict[str, list[str]], cle: str) -> str | None:
    """La premiere valeur d'un parametre d'URL, ou ``None``.

    `parse_qs` rend une liste par parametre, et un `[0]` nu sur un parametre
    absent leve. Extrait pour que les deux lectures (boucle locale et URL
    recopiee) partagent la meme regle.
    """
    valeurs = params.get(cle)
    return valeurs[0] if valeurs else None


class _Retour(http.server.BaseHTTPRequestHandler):
    """Reçoit l'unique requête du navigateur, et ne sert rien d'autre.

    Le code d'autorisation arrive dans l'URL. Il est gardé sur la classe du
    serveur plutôt que rendu : ``BaseHTTPRequestHandler`` est instancié par
    requête.
    """

    code: str | None = None
    etat_recu: str | None = None
    erreur: str | None = None

    def do_GET(self) -> None:
        params = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
        type(self).code = _premier(params, "code")
        type(self).etat_recu = _premier(params, "state")
        type(self).erreur = _premier(params, "error")
        self.send_response(200)
        self.send_header("content-type", "text/html; charset=utf-8")
        self.send_header("content-length", str(len(_PAGE)))
        self.end_headers()
        self.wfile.write(_PAGE)

    def log_request(self, code: object = "-", size: object = "-") -> None:
        # `log_request` et non `log_message` : c'est le premier qui compose la
        # ligne, et il y met `self.requestline`, donc `GET /?code=…&state=…`.
        # Détourner le second recopiait le code d'autorisation dans
        # `~/.local/state/dsoxlab/dsoxlab.log`, au niveau DEBUG qui est posé
        # inconditionnellement, et ce fichier est celui que `dsoxlab support`
        # ramasse et qu'un `support --issue` publie. L'anonymiseur ne traite
        # que le home, l'utilisateur et les IPv4 : un `code=` passait tel quel.
        # Il est à usage unique et inutile sans le vérificateur PKCE, mais un
        # secret OAuth n'a rien à faire dans un rapport public.
        logger.debug("OIDC callback received (status %s)", code)

    def log_message(self, format: str, *args: object) -> None:
        # Même raison : la sortie par défaut écrit sur stderr, sous les yeux de
        # l'apprenant et de tout ce qui capture la session.
        logger.debug("OIDC callback server message")


def attendre_le_code(config: Configuration, etat: str) -> str:
    """Écoute la boucle locale et rend le code d'autorisation.

    Lève :class:`ErreurPortail` quand le portail renvoie une erreur, quand
    l'état ne correspond pas, ou quand le port est déjà pris : trois situations
    qui appellent trois messages différents, et dont une seule est une panne.
    """
    _Retour.code = _Retour.etat_recu = _Retour.erreur = None
    try:
        serveur = http.server.HTTPServer(("127.0.0.1", config.port_retour), _Retour)
    except OSError as erreur:
        raise ErreurPortail(0, "port_occupe", detail=str(erreur)) from None
    serveur.timeout = DELAI_RETOUR
    try:
        serveur.handle_request()
    finally:
        serveur.server_close()

    if _Retour.erreur:
        raise ErreurPortail(0, "autorisation_refusee", detail=_Retour.erreur)
    if _Retour.code is None:
        raise ErreurPortail(0, "retour_sans_code")
    # L'état lie le retour à CETTE demande : sans ce contrôle, un lien forgé
    # ferait échanger un code obtenu ailleurs.
    if not secrets.compare_digest(_Retour.etat_recu or "", etat):
        raise ErreurPortail(0, "etat_incoherent")
    return _Retour.code


def code_depuis_url(brut: str, etat: str) -> str:
    """Le code lu dans l'URL de retour que l'apprenant recopie.

    Accepte l'URL entière, la seule interrogation, ou le code nu : les trois
    formes se présentent selon ce que le navigateur montre, et exiger la bonne
    ferait échouer une connexion pour une question de copier-coller.
    """
    texte = brut.strip()
    if not texte:
        raise ErreurPortail(0, "retour_sans_code")
    requete = urllib.parse.urlparse(texte).query or texte.lstrip("?")
    params = urllib.parse.parse_qs(requete)
    if not params:
        # Un code nu : l'état n'a pas voyagé, on ne peut donc pas le vérifier.
        # Acceptable parce que l'apprenant a lui-même ouvert l'URL et recopié
        # ce qu'elle a rendu ; le vérificateur PKCE reste la vraie preuve.
        return texte
    erreur = _premier(params, "error")
    if erreur:
        raise ErreurPortail(0, "autorisation_refusee", detail=erreur)
    code = _premier(params, "code")
    if code is None:
        raise ErreurPortail(0, "retour_sans_code")
    recu = _premier(params, "state") or ""
    if recu and not secrets.compare_digest(recu, etat):
        raise ErreurPortail(0, "etat_incoherent")
    return code


def _echanger(config: Configuration, corps: dict[str, str]) -> Session:
    donnees = urllib.parse.urlencode(corps).encode("ascii")
    requete = urllib.request.Request(  # noqa: S310 — https, déclaré par le portail
        f"{config.domaine.rstrip('/')}/oauth2/token",
        data=donnees,
        headers={
            "content-type": "application/x-www-form-urlencoded",
            "accept": "application/json",
            "user-agent": "dsoxlab",
        },
        method="POST",
    )
    try:
        _, brut = transport.ouvrir(requete, DELAI_ECHANGE)
        charge = json.loads(brut.decode("utf-8"))
    except urllib.error.HTTPError as erreur:
        detail = ""
        try:
            lu = json.loads(transport.lire_erreur(erreur).decode("utf-8", "replace"))
            detail = str(lu.get("error") or "")
        except (TypeError, ValueError):
            pass
        raise ErreurPortail(int(erreur.code), detail or "echange_refuse") from None
    except urllib.error.URLError as erreur:
        raise ErreurPortail(0, "injoignable", detail=str(erreur.reason)) from None
    except ValueError:
        # Un 200 qui n'est pas du JSON : un portail mal configuré, ou un portail
        # captif qui rend sa page. Sans ce cas, la trace Python remontait
        # jusqu'a l'apprenant.
        raise ErreurPortail(0, "echange_illisible") from None

    acces = charge.get("access_token")
    if not isinstance(acces, str) or not acces:
        raise ErreurPortail(0, "echange_sans_jeton")
    duree = charge.get("expires_in")
    secondes = int(duree) if isinstance(duree, (int, float)) else 3600
    rafraichissement = charge.get("refresh_token")
    return Session(
        emetteur=config.emetteur,
        acces=acces,
        expire_le=datetime.now(UTC) + timedelta(seconds=secondes),
        # Absent d'un rafraîchissement : Cognito ne réémet pas le jeton de
        # rafraîchissement, et écraser l'ancien par `None` déconnecterait
        # l'apprenant au bout d'une heure. L'appelant conserve le précédent.
        rafraichissement=rafraichissement if isinstance(rafraichissement, str) else None,
        portees=str(charge.get("scope") or PORTEES),
        # Le portail au complet, scellé dans la session : c'est ce que
        # `Session.liee_a` relira pour refuser de présenter ce jeton à un hôte
        # qu'un autre catalogue aurait déclaré.
        api=config.api,
        domaine=config.domaine,
        client_id=config.client_id,
    )


def echanger_le_code(config: Configuration, code: str, verificateur: str) -> Session:
    """Le code d'autorisation contre des jetons."""
    return _echanger(config, {
        "grant_type": "authorization_code",
        "client_id": config.client_id,
        "code": code,
        "redirect_uri": _retour(config),
        "code_verifier": verificateur,
    })


def rafraichir(config: Configuration, session: Session) -> Session:
    """Un jeton d'accès neuf, sans réouvrir le navigateur.

    Conserve le jeton de rafraîchissement précédent quand la réponse n'en porte
    pas : c'est le cas chez Cognito, et l'oublier ferait redemander une
    connexion complète à chaque heure.
    """
    if not session.rafraichissement:
        raise ErreurPortail(0, "sans_rafraichissement")
    neuve = _echanger(config, {
        "grant_type": "refresh_token",
        "client_id": config.client_id,
        "refresh_token": session.rafraichissement,
    })
    if neuve.rafraichissement is None:
        neuve.rafraichissement = session.rafraichissement
    return neuve


def etat_neuf() -> str:
    return secrets.token_urlsafe(24)


def nouveau_verificateur() -> str:
    return _verificateur()


def port_libre(port: int) -> bool:
    """Vrai si la boucle locale peut écouter ce port maintenant.

    Sondé **avant** d'ouvrir le navigateur : découvrir le conflit après coup
    laisserait l'apprenant devant une page de connexion dont le retour ne
    mènerait nulle part.
    """
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as prise:
        prise.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            prise.bind(("127.0.0.1", port))
        except OSError:
            return False
    return True
