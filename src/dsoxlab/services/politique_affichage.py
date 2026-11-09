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
from .lab_service import CheckResult, EchecDeTest, echecs_de_tests
from .rapport_de_criteres import ResultatDeCritere, nom_de_controle

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


def separer_les_non_evalues(
    lab: LabDefinition, result: CheckResult, echecs: list[EchecDeTest]
) -> tuple[list[LigneDeCritere], list[EchecDeTest]]:
    """Sépare ce qui n'a PAS PU être vérifié de ce que l'apprenant a raté.

    Pourquoi cette fonction existe
    ------------------------------

    La politique ``full`` montre les échecs par le texte de pytest
    (:func:`echecs_de_tests`), qui range un ``ERROR`` de collecte ou de fixture
    avec les ``FAILED``. Un critère que la machine n'a pas pu évaluer
    s'affichait donc comme un travail faux, sans la mention que ``first-line``
    et ``verdict`` portent déjà (issue #350). Les deux réactions attendues sont
    opposées : corriger son travail d'un côté, relancer ``check`` ou regarder
    son poste de l'autre.

    Rend ``([], echecs)`` tel quel quand aucun rapport structuré n'existe : sans
    lui, rien ne permet de distinguer les deux, et inventer la distinction
    serait pire que l'absence.

    Un critère DÉCLARÉ regroupe plusieurs tests et ne garde que le ``nodeid`` du
    premier : ses membres se lisent donc dans ``criteria:``, faute de quoi les
    autres resteraient dans la liste des échecs, et la même vérification
    bloquée se dirait deux fois de deux façons.
    """
    if not result.criteres:
        return [], echecs
    lignes: list[LigneDeCritere] = []
    noms_bloques: set[str] = set()
    for critere in result.criteres:
        if critere.etat != "not_evaluated":
            continue
        lignes.append(LigneDeCritere(
            lab.libelle_de_critere(critere.identifiant)
            or libelle_du_test(critere.identifiant),
            "not_evaluated",
        ))
        noms_bloques.update(_tests_du_critere(lab, critere))
    if not noms_bloques:
        return lignes, echecs
    return lignes, [e for e in echecs if e.nom not in noms_bloques]


def _tests_du_critere(lab: LabDefinition, critere: ResultatDeCritere) -> set[str]:
    """Les noms de fonctions de test que ce critère couvre."""
    for declare in lab.criteria:
        if declare.id == critere.identifiant:
            return {nom_de_controle(nom) for nom in declare.tests}
    return {nom_de_controle(critere.nodeid)}
