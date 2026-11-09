"""Faire tenir les preuves sous les limites du portail, sans rien retirer.

Le portail garde au plus ``BRUT_PAR_SECTION`` octets bruts et
``COMPRESSE_PAR_SECTION`` octets compressés pour toutes les preuves. Depuis
0.8.0, une ligne porte le détail de la tentative (``criteria``, ``hints_seen``,
``not_evaluated``), qui la fait passer d'environ 560 octets à plus d'un kilo-octet
: un apprenant qui a beaucoup joué atteindrait la limite, et ``push`` refuserait
tout.

Plutôt que de refuser, on **allège la charge envoyée**, des lignes les plus
anciennes aux plus récentes, et seulement autant qu'il le faut :

1. ``criteria`` de la ligne la plus ancienne passe à ``None`` ;
2. si cela ne suffit pas, son ``hints_seen`` ; puis son ``not_evaluated`` ;
3. on passe à la ligne suivante, en remontant le temps.

Ce que l'allègement ne fait JAMAIS : tronquer une liste (une liste tronquée se
donnerait pour complète), retirer une ligne, toucher un champ du format v1
(compteurs, ``validated``, ``failed_checks``, ``blocking_failed``...), ni
modifier la base locale. ``None`` veut dire « inconnu » pour le portail, ce qui
est exact : le détail existe encore sur la machine de l'apprenant.

Si après allègement complet cela ne tient toujours pas, la charge est rendue
telle quelle et le refus habituel de ``push`` (``sync_charge_trop_grosse``)
s'applique : on ne cache pas une limite atteinte.

La mesure est celle du portail (:func:`protocole.mesurer_charge`) : octets bruts
d'une charge où le magasin est une chaîne échappée, et octets gzippés.
"""

from __future__ import annotations

from typing import Any

from .magasin import Magasin, Preuve, serialiser
from .protocole import BRUT_PAR_SECTION, COMPRESSE_PAR_SECTION, mesurer_charge

#: Les champs de détail, dans l'ordre où on les abandonne.
CHAMPS_ALLEGEABLES = ("criteria", "hints_seen", "not_evaluated")


def _tient(preuves: list[Preuve], dernier: str | None) -> bool:
    brut, compresse = mesurer_charge(
        serialiser({"v": 1, "preuves": preuves, "dernierImport": dernier})
    )
    return brut <= BRUT_PAR_SECTION and compresse <= COMPRESSE_PAR_SECTION


def _etapes(preuves: list[Preuve]) -> list[tuple[int, str]]:
    """Les étapes d'allègement, de la plus ancienne ligne à la plus récente.

    Une étape n'existe que si le champ est présent et non nul : alléger ce qui
    est déjà inconnu ne gagnerait rien. Le tri est stable et porte sur la date
    de tentative, donc le même magasin donne toujours le même ordre.
    """
    ordre = sorted(
        range(len(preuves)), key=lambda i: (str(preuves[i].get("attempted_at", "")), i)
    )
    return [
        (i, champ)
        for i in ordre
        for champ in CHAMPS_ALLEGEABLES
        if preuves[i].get(champ) is not None
    ]


def _appliquer(preuves: list[Preuve], etapes: list[tuple[int, str]]) -> list[Preuve]:
    """Une copie où les ``etapes`` sont appliquées ; l'original n'est pas touché."""
    copie: list[Any] = list(preuves)
    copies: set[int] = set()
    for i, champ in etapes:
        if i not in copies:
            copie[i] = dict(preuves[i])
            copies.add(i)
        copie[i][champ] = None
    return copie


def alleger(magasin: Magasin) -> tuple[Magasin, int]:
    """Le magasin à envoyer, et combien de lignes ont perdu un détail.

    Rend ``(magasin, 0)`` sans rien copier quand tout tient déjà. Sinon cherche,
    par dichotomie sur la suite ordonnée des étapes, le plus petit allègement qui
    tient sous les deux limites : chaque sonde mesure pour de vrai (sérialisation
    et gzip), parce que le rapport de compression n'est pas devinable.
    """
    preuves = magasin["preuves"]
    dernier = magasin["dernierImport"]
    if _tient(preuves, dernier):
        return magasin, 0

    etapes = _etapes(preuves)
    bas, haut = 0, len(etapes)  # `bas` ne tient pas, `haut` : à vérifier
    if not _tient(_appliquer(preuves, etapes), dernier):
        # Même allégé au maximum cela ne tient pas : on rend le tout allégé, et
        # `push` refusera en nommant la limite.
        retenues = etapes
    else:
        while haut - bas > 1:
            milieu = (bas + haut) // 2
            if _tient(_appliquer(preuves, etapes[:milieu]), dernier):
                haut = milieu
            else:
                bas = milieu
        retenues = etapes[:haut]

    allegees = _appliquer(preuves, retenues)
    touchees = len({i for i, _ in retenues})
    return {"v": 1, "preuves": allegees, "dernierImport": dernier}, touchees
