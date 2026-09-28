"""Lien vers le guide en ligne d'un lab, marqué pour l'attribution analytics.

Le contenu pédagogique vit sur le site du formateur, pas dans le dépôt de labs :
un lab porte son ``doc_url``. Ouvrir cette page dans le navigateur plutôt que
d'en rapatrier le contenu est délibéré. C'est la seule façon dont la lecture
compte comme une vraie visite (le script analytics s'exécute sur le domaine du
site), et cela évite d'avoir à suivre la structure HTML d'un site tiers.

Ce module ne fait que composer l'URL. Il n'ouvre rien : la CLI et une éventuelle
interface web décident quoi en faire.
"""

from __future__ import annotations

from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse

from ..models.lab import LabDefinition
from ..security.urls import PolitiqueURL, url_sure

DEFAULT_SOURCE = "dsoxlab"
DEFAULT_MEDIUM = "lab"


def guide_url(
    lab: LabDefinition,
    *,
    source: str = DEFAULT_SOURCE,
    medium: str = DEFAULT_MEDIUM,
    campaign: str | None = None,
) -> str | None:
    """URL du guide du lab, portant les paramètres de campagne, ou None.

    Retourne None quand le lab ne déclare pas de ``doc_url`` : l'appelant décide
    quoi dire à l'apprenant, ce module ne lève pas pour un champ absent.

    Les paramètres UTM sont indispensables ici, et pas seulement confortables :
    quand le lien est cliqué depuis une interface locale, le referrer transmis
    vaut au mieux ``http://localhost:<port>``, au pire rien du tout selon la
    politique du navigateur. Sans marquage, ces lectures se noieraient dans le
    trafic « direct » et l'on ne saurait jamais quel lab amène à quel guide.

    Les paramètres déjà présents dans le ``doc_url`` sont conservés, et une
    ancre (``#section``) reste intacte : le lab peut pointer une section précise
    d'un guide.
    """
    if not lab.doc_url:
        return None

    # AVANT d'y greffer quoi que ce soit. Le `doc_url` vient du catalogue, et
    # un catalogue est une entrée non fiable : `javascript:…` transformé en
    # `javascript:…?utm_source=dsoxlab` reste `javascript:`, et y ajouter des
    # paramètres de campagne ne fait que lui donner l'air d'une URL. Lever
    # plutôt que rendre None : un `doc_url` refusé n'est pas un `doc_url`
    # absent, et l'appelant doit pouvoir le dire.
    valide = url_sure(lab.doc_url, champ="doc_url", politique=PolitiqueURL.DOCUMENTATION)

    parts = urlparse(valide)
    query = dict(parse_qsl(parts.query, keep_blank_values=True))
    query.update(
        {
            "utm_source": source,
            "utm_medium": medium,
            "utm_campaign": campaign or lab.id,
        }
    )
    return urlunparse(parts._replace(query=urlencode(query)))
