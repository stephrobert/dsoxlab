"""Envoi des preuves vers le portail que le catalogue déclare.

**Ce paquet est opt-in de bout en bout.** Rien ne part sans que trois choses
coïncident : le catalogue déclare un `learning.sync`, l'apprenant a joué
`dsoxlab login`, et il tape `dsoxlab push`. Aucun `check`, aucun `submit`,
aucune commande de parcours n'envoie quoi que ce soit.

C'est une **inversion assumée** d'un invariant précédent. La docstring de
:class:`dsoxlab.models.repo.LearningDefinition` affirmait « il n'envoie rien,
jamais » : c'était vrai du seul `portal_url`, un lien que l'apprenant lit et
décide d'ouvrir. Cette partie-là ne change pas. Ce qui change est qu'un
catalogue peut désormais déclarer, **en plus**, une API de synchronisation.

Ce qui ne change pas, et qui comptait vraiment dans l'invariant :

- **le catalogue ne porte aucun secret.** Ni jeton, ni clé d'API, ni en-tête
  d'autorisation. Un dépôt versionné n'est pas un endroit où poser un secret,
  et le client OAuth déclaré ici est **public** : PKCE ne demande pas de
  secret, c'est tout son intérêt ;
- **le catalogue ne donne pas d'ordres au moteur.** Il déclare une adresse et
  un protocole ; il ne déclenche rien ;
- **l'identité ne vient jamais d'un paramètre.** Le serveur la lit dans les
  revendications du jeton vérifié, et dsoxlab n'a aucun moyen de la poser.

Découpage, et pourquoi il y a trois modules plutôt qu'un :

- :mod:`.magasin` ne parle que de **forme** : il transforme l'historique local
  en ce que le portail sait relire, et refuse d'émettre ce que le portail
  écarterait. Aucun réseau, donc testable sans serveur ;
- :mod:`.oidc` ne parle que d'**identité** : obtenir un jeton par PKCE ;
- :mod:`.protocole` ne parle que de **transport** : l'enveloppe, les codes et
  la reprise sur conflit.

Un défaut de l'un ne se diagnostique pas dans l'autre, et c'est le but : les
trois familles d'échec qu'on rencontre ici (ma charge est mal formée, je ne
suis pas authentifié, quelqu'un a écrit avant moi) appellent trois gestes
opposés.
"""

from __future__ import annotations


class SyncIndisponible(RuntimeError):
    """Le catalogue ne déclare aucune synchronisation, ou la déclare mal.

    Distincte d'une panne : il n'y a rien à joindre, donc rien à réessayer.
    Le message nomme ce qui manque dans le ``meta.yml``.
    """

    def __init__(self, cle: str, **params: object) -> None:
        self.cle = cle
        self.params = params
        super().__init__(cle)


class SansSession(RuntimeError):
    """Aucun jeton utilisable : `dsoxlab login` n'a pas été joué, ou il a expiré.

    Séparée des erreurs de transport parce que le geste est différent : ce
    n'est pas un réessai, c'est une connexion.
    """

    def __init__(self, cle: str = "sync_sans_session", **params: object) -> None:
        self.cle = cle
        self.params = params
        super().__init__(cle)


class ErreurPortail(RuntimeError):
    """Le portail a répondu, et il a refusé.

    Porte le statut HTTP **et** le code stable du corps (``erreur.code``), car
    les deux ne disent pas la même chose : un ``409`` se reprend par une
    fusion quand son code est ``revision``, et ne se reprend jamais quand il
    est ``operation-reutilisee``, qui dit un défaut de la CLI.
    """

    def __init__(self, statut: int, code: str, *, detail: str = "") -> None:
        self.statut = statut
        self.code = code
        self.detail = detail
        super().__init__(f"{statut} {code}")


class ChargeRefusee(ValueError):
    """La charge ne peut pas partir : elle dépasse une limite du contrat.

    Levée **avant** l'envoi. Le portail la refuserait aussi, mais il le dirait
    après un aller-retour, en langage de passerelle, et sans dire laquelle.
    """

    def __init__(self, cle: str, **params: object) -> None:
        self.cle = cle
        self.params = params
        super().__init__(cle)


__all__ = [
    "ChargeRefusee",
    "ErreurPortail",
    "SansSession",
    "SyncIndisponible",
]
