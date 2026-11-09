"""Ce que `check` et l'export disent d'un critère raté : la politique d'affichage.

Décision du propriétaire du catalogue (#336, lot D). Un lab enseigne, il peut
donc tout montrer ; un défi ne doit pas rendre la solution avec l'énoncé de
l'échec ; une épreuve ne dit que le verdict. Trois politiques, déclarées par
``feedback:`` dans le ``lab.yaml`` ou déduites du type du lab
(:attr:`dsoxlab.models.lab.LabDefinition.feedback_policy`) :

- ``full`` : le message complet de l'auteur, comme avant ;
- ``first-line`` : le libellé du critère, son verdict, et la PREMIÈRE ligne du
  message de l'auteur seulement ;
- ``verdict`` : le libellé et le verdict, aucun message.

Un critère NON ÉVALUÉ (fixture en erreur, erreur de collecte) s'affiche comme
tel, jamais comme non satisfait : l'apprenant n'a rien raté.

Ce module ne décide que de ce qui se MONTRE. Le texte reste entier dans la base
locale de l'apprenant et dans ``check.output`` du mode machine.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from ..models.lab import LabDefinition
from .lab_service import CheckResult, echecs_de_tests

#: Longueur maximale d'une observation exportée.
OBSERVATION_MAX = 280


@dataclass(frozen=True)
class LigneDeCritere:
    """Une ligne de l'écran : ce qui reste à faire, ou ce qui n'a pas pu l'être."""

    libelle: str
    etat: Literal["unsatisfied", "not_evaluated"]
    message: str | None = None


def premiere_ligne(message: str | None) -> str | None:
    """La première ligne non vide du message de l'auteur, ou ``None``."""
    if not message:
        return None
    for ligne in message.splitlines():
        propre = ligne.strip()
        if propre:
            return propre
    return None


def observation_exportee(message: str | None, politique: str) -> str | None:
    """Le message tel que l'export le porte : ``verdict`` n'en porte aucun."""
    if politique == "verdict":
        return None
    ligne = premiere_ligne(message)
    return ligne[:OBSERVATION_MAX] if ligne else None


def libelle_du_test(identifiant: str) -> str:
    """Le nom d'un test lu comme une phrase, cas paramétré conservé.

    ``test_le_mot_du_cours`` donne ``le mot du cours`` ; ``test_pair[2]`` donne
    ``pair[2]``. Les labs nomment leurs tests en phrases pour qu'ils se lisent.
    """
    fonction = identifiant.rsplit("::", 1)[-1]
    return fonction.removeprefix("test_").replace("_", " ")


def lignes_a_afficher(
    lab: LabDefinition, result: CheckResult, politique: str
) -> list[LigneDeCritere]:
    """Les critères non satisfaits ou non évalués, dans l'ordre d'exécution.

    Depuis le rapport structuré quand il existe ; sinon depuis le texte de
    pytest (``echecs_de_tests``), où tout échec est un critère non satisfait.
    Le message est coupé selon la politique : première ligne, ou rien.
    """
    lignes: list[LigneDeCritere] = []
    for critere in result.criteres or ():
        if critere.etat not in ("unsatisfied", "not_evaluated"):
            continue
        libelle = lab.libelle_de_critere(critere.identifiant) or libelle_du_test(
            critere.identifiant
        )
        message = None
        if critere.etat == "unsatisfied" and politique == "first-line":
            message = premiere_ligne(critere.message_auteur)
        etat: Literal["unsatisfied", "not_evaluated"] = (
            "not_evaluated" if critere.etat == "not_evaluated" else "unsatisfied"
        )
        lignes.append(LigneDeCritere(libelle, etat, message))
    if lignes:
        return lignes
    return [
        LigneDeCritere(
            echec.phrase,
            "unsatisfied",
            premiere_ligne(echec.message) if politique == "first-line" else None,
        )
        for echec in echecs_de_tests(result.output)
    ]
