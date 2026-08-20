"""test_functional.py — premiers-pas

Prouve l'ÉTAT produit, jamais les commandes tapées : ce sont les trois fichiers
de `reponses/` qui sont lus. C'est la règle de tous les labs dsoxlab, et ce lab
existe justement pour la faire comprendre.

Le barème est réparti à parts égales entre les trois étapes de la boucle : lire
le cours, lire la mission, demander un indice.
"""
from __future__ import annotations

import pathlib

WORK = pathlib.Path()
REPONSES = WORK / "reponses"

#: Le mot attendu dans chaque fichier, et où l'apprenant le trouve.
ATTENDUS = {
    "cours.txt": ("catalogue", "dsoxlab course premiers-pas"),
    "mission.txt": ("challenge", "dsoxlab challenge premiers-pas"),
    "indice.txt": ("progression", "dsoxlab hint premiers-pas"),
}


def _verifier(nom: str) -> None:
    mot, ou = ATTENDUS[nom]
    fichier = REPONSES / nom

    assert fichier.exists(), (
        f"{fichier} manquant. Le mot attendu se lit dans : {ou}\n"
        f"Crée le fichier, par exemple : mkdir -p reponses && "
        f"echo <le mot> > reponses/{nom}"
    )

    contenu = fichier.read_text(encoding="utf-8", errors="replace").strip().lower()
    assert contenu, f"{fichier} est vide. Le mot attendu se lit dans : {ou}"
    assert mot in contenu, (
        f"{fichier} ne contient pas le mot attendu.\n"
        f"Il se lit dans : {ou}\n"
        f"Obtenu : {contenu[:60]!r}"
    )


def test_le_mot_du_cours() -> None:
    """Première étape de la boucle : lire le cours."""
    _verifier("cours.txt")


def test_le_mot_de_la_mission() -> None:
    """Deuxième étape : lire la mission, qui dit ce qu'il faut produire."""
    _verifier("mission.txt")


def test_le_mot_de_l_indice() -> None:
    """Troisième étape : demander un indice, et voir ce qu'il coûte.

    Ce test est là pour que l'apprenant fasse le geste au moins une fois, sur
    un lab où la dépense est sans conséquence.
    """
    _verifier("indice.txt")
