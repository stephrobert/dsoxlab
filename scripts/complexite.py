#!/usr/bin/env python3
"""Mesure ce que la complexité cyclomatique ne voit pas, et refuse que ça empire.

Pourquoi ce script existe à côté de ruff
========================================

``ruff C901`` mesure la complexité **cyclomatique**, et le ``pyproject.toml`` la
plafonne. Elle ne suffit pas. Mesuré sur ``cli/_barres.py`` le 2026-10-16 :

===================================  =========  =========  ==========
fonction                             ruff C901  cognitive  profondeur
===================================  =========  =========  ==========
``_run_ansible_with_progress``               1         54           7
``_run_terraform_with_progress``            16         77           8
===================================  =========  =========  ==========

Une cyclomatique de **1** pour une fonction de 91 lignes : pour ruff, elle est
triviale, parce qu'elle n'a pas de branche. Ce que le lecteur affronte, ce sont
trois fermetures emboîtées qui se passent un état mutable. Mesurer la seule
cyclomatique aurait classé le module le plus difficile du dépôt parmi les plus
simples, et c'est exactement ce qui s'est produit pendant des mois.

Ce script mesure donc les trois grandeurs que ruff ignore :

- la **complexité cognitive** (méthode SonarSource), qui pénalise
  l'imbrication et compte les fermetures dans leur parent ;
- la **profondeur** d'imbrication ;
- la **longueur** de la fonction.

La cyclomatique n'est **pas** recalculée ici, à dessein : deux chiffres
différents pour la même grandeur dans un même dépôt est une confusion, pas une
mesure. Elle appartient à ``ruff``.

Le cliquet
==========

Un seuil absolu n'est pas jouable : 35 blocs dépassent aujourd'hui au moins un
seuil, et les interdire d'un coup bloquerait tout commit. Ce script compare donc
au relevé figé dans ``scripts/complexite-reference.json`` :

- une fonction qui empire fait **échouer** ;
- une fonction nouvelle au-dessus des seuils fait **échouer** ;
- une fonction qui s'améliore fait échouer **aussi**, avec le geste pour
  entériner le gain : une dette payée qui n'est pas enregistrée se reprend en
  silence au commit suivant.

C'est ce qui permet de traiter la dette **en même temps** qu'on produit, plutôt
que dans un chantier à part : le relevé ne peut que descendre.

Usage :
    python3 scripts/complexite.py                 # le classement, pour lire
    python3 scripts/complexite.py --verifier      # sort 1 si la dette augmente
    python3 scripts/complexite.py --figer         # entérine l'état courant
    python3 scripts/complexite.py --pires 20      # les 20 blocs les plus lourds
"""

from __future__ import annotations

import argparse
import ast
import json
import sys
from dataclasses import dataclass, field
from pathlib import Path

RACINE = Path(__file__).resolve().parent.parent
SOURCES = RACINE / "src" / "dsoxlab"
REFERENCE = Path(__file__).resolve().parent / "complexite-reference.json"

#: Au-dessus de ces valeurs, une fonction **nouvelle** est refusée. Les
#: fonctions déjà au-dessus sont tenues par le relevé, pas par ces seuils :
#: c'est la différence entre « ne pas aggraver » et « tout réparer d'abord ».
SEUIL_COGNITIVE = 20
SEUIL_PROFONDEUR = 5
SEUIL_LIGNES = 80

#: Exclus de la mesure : ce ne sont pas des unités de logique.
#:  - ``i18n/strings/`` : deux dictionnaires de 749 entrées ;
#:  - ``templates/demo/`` : du contenu pédagogique packagé, pas le moteur.
EXCLUS = ("i18n/strings/", "templates/demo/", "__pycache__")

_MESURES = ("cognitive", "profondeur", "lignes")

_IMBRIQUANTS = (
    ast.If,
    ast.For,
    ast.AsyncFor,
    ast.While,
    ast.ExceptHandler,
    ast.ListComp,
    ast.SetComp,
    ast.DictComp,
    ast.GeneratorExp,
    ast.Try,
    ast.With,
)


@dataclass(frozen=True)
class Bloc:
    """Une fonction mesurée, nommée par son chemin logique."""

    cle: str
    fichier: str
    ligne: int
    cognitive: int
    profondeur: int
    lignes: int

    def depasse(self) -> list[str]:
        """Les seuils que ce bloc dépasse, tel qu'on le dirait à l'auteur."""
        hors = []
        if self.cognitive > SEUIL_COGNITIVE:
            hors.append(f"cognitive {self.cognitive} > {SEUIL_COGNITIVE}")
        if self.profondeur > SEUIL_PROFONDEUR:
            hors.append(f"profondeur {self.profondeur} > {SEUIL_PROFONDEUR}")
        if self.lignes > SEUIL_LIGNES:
            hors.append(f"longueur {self.lignes} > {SEUIL_LIGNES}")
        return hors


@dataclass
class Ecart:
    """Ce qui a changé entre le relevé figé et la mesure du jour."""

    aggravations: list[tuple[Bloc, dict[str, int]]] = field(default_factory=list)
    nouveaux_hors_seuil: list[Bloc] = field(default_factory=list)
    ameliorations: list[tuple[Bloc, dict[str, int]]] = field(default_factory=list)
    disparus: list[str] = field(default_factory=list)

    @property
    def regresse(self) -> bool:
        return bool(self.aggravations or self.nouveaux_hors_seuil)

    @property
    def progresse(self) -> bool:
        return bool(self.ameliorations or self.disparus)


def cognitive(fn: ast.AST) -> int:
    """Complexité cognitive, méthode de G. Ann Campbell (SonarSource, 2017).

    +1 par structure de contrôle, plus un incrément égal au niveau
    d'imbrication ; +1 par ``elif``, par opérateur booléen, par rupture de flux.
    Les fonctions imbriquées **comptent** pour leur parent : c'est le seul
    moyen de voir une fermeture, et c'est tout l'objet de cette mesure.

    **Limites, à connaître avant de citer ces nombres.** Implémentation
    approchée, pas l'outil SonarSource : le traitement des séquences booléennes
    mixtes est simplifié, et les ``match``/``case`` imbriqués ne reçoivent leur
    incrément qu'au premier niveau. Elle sert à classer les fonctions entre
    elles et à détecter une aggravation, pas à être comparée à SonarQube.
    """
    score = 0

    def visiter(noeud: ast.AST, niveau: int) -> None:
        nonlocal score
        for enfant in ast.iter_child_nodes(noeud):
            inc = 0
            imbrique = False
            if isinstance(enfant, ast.If):
                inc, imbrique = 1 + niveau, True
                inc += sum(1 for sous in enfant.orelse if isinstance(sous, ast.If))
            elif isinstance(
                enfant,
                ast.For
                | ast.AsyncFor
                | ast.While
                | ast.ExceptHandler
                | ast.ListComp
                | ast.SetComp
                | ast.DictComp
                | ast.GeneratorExp,
            ):
                inc, imbrique = 1 + niveau, True
            elif isinstance(enfant, ast.IfExp | ast.match_case):
                inc = 1 + niveau
            elif isinstance(enfant, ast.BoolOp | ast.Break | ast.Continue):
                inc = 1
            elif isinstance(enfant, ast.FunctionDef | ast.AsyncFunctionDef | ast.Lambda):
                imbrique = True
            score += inc
            visiter(enfant, niveau + 1 if imbrique else niveau)

    visiter(fn, 0)
    return score


def profondeur(fn: ast.AST) -> int:
    """Niveau maximal d'imbrication de structures de contrôle."""
    pire = 0

    def visiter(noeud: ast.AST, courant: int) -> None:
        nonlocal pire
        pire = max(pire, courant)
        for enfant in ast.iter_child_nodes(noeud):
            visiter(enfant, courant + (1 if isinstance(enfant, _IMBRIQUANTS) else 0))

    visiter(fn, 0)
    return pire


def _fichiers() -> list[Path]:
    return sorted(
        p for p in SOURCES.rglob("*.py") if not any(e in p.as_posix() for e in EXCLUS)
    )


def mesurer() -> list[Bloc]:
    """Toutes les fonctions de ``src/dsoxlab``, mesurées trois fois."""
    blocs: list[Bloc] = []
    for chemin in _fichiers():
        relatif = chemin.relative_to(RACINE).as_posix()
        arbre = ast.parse(chemin.read_text(encoding="utf-8"))
        # Le chemin logique porte la classe ou la fonction englobante : deux
        # `from_yaml` dans le même module ne doivent pas se confondre, et un
        # `on_event` doit être nommé par la fonction qui le définit.
        pile: list[tuple[ast.AST, str]] = [(arbre, "")]
        while pile:
            noeud, prefixe = pile.pop()
            for enfant in ast.iter_child_nodes(noeud):
                if isinstance(enfant, ast.ClassDef):
                    pile.append((enfant, f"{prefixe}{enfant.name}."))
                elif isinstance(enfant, ast.FunctionDef | ast.AsyncFunctionDef):
                    nom = f"{prefixe}{enfant.name}"
                    blocs.append(
                        Bloc(
                            cle=f"{relatif}::{nom}",
                            fichier=relatif,
                            ligne=enfant.lineno,
                            cognitive=cognitive(enfant),
                            profondeur=profondeur(enfant),
                            lignes=(enfant.end_lineno or enfant.lineno) - enfant.lineno + 1,
                        )
                    )
                    pile.append((enfant, f"{nom}."))
    return blocs


def _charger_reference() -> dict[str, dict[str, int]]:
    if not REFERENCE.is_file():
        return {}
    donnees = json.loads(REFERENCE.read_text(encoding="utf-8"))
    return {str(c): dict(v) for c, v in donnees.get("blocs", {}).items()}


def comparer(blocs: list[Bloc], reference: dict[str, dict[str, int]]) -> Ecart:
    """Confronte la mesure du jour au relevé figé."""
    ecart = Ecart()
    for bloc in blocs:
        ancien = reference.get(bloc.cle)
        if ancien is None:
            if bloc.depasse():
                ecart.nouveaux_hors_seuil.append(bloc)
            continue
        pires = {
            nom: ancien[nom]
            for nom in _MESURES
            if nom in ancien and getattr(bloc, nom) > ancien[nom]
        }
        if pires:
            ecart.aggravations.append((bloc, pires))
            continue
        mieux = {
            nom: ancien[nom]
            for nom in _MESURES
            if nom in ancien and getattr(bloc, nom) < ancien[nom]
        }
        if mieux:
            ecart.ameliorations.append((bloc, mieux))
    ecart.disparus = sorted(set(reference) - {b.cle for b in blocs})
    return ecart


def figer(blocs: list[Bloc]) -> None:
    """Écrit le relevé. Seuls les blocs qui dépassent un seuil y figurent.

    Figer les 626 blocs du dépôt produirait un fichier que personne ne relit et
    un diff illisible au moindre renommage. Le relevé ne retient donc que la
    dette : ce qui est déjà simple est tenu par les seuils.
    """
    retenus = sorted((b for b in blocs if b.depasse()), key=lambda b: b.cle)
    document = {
        "_lire": (
            "Relevé de dette de complexité, produit par « python3 "
            "scripts/complexite.py --figer ». Il ne peut que descendre : toute "
            "aggravation fait échouer le hook. Les blocs absents de ce relevé "
            "sont tenus par les seuils déclarés ci-dessous. La complexité "
            "cyclomatique n'est pas ici : elle appartient à ruff C901."
        ),
        "seuils": {
            "cognitive": SEUIL_COGNITIVE,
            "profondeur": SEUIL_PROFONDEUR,
            "lignes": SEUIL_LIGNES,
        },
        "blocs": {
            b.cle: {"cognitive": b.cognitive, "profondeur": b.profondeur, "lignes": b.lignes}
            for b in retenus
        },
    }
    REFERENCE.write_text(
        json.dumps(document, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )


def _afficher_classement(blocs: list[Bloc], combien: int) -> None:
    pires = sorted(blocs, key=lambda b: (-b.cognitive, -b.lignes))[:combien]
    print(f"{'cogn':>5} {'prof':>5} {'lignes':>7}  bloc")
    for bloc in pires:
        print(
            f"{bloc.cognitive:>5} {bloc.profondeur:>5} {bloc.lignes:>7}  "
            f"{bloc.cle}:{bloc.ligne}"
        )
    hors = [b for b in blocs if b.depasse()]
    print()
    print(f"blocs mesurés : {len(blocs)}")
    print(f"blocs au-dessus d'au moins un seuil : {len(hors)}")
    print(f"cognitive cumulée : {sum(b.cognitive for b in blocs)}")


def _afficher_regression(ecart: Ecart) -> None:
    for bloc, pires in ecart.aggravations:
        details = ", ".join(
            f"{nom} {avant} -> {getattr(bloc, nom)}" for nom, avant in pires.items()
        )
        print(f"  ✘ {bloc.cle}:{bloc.ligne} aggravé : {details}", file=sys.stderr)
    for bloc in ecart.nouveaux_hors_seuil:
        print(
            f"  ✘ {bloc.cle}:{bloc.ligne} nouveau et hors seuil : "
            f"{', '.join(bloc.depasse())}",
            file=sys.stderr,
        )


def main() -> int:
    analyseur = argparse.ArgumentParser(description="Complexité cognitive de src/dsoxlab.")
    analyseur.add_argument("--verifier", action="store_true", help="sort 1 si la dette augmente")
    analyseur.add_argument("--figer", action="store_true", help="entérine l'état courant")
    analyseur.add_argument("--pires", type=int, default=15, help="taille du classement affiché")
    options = analyseur.parse_args()

    blocs = mesurer()

    if options.figer:
        figer(blocs)
        retenus = sum(1 for b in blocs if b.depasse())
        print(f"Relevé écrit : scripts/{REFERENCE.name} ({retenus} blocs de dette).")
        return 0

    if not options.verifier:
        _afficher_classement(blocs, options.pires)
        return 0

    reference = _charger_reference()
    if not reference:
        print(
            "Aucun relevé de référence. Le poser une fois :\n"
            "  python3 scripts/complexite.py --figer",
            file=sys.stderr,
        )
        # Sortie 2, jamais 0 : « je n'ai rien pu comparer » n'est pas « tout va
        # bien ». C'est la règle que ce dépôt applique déjà à doctor --strict.
        return 2

    ecart = comparer(blocs, reference)

    if ecart.regresse:
        print("La complexité augmente :", file=sys.stderr)
        _afficher_regression(ecart)
        print(
            "\nDeux issues, et une seule est bonne : simplifier la fonction, ou\n"
            "entériner sciemment la dette par « python3 scripts/complexite.py --figer »\n"
            "en disant dans le message de commit pourquoi elle était nécessaire.",
            file=sys.stderr,
        )
        return 1

    if ecart.progresse:
        gains = len(ecart.ameliorations) + len(ecart.disparus)
        print(f"La complexité baisse sur {gains} bloc(s) : le relevé est en retard.")
        for bloc, mieux in ecart.ameliorations[:10]:
            details = ", ".join(
                f"{nom} {avant} -> {getattr(bloc, nom)}" for nom, avant in mieux.items()
            )
            print(f"  ✔ {bloc.cle} : {details}")
        for cle in ecart.disparus[:10]:
            print(f"  ✔ {cle} : plus de dette (simplifiée, renommée ou retirée)")
        print(
            "\nEntériner le gain, sinon il se reprendra en silence :\n"
            "  python3 scripts/complexite.py --figer"
        )
        return 1

    print(f"Complexité stable sur {len(blocs)} blocs ({len(reference)} en dette connue).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
