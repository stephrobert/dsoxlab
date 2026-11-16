"""L'invitation au premier ``push``, affichée UNE fois par machine.

Une tentative de lab vit d'abord sur la machine de l'apprenant. Sans le savoir,
il ne la retrouve jamais dans « Mon apprentissage » sur le site. Après la
première tentative enregistrée (``check`` ou ``submit``), la CLI le lui dit,
une seule fois, avec les deux commandes qui l'y mènent et la phrase qui
rassure : rien n'est envoyé sans son action.

Ce que ce module ne fait JAMAIS : envoyer quoi que ce soit, ouvrir une socket,
rafraîchir un jeton. Il lit le ``meta.yml`` du catalogue et le magasin de jetons
local, et il écrit un fichier marqueur. C'est tout (brief gamification, lot A ;
critères de non-régression 1 et 2 : aucun lab n'a besoin d'un compte ni du
réseau, et un ``check`` n'émet rien sans consentement).

Les conditions, toutes à la fois :

- la tentative a été **mesurée** : une suite qui n'a rien collecté n'est pas
  une tentative, et l'inviter à l'envoyer serait faux ;
- le catalogue **déclare un portail** (``learning.sync``) : sans lui, ``push``
  est impossible, et l'on ne dit rien, comme pour le lien de remise ;
- la sortie est un **terminal** : un script ou une CI ne doit pas consommer
  l'unique affichage ;
- le **marqueur** est absent.

Le marqueur vaut pour la machine, pas pour le catalogue : la règle est « une
fois », et un apprenant qui suit trois formations ne doit pas la relire trois
fois. Il est écrit juste après l'affichage. Une écriture impossible (disque en
lecture seule) se dit au journal, et l'invitation reviendra : c'est un moindre
mal que de ne jamais la montrer.
"""

from __future__ import annotations

import logging
import sys
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from ..config import xdg_state_home

logger = logging.getLogger(__name__)


def terminal() -> bool:
    """La sortie standard est-elle un terminal ? Un script ou une CI ne consomme pas l'invitation."""
    return sys.stdout.isatty()


def chemin_du_marqueur() -> Path:
    """Le fichier qui dit que l'invitation a déjà été montrée sur cette machine."""
    return xdg_state_home() / "dsoxlab" / "invitation-push-affichee"


@dataclass(frozen=True)
class Invitation:
    """Ce qu'il faut afficher. ``avec_login`` : aucune session de ce portail n'existe."""

    avec_login: bool


def a_proposer(root: Path, *, mesuree: bool, terminal: bool) -> Invitation | None:
    """L'invitation à afficher maintenant, ou ``None``. Ne touche ni au réseau ni au disque.

    ``root`` est la racine du catalogue. Toute erreur de lecture du catalogue ou
    du magasin de jetons vaut ``None`` : une invitation ne doit jamais faire
    échouer un ``check``.
    """
    if not (mesuree and terminal) or chemin_du_marqueur().exists():
        return None
    from ..discovery.repo import read_repo_metadata
    from ..sync import SyncIndisponible, jetons
    from .sync_service import configuration

    try:
        portail = configuration(read_repo_metadata(root))
    except SyncIndisponible:
        return None
    except Exception:  # un catalogue illisible n'empêche pas le verdict
        logger.warning("push invitation skipped: catalogue unreadable", exc_info=True)
        return None
    identite = portail.identite
    try:
        session = jetons.lire(identite.emetteur)
    except Exception:
        logger.warning("push invitation: token store unreadable", exc_info=True)
        session = None
    connecte = session is not None and session.liee_a(
        identite.api, identite.domaine, identite.client_id
    )
    return Invitation(avec_login=not connecte)


def marquer_comme_affichee(version: str) -> None:
    """Écrit le marqueur. Un échec se dit au journal, jamais à l'écran."""
    chemin = chemin_du_marqueur()
    try:
        chemin.parent.mkdir(parents=True, exist_ok=True)
        chemin.write_text(
            f"{datetime.now(tz=UTC).isoformat(timespec='seconds')} dsoxlab {version}\n",
            encoding="utf-8",
        )
    except OSError as exc:
        logger.warning("push invitation marker not written (%s): it will show again", exc)
