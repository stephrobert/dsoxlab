"""Version du **contrat d'entrée** : ``meta.yml`` et ``lab.yaml``.

Ces deux fichiers sont l'interface publique du moteur : c'est ce qu'écrit un
auteur de catalogue, et c'est la seule chose qui lie son dépôt à dsoxlab. Sans
numéro de version, un champ qui change de sens ne peut être ni annoncé, ni
détecté, ni refusé : il se manifeste par un lab qui disparaît du catalogue,
sans message.

**À ne pas confondre avec ``reporting/machine.py: SCHEMA``.** Celui-là versionne
la sortie JSON, donc ce que dsoxlab **écrit** pour un programme tiers. Celui-ci
versionne ce que dsoxlab **lit** d'un dépôt de labs. Deux contrats distincts,
deux publics, deux rythmes d'évolution : ils ne doivent jamais être couplés, ni
incrémentés ensemble par réflexe.

Règle d'évolution de la v1, telle que ``docs/contract-v1.md`` la publie :

- **ajouter** un champ optionnel ne change pas la version. Un dsoxlab plus
  ancien l'ignore, ce qu'il faisait déjà de tout champ inconnu ;
- **retirer** un champ, en rendre un obligatoire, ou changer le sens ou le type
  d'un champ existant exige une v2.
"""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from typing import Any

from ._contract import ContractError

#: Version la plus récente du contrat d'entrée que ce dsoxlab sait lire. Un
#: fichier qui en déclare une plus grande n'est pas lu : le moteur ignore ce
#: que ses champs signifient, et deviner serait pire que refuser.
SUPPORTED_SCHEMA_VERSION = 1

#: Ce que vaut l'absence de ``schema_version``. **Ne suit pas**
#: ``SUPPORTED_SCHEMA_VERSION`` : le jour où la v2 existera, un fichier muet
#: restera un fichier v1, écrit avant que la version existe. Les faire évoluer
#: ensemble reviendrait à promouvoir en silence tous les catalogues du monde.
DEFAULT_SCHEMA_VERSION = 1

#: Le nom du champ, une seule fois, pour que le validator, les modèles et les
#: schémas JSON ne puissent pas diverger sur son orthographe.
SCHEMA_VERSION_FIELD = "schema_version"


class UnsupportedSchemaVersion(ValueError):
    """Le fichier déclare une version de contrat que ce dsoxlab ne connaît pas.

    Hérite de ``ValueError`` **volontairement** : c'est le filet exact que
    ``discovery/scanner.py`` tend autour du parsing d'un ``lab.yaml``, et que
    ``cli.py`` tend autour de la lecture du ``meta.yml``. Un appelant qui ne
    connaît pas cette classe continue donc de se comporter correctement ; ceux
    qui la connaissent l'interceptent plus tôt pour en dire davantage.

    Ne porte **aucun texte destiné à l'utilisateur**, comme
    :class:`~dsoxlab.models.repo.ProviderUnresolved` : le modèle reste agnostique
    de la langue. La CLI compose le message traduit depuis ``source``, ``found``
    et ``supported``.
    """

    def __init__(
        self, source: Path, found: int, supported: int = SUPPORTED_SCHEMA_VERSION
    ) -> None:
        self.source = source
        self.found = found
        self.supported = supported
        super().__init__(
            f"{source}: schema_version {found} is beyond the contract version "
            f"{supported} this dsoxlab understands"
        )


def read_schema_version(data: Mapping[str, Any], source: Path) -> int:
    """Lit et valide ``schema_version`` à la racine d'un document du contrat.

    Args:
        data: le mapping racine déjà chargé (``meta.yml`` ou ``lab.yaml``).
        source: le fichier d'origine, nommé dans les erreurs.

    Returns:
        La version déclarée, ou :data:`DEFAULT_SCHEMA_VERSION` en son absence.

    Raises:
        UnsupportedSchemaVersion: la version dépasse celle que ce dsoxlab lit.
        ContractError: la valeur n'est pas un entier YAML, ou est inférieure à
            1. Elle porte la clé i18n et ses paramètres ; c'est la CLI qui dit
            la phrase, dans la langue de l'apprenant. Reste un ``ValueError``,
            donc le filet de ``discovery/scanner.py`` ne change pas.

    Le champ absent, ou présent mais vide (``schema_version:`` en blanc), vaut
    la v1 : **aucun catalogue existant ne doit casser**, et aucun n'en déclare
    aujourd'hui.

    La lecture est **stricte** là où le reste du contrat est tolérant : ``"1"``,
    ``1.0`` et ``true`` sont refusés, alors que :func:`~dsoxlab.models._contract.as_int`
    les accepterait. Un numéro de version n'est pas une mesure qu'on arrondit :
    ``1.5`` deviendrait ``1`` sans un mot, et c'est précisément le silence que
    ce champ existe pour supprimer. Aucun catalogue ne déclarant ce champ, la
    sévérité ne coûte rien aujourd'hui et évite d'avoir à la durcir plus tard.
    """
    if SCHEMA_VERSION_FIELD not in data:
        return DEFAULT_SCHEMA_VERSION

    brut = data[SCHEMA_VERSION_FIELD]
    if brut is None:
        return DEFAULT_SCHEMA_VERSION

    # `bool` avant `int` : True est un int en Python, donc `schema_version: true`
    # passerait pour la version 1 sans ce garde-fou.
    #
    # Les deux refus partagent la clé du validator : c'est le même fait pour
    # l'auteur (« ce n'est pas un numéro de version »), et deux textes pour un
    # seul fait finissent par diverger.
    if isinstance(brut, bool) or not isinstance(brut, int):
        raise ContractError(
            source, SCHEMA_VERSION_FIELD, "schema_version_invalid",
            got=repr(brut), supported=SUPPORTED_SCHEMA_VERSION,
        )
    if brut < 1:
        raise ContractError(
            source, SCHEMA_VERSION_FIELD, "schema_version_invalid",
            got=repr(brut), supported=SUPPORTED_SCHEMA_VERSION,
        )
    if brut > SUPPORTED_SCHEMA_VERSION:
        raise UnsupportedSchemaVersion(source, brut)
    return brut
