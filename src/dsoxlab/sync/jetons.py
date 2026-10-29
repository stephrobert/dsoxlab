"""Où vivent les jetons, et pourquoi pas ailleurs.

TROIS ENDROITS OÙ ILS NE DOIVENT PAS ÊTRE

- **le dépôt de labs**, qui est versionné : un jeton commité est un jeton
  publié, et `git` ne l'oublie pas ;
- **une variable d'environnement**, qui se lit dans ``/proc`` et se recopie
  dans tout processus enfant, dont `terraform` et `ansible` ;
- **l'historique du shell**, où une option ``--jeton`` l'écrirait en clair.
  C'est pour cela que cette option n'existe pas.

OÙ ILS SONT, ET LA LIMITE ASSUMÉE

Sous ``XDG_STATE_HOME``, un fichier par portail, en **0600** dans un
répertoire en **0700**. C'est de l'état dérivé, pas de la configuration : il se
jette sans rien perdre d'autre qu'une reconnexion.

Ce n'est **pas** le trousseau du système, et c'est une limite consciente. Un
trousseau demanderait une dépendance d'exécution de plus (``keyring``, et ses
greffons par plateforme) pour un gain réel mais partiel : il protège contre un
autre utilisateur de la machine, pas contre un processus qui tourne sous le
compte de l'apprenant, lequel peut de toute façon lire ce fichier. Les
dépendances de dsoxlab se comptent sur une main et cette décision appartient à
celui qui tranche le périmètre, pas à ce module. Le jour où elle se prend,
seule l'implémentation de ce fichier change.

UN FICHIER PAR PORTAIL, ET LA CLÉ EST L'ÉMETTEUR

Pas par dépôt de labs : un même compte sert tous les catalogues du même
portail, et demander une connexion par catalogue serait absurde. Pas un fichier
unique non plus : deux portails distincts ne partagent pas une session, et
écraser l'un en se connectant à l'autre serait un défaut difficile à voir.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import stat
import tempfile
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path

from ..config import xdg_state_home

#: Marge avant l'expiration : un jeton valable dix secondes ne survivra pas à
#: l'aller-retour qu'on s'apprête à faire.
MARGE_EXPIRATION = timedelta(seconds=60)

_NOM_SUR = re.compile(r"[^a-z0-9.-]+")


@dataclass
class Session:
    """Ce qu'on garde d'une connexion, et rien de plus.

    Pas d'adresse de courriel, pas de nom, pas de ``sub`` : dsoxlab n'a aucun
    usage de l'identité de l'apprenant. C'est le portail qui la lit dans le
    jeton, et lui seul.
    """

    emetteur: str
    """L'``issuer`` OIDC, qui identifie le portail et nomme le fichier."""

    acces: str
    expire_le: datetime
    rafraichissement: str | None = None
    portees: str = ""

    api: str = ""
    """La racine d'API **pour laquelle** cette session a été obtenue.

    Enregistrée, et pas seulement l'émetteur, parce que c'est le seul hôte à
    qui ce jeton sera présenté. Voir :func:`liee_a`."""

    domaine: str = ""
    """Le domaine OAuth où le rafraîchissement sera présenté."""

    client_id: str = ""
    """Le client pour lequel ce jeton a été émis."""

    @property
    def expire(self) -> bool:
        return datetime.now(UTC) + MARGE_EXPIRATION >= self.expire_le

    def liee_a(self, api: str, domaine: str, client_id: str) -> bool:
        """Vrai si cette session a bien été obtenue pour CE portail-là.

        **C'est un contrôle de sécurité, pas une commodité.** La session est
        nommée par le seul émetteur, et l'émetteur est déclaré par le
        ``meta.yml`` d'un catalogue, donc par un dépôt que `catalog add` clone
        depuis une adresse quelconque. Sans ce contrôle, un catalogue tiers
        déclarant l'émetteur du vrai portail et sa propre ``api`` récupérait la
        session de l'apprenant : au premier ``push``, et **avant toute
        écriture**, le jeton d'accès partait vers l'hôte de son choix ; une fois
        l'heure écoulée, c'est le jeton de rafraîchissement, secret de longue
        durée que Cognito ne fait pas tourner, qui partait vers son
        ``oauth_domain``. Mesuré sur cette branche avant correction : les trois
        adresses étaient validées **indépendamment**, aucune n'avait à
        s'accorder avec les autres, et le fichier de session visé était bien
        celui du vrai portail.

        Une session d'avant ce champ (``api`` vide) ne correspond à rien et
        appelle une reconnexion : c'est un geste, pas une perte.
        """
        return bool(self.api) and (self.api, self.domaine, self.client_id) == (
            api,
            domaine,
            client_id,
        )


def _racine() -> Path:
    return xdg_state_home() / "dsoxlab" / "sessions"


def chemin(emetteur: str) -> Path:
    """Le fichier de session d'un portail.

    Le nom dérive de l'émetteur, assaini **et** suffixé d'un condensat : un
    émetteur peut contenir des caractères qui ne font pas un nom de fichier, et
    deux émetteurs distincts pourraient s'assainir en un même nom. Le condensat
    lève l'ambiguïté sans rendre le nom illisible pour qui inspecte le
    répertoire.
    """
    lisible = _NOM_SUR.sub("-", emetteur.lower().removeprefix("https://")).strip("-")
    empreinte = hashlib.sha256(emetteur.encode("utf-8")).hexdigest()[:8]
    return _racine() / f"{lisible[:60]}-{empreinte}.json"


def lire(emetteur: str) -> Session | None:
    """La session enregistrée pour ce portail, ou ``None``.

    Un fichier illisible ou d'une forme inconnue vaut « pas de session » : il
    sera réécrit à la prochaine connexion. On ne lève pas, parce qu'il n'y a
    rien à réparer et que l'apprenant n'a qu'un geste à faire.
    """
    fichier = chemin(emetteur)
    try:
        charge = json.loads(fichier.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    if not isinstance(charge, dict) or charge.get("v") != 1:
        return None
    acces = charge.get("acces")
    expire = charge.get("expire_le")
    if not isinstance(acces, str) or not isinstance(expire, str):
        return None
    try:
        quand = datetime.fromisoformat(expire)
    except ValueError:
        return None
    if quand.tzinfo is None:
        return None
    rafraichissement = charge.get("rafraichissement")
    portees = charge.get("portees")

    def _texte(cle: str) -> str:
        valeur = charge.get(cle)
        return valeur if isinstance(valeur, str) else ""

    return Session(
        emetteur=emetteur,
        acces=acces,
        expire_le=quand,
        rafraichissement=rafraichissement if isinstance(rafraichissement, str) else None,
        portees=portees if isinstance(portees, str) else "",
        api=_texte("api"),
        domaine=_texte("domaine"),
        client_id=_texte("client_id"),
    )


def ecrire(session: Session) -> Path:
    """Enregistre la session, en 0600, sans fenêtre où le fichier serait lisible.

    Le mode est posé sur le fichier **temporaire**, avant le remplacement
    atomique : créer puis restreindre laisserait un instant, court mais réel, où
    un jeton serait lisible par tout le monde. Même précaution que pour le
    ``ssh_config`` généré.
    """
    racine = _racine()
    racine.mkdir(parents=True, exist_ok=True)
    os.chmod(racine, stat.S_IRWXU)  # noqa: PTH101 — 0700, et seulement ce répertoire

    charge = {
        "v": 1,
        "emetteur": session.emetteur,
        "acces": session.acces,
        "expire_le": session.expire_le.isoformat(),
        "rafraichissement": session.rafraichissement,
        "portees": session.portees,
        # Le portail entier, pas seulement son émetteur : c'est ce qui permet
        # de refuser une session à un catalogue qui déclare un autre hôte.
        "api": session.api,
        "domaine": session.domaine,
        "client_id": session.client_id,
    }
    cible = chemin(session.emetteur)
    descripteur, provisoire = tempfile.mkstemp(dir=str(racine), prefix=".session-")
    try:
        os.fchmod(descripteur, stat.S_IRUSR | stat.S_IWUSR)  # 0600 avant d'écrire
        with os.fdopen(descripteur, "w", encoding="utf-8") as sortie:
            json.dump(charge, sortie, ensure_ascii=False)
        Path(provisoire).replace(cible)
    except BaseException:
        Path(provisoire).unlink(missing_ok=True)
        raise
    return cible


def oublier(emetteur: str) -> bool:
    """Efface la session de ce portail. Rend vrai si un fichier a été retiré.

    Efface **le fichier**, et ne tente pas de révoquer le jeton côté portail :
    une révocation qui échoue laisserait l'apprenant croire qu'il est déconnecté
    alors qu'un jeton vit encore. La CLI dit donc exactement ce qu'elle a fait,
    et rappelle où se déconnecter vraiment.
    """
    fichier = chemin(emetteur)
    try:
        fichier.unlink()
    except FileNotFoundError:
        return False
    except OSError:
        return False
    return True
