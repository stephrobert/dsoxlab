"""Journalisation : rendre visible ce que le moteur sait déjà.

Onze modules du moteur écrivent dans un logger, et aucun de ces messages
n'atteignait jamais l'utilisateur ni un fichier. Le cas le plus coûteux est
connu : un ``lab.yaml`` qui lève au parsing est avalé par un ``logger.warning``
puis un ``continue``. Le lab disparaît du catalogue **sans un mot**, et c'est le
premier symptôme que rencontre un auteur, en même temps que le plus difficile à
diagnostiquer.

Trois décisions gouvernent ce module.

1. **Le journal va sur stderr, jamais sur stdout.** ``list-labs --json`` doit
   rester lisible par un programme, y compris en mode verbeux. Un octet de
   diagnostic sur stdout casserait tout consommateur machine.

2. **Le fichier est écrit même sans option.** C'est ce qui permet de joindre une
   trace à un rapport de bug *après coup*, sans redemander à l'utilisateur de
   reproduire. Il est borné en taille : un outil de formation n'a pas à remplir
   un disque.

3. **Aucun échec de journalisation ne fait échouer une commande.** Un HOME en
   lecture seule, un disque plein ou un montage réseau absent ne doivent pas
   empêcher de jouer un lab. Le journal est un confort, pas une dépendance.
"""

from __future__ import annotations

import logging
import os
from logging.handlers import RotatingFileHandler
from pathlib import Path

from .config import xdg_state_home

#: Niveau affiché sur stderr selon le nombre de ``-v``. Au-delà de deux, on
#: reste en DEBUG : il n'existe pas de niveau plus bavard.
_NIVEAUX = {0: logging.WARNING, 1: logging.INFO}

#: Taille maximale d'un fichier de journal, et nombre d'archives conservées.
#: 1 Mo couvre largement une session de travail ; trois archives permettent de
#: retrouver la veille sans jamais dépasser 4 Mo.
_TAILLE_MAX = 1_000_000
_ARCHIVES = 3

#: Variable d'environnement équivalente aux options, pour les cas où l'on ne
#: contrôle pas la ligne de commande (script, CI, alias).
_ENV_NIVEAU = "DSOXLAB_LOG"

#: Marqueur posé sur les handlers que ce module installe, pour pouvoir les
#: retirer sans toucher à ceux d'un programme hôte. Sans lui, une suite de tests
#: qui appelle ``configurer()`` plusieurs fois empilerait les handlers, et
#: chaque message apparaîtrait autant de fois.
_MARQUEUR = "_dsoxlab_handler"


def chemin_journal() -> Path:
    """Le fichier de journal, sous le répertoire d'état XDG.

    Volontairement **global** et non par dépôt : on veut pouvoir répondre à
    « la dernière commande a échoué » sans savoir dans quel catalogue elle a
    tourné, ce que l'utilisateur qui rapporte un bug ignore souvent lui-même.
    """
    return xdg_state_home() / "dsoxlab" / "dsoxlab.log"


def _niveau_depuis_env() -> int | None:
    """``DSOXLAB_LOG=debug`` vaut ``-vv``. Une valeur inconnue est ignorée.

    Ignorer plutôt que lever : une variable mal orthographiée dans un ``.bashrc``
    ne doit pas rendre la CLI inutilisable.
    """
    brut = os.environ.get(_ENV_NIVEAU, "").strip().lower()
    if not brut:
        return None
    return {
        "debug": logging.DEBUG,
        "info": logging.INFO,
        "warning": logging.WARNING,
        "error": logging.ERROR,
    }.get(brut)


def _retirer_les_notres(racine: logging.Logger) -> None:
    for handler in list(racine.handlers):
        if getattr(handler, _MARQUEUR, False):
            racine.removeHandler(handler)
            handler.close()


def _handler_fichier() -> logging.Handler | None:
    """Le handler de fichier, ou ``None`` s'il ne peut pas être créé.

    Toutes les raisons d'échouer se valent ici (répertoire non inscriptible,
    disque plein, chemin occupé par autre chose) : aucune ne justifie de faire
    échouer la commande que l'utilisateur a lancée.
    """
    chemin = chemin_journal()
    try:
        chemin.parent.mkdir(parents=True, exist_ok=True)
        handler = RotatingFileHandler(
            chemin, maxBytes=_TAILLE_MAX, backupCount=_ARCHIVES, encoding="utf-8"
        )
    except OSError:
        return None
    handler.setLevel(logging.DEBUG)
    handler.setFormatter(
        logging.Formatter(
            "%(asctime)s %(levelname)-7s %(name)s: %(message)s",
            datefmt="%Y-%m-%dT%H:%M:%S",
        )
    )
    return handler


def configurer(verbosite: int = 0, *, debug: bool = False) -> None:
    """Installe la journalisation pour toute la durée du processus.

    Args:
        verbosite: nombre de ``-v`` passés. 0 n'affiche que les avertissements,
            1 ajoute les informations, 2 et plus ajoutent le détail.
        debug: équivalent de ``-vv``, sous un nom qui se retient.
    """
    if debug:
        verbosite = max(verbosite, 2)

    niveau_console = _NIVEAUX.get(verbosite, logging.DEBUG)
    force = _niveau_depuis_env()
    if force is not None:
        niveau_console = force

    racine = logging.getLogger("dsoxlab")
    _retirer_les_notres(racine)

    # Le logger capte tout, ce sont les handlers qui filtrent : le fichier doit
    # garder le DEBUG même quand la console n'affiche que les avertissements,
    # sans quoi le journal ne servirait à rien le jour où l'on en a besoin.
    racine.setLevel(logging.DEBUG)
    # Ne pas remonter à la racine du logging : le handler de dernier recours de
    # la bibliothèque standard écrirait une seconde copie de chaque message.
    racine.propagate = False

    console = logging.StreamHandler()  # stderr par défaut, et c'est voulu
    console.setLevel(niveau_console)
    console.setFormatter(logging.Formatter("%(levelname)s %(name)s: %(message)s"))
    setattr(console, _MARQUEUR, True)
    racine.addHandler(console)

    fichier = _handler_fichier()
    if fichier is not None:
        setattr(fichier, _MARQUEUR, True)
        racine.addHandler(fichier)


def dernieres_lignes(nombre: int = 40) -> list[str]:
    """Les dernières lignes du journal, pour un rapport de diagnostic.

    Rend une liste vide si le journal n'existe pas ou n'est pas lisible : un
    rapport sans traces reste utile, une exception en produisant un ne l'est
    pas.
    """
    chemin = chemin_journal()
    try:
        lignes = chemin.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return []
    return lignes[-nombre:]
