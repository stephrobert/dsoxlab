"""Le seul endroit d'où dsoxlab parle à un portail, et ce qu'il refuse d'y faire.

DEUX GARDE-FOUS, ET AUCUN DES DEUX N'EST LE DÉFAUT DE ``urllib``

**On ne suit aucune redirection.** ``urllib.request.urlopen`` installe un
``HTTPRedirectHandler`` par défaut, qui ne retire de la requête rejouée que
``content-length`` et ``content-type`` : l'en-tête ``Authorization`` **survit**,
et la cible peut être en ``http``. Un portail qui répondrait
``302 Location: http://ailleurs.test/`` à un ``GET`` ferait donc partir le jeton
de l'apprenant vers cet hôte, en clair, en contournant la politique d'URL qui
n'a contrôlé que l'adresse de départ. Le ``PUT`` était déjà épargné, ``urllib``
refusant de rejouer cette méthode ; le ``GET`` ne l'était pas. Une redirection
n'a ici aucun usage légitime : les chemins du protocole sont fixes.

**On ne lit pas une réponse sans borne.** L'hôte est déclaré par un `meta.yml`,
donc par un dépôt que `catalog add` clone depuis une adresse quelconque. Une
réponse de plusieurs gigaoctets épuiserait la mémoire du poste. La borne est
large devant toute réponse légitime, et c'est voulu : elle arrête un abus, elle
ne rogne aucun cas réel.
"""

from __future__ import annotations

import urllib.error
import urllib.request

#: Au-delà, on arrête de lire. Le magasin le plus gros que le portail accepte
#: tient dans 350 ko ; 8 Mo laissent toute la marge voulue à une réponse
#: légitime, y compris une erreur bavarde.
REPONSE_MAX = 8 * 1024 * 1024


class _SansRedirection(urllib.request.HTTPRedirectHandler):
    """Refuse toute redirection, au lieu de la suivre avec le jeton."""

    def redirect_request(self, *_args: object, **_kwargs: object) -> None:
        return None


#: Construit une fois : un opener porte des connexions et n'a pas à être recréé
#: à chaque appel. Sans gestionnaire de cookies ni d'authentification, et sans
#: redirection.
_OPENER = urllib.request.build_opener(_SansRedirection)


def ouvrir(requete: urllib.request.Request, delai: float) -> tuple[int, bytes]:
    """Joue la requête et rend ``(statut, corps borné)``.

    Lève les mêmes exceptions que ``urlopen`` : l'appelant les traduit, chacun
    selon ce qu'il sait du protocole.
    """
    with _OPENER.open(requete, timeout=delai) as reponse:
        return int(reponse.status), reponse.read(REPONSE_MAX)


def lire_erreur(erreur: urllib.error.HTTPError) -> bytes:
    """Le corps d'une erreur HTTP, borné lui aussi.

    Un portail qui refuse n'est pas moins capable de répondre trop : le corps
    d'erreur passe par la même borne que le corps de succès.
    """
    try:
        return bytes(erreur.read(REPONSE_MAX))
    except OSError:
        return b""
