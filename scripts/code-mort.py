#!/usr/bin/env python3
"""Nomme le code que plus personne n'appelle, sans bruit.

Pourquoi pas vulture
====================

Mesuré le 2026-10-16 : ``vulture --min-confidence 60`` rend 108 lignes sur ce
dépôt, dont **environ 80 de faux positifs structurels** : les 38 commandes
Typer, qui ne sont référencées que par un décorateur, et une quarantaine de
fixtures pytest, injectées par nom d'argument. Un contrôle à 80 % de bruit
n'est pas lu, et la ``whitelist`` qu'il faudrait maintenir grandirait à chaque
commande ajoutée.

Ce script connaît ces deux mécanismes, et quatre autres : il peut donc tourner
dans un hook et **échouer**, ce que vulture ne peut pas faire ici.

Ce qu'il regarde
================

Les symboles de **niveau module** de ``src/dsoxlab`` : fonctions, classes,
constantes. Pas les méthodes ni les attributs : un appel par ``getattr`` ou une
interface implicite les rendrait suspects à tort, et le gain ne vaut pas le
risque de faire supprimer du code vivant.

Est tenu pour vivant un symbole :

- référencé ailleurs que dans sa propre définition, dans ``src/``, ``tests/``,
  ``tests_e2e/``, ``scripts/`` ou ``fuzz/`` ;
- décoré par un enregistrement (``@app.command``, ``@pytest.fixture``…) ;
- exporté par un ``__all__`` ;
- cité par la **surface publique déclarée** ci-dessous, parce que les dépôts de
  labs l'importent depuis leur ``conftest.py`` et que ce dépôt ne voit pas ces
  appels ;
- cité dans ``docs/``, ce qui vaut pour une valeur publiée comme un code de
  sortie : un contrat documenté n'est pas du code mort, même si rien ne le
  nomme en interne.

Usage :
    python3 scripts/code-mort.py                # la liste, pour lire
    python3 scripts/code-mort.py --verifier     # sort 1 s'il y a du neuf
    python3 scripts/code-mort.py --figer        # entérine l'état courant
"""

from __future__ import annotations

import argparse
import ast
import json
import sys
from dataclasses import dataclass
from pathlib import Path

RACINE = Path(__file__).resolve().parent.parent
SOURCES = RACINE / "src" / "dsoxlab"
REFERENCE = Path(__file__).resolve().parent / "code-mort-reference.json"

#: Où chercher les usages. ``docs/`` est traité à part, en texte.
PERIMETRES = ("src", "tests", "tests_e2e", "scripts", "fuzz")

#: La surface Python que les dépôts de labs importent depuis leur
#: ``conftest.py``. Relevée le 2026-10-16 sur les huit catalogues présents.
#: C'est la seule liste qui matérialise ce contrat : rien d'autre dans ce dépôt
#: ne dit que ces symboles sont publics, et un refactoring les casserait sans
#: qu'un seul test d'ici ne bronche.
#:
#: ATTENTION : `containers-dsoxlab-training` n'était pas clonable au moment du
#: relevé. Cette liste est donc un minorant.
SURFACE_PUBLIQUE = frozenset(
    {
        "build_inventory",
        "read_terraform_outputs",
        "write_ssh_config",
        "read_repo_metadata",
        "LabDefinition",
        # `infra.ansible` et `runtimes.services` sont importés en ENTIER par
        # deux catalogues : tout symbole public y est joignable.
        "src/dsoxlab/infra/ansible.py",
        "src/dsoxlab/runtimes/services.py",
    }
)

#: Décorateurs qui enregistrent un symbole ailleurs que par son nom. Comparés
#: sur le dernier segment : `@app.command(...)`, `@catalog_app.command(...)`,
#: `@pytest.fixture`, `@property`, `@contextmanager`…
DECORATEURS_ENREGISTREURS = frozenset(
    {
        "command",
        "callback",
        "fixture",
        "property",
        "setter",
        "getter",
        "deleter",
        "contextmanager",
        "asynccontextmanager",
        "cache",
        "lru_cache",
        "cached_property",
        "overload",
        "singledispatch",
        "register",
        "hookimpl",
        "validator",
    }
)

#: Exclus : du contenu packagé, pas le moteur.
EXCLUS = ("templates/demo/", "__pycache__")


@dataclass(frozen=True)
class Symbole:
    """Un symbole de niveau module, et où il est défini."""

    nom: str
    fichier: str
    ligne: int
    genre: str

    @property
    def cle(self) -> str:
        return f"{self.fichier}::{self.nom}"


def _fichiers_python(racine: Path) -> list[Path]:
    if not racine.is_dir():
        return []
    return sorted(
        p for p in racine.rglob("*.py") if not any(e in p.as_posix() for e in EXCLUS)
    )


def _nom_decorateur(noeud: ast.expr) -> str:
    cible = noeud.func if isinstance(noeud, ast.Call) else noeud
    if isinstance(cible, ast.Attribute):
        return cible.attr
    if isinstance(cible, ast.Name):
        return cible.id
    return ""


def _est_enregistre(noeud: ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef) -> bool:
    return any(
        _nom_decorateur(d) in DECORATEURS_ENREGISTREURS for d in noeud.decorator_list
    )


def definitions() -> list[Symbole]:
    """Les symboles de niveau module de ``src/dsoxlab``, hors cas enregistrés."""
    trouves: list[Symbole] = []
    for chemin in _fichiers_python(SOURCES):
        relatif = chemin.relative_to(RACINE).as_posix()
        arbre = ast.parse(chemin.read_text(encoding="utf-8"))
        exportes = _exportes(arbre)
        for noeud in arbre.body:
            if isinstance(noeud, ast.FunctionDef | ast.AsyncFunctionDef):
                if _est_enregistre(noeud) or noeud.name.startswith("__"):
                    continue
                genre = "fonction"
            elif isinstance(noeud, ast.ClassDef):
                if _est_enregistre(noeud):
                    continue
                genre = "classe"
            elif isinstance(noeud, ast.Assign | ast.AnnAssign):
                cibles = (
                    noeud.targets if isinstance(noeud, ast.Assign) else [noeud.target]
                )
                for cible in cibles:
                    if (
                        isinstance(cible, ast.Name)
                        and cible.id.isupper()
                        and not cible.id.startswith("_")
                        and cible.id not in exportes
                    ):
                        trouves.append(
                            Symbole(cible.id, relatif, noeud.lineno, "constante")
                        )
                continue
            else:
                continue
            if noeud.name in exportes:
                continue
            trouves.append(Symbole(noeud.name, relatif, noeud.lineno, genre))
    return trouves


def _exportes(arbre: ast.Module) -> set[str]:
    """Les noms d'un ``__all__``, qui sont publics par déclaration."""
    noms: set[str] = set()
    for noeud in arbre.body:
        if isinstance(noeud, ast.Assign):
            for cible in noeud.targets:
                if (
                    isinstance(cible, ast.Name)
                    and cible.id == "__all__"
                    and isinstance(noeud.value, ast.List | ast.Tuple)
                ):
                    noms |= {
                            e.value
                            for e in noeud.value.elts
                            if isinstance(e, ast.Constant) and isinstance(e.value, str)
                        }
    return noms


def usages() -> dict[str, set[str]]:
    """Pour chaque identifiant vu, l'ensemble des fichiers qui le nomment.

    Compte les ``Name``, les ``Attribute`` (``mod.fonction``), les noms importés
    et les chaînes de caractères : un nom cité dans une chaîne peut être une
    résolution dynamique, et le bénéfice du doute va au code vivant.
    """
    vus: dict[str, set[str]] = {}

    def noter(nom: str, fichier: str) -> None:
        vus.setdefault(nom, set()).add(fichier)

    for perimetre in PERIMETRES:
        for chemin in _fichiers_python(RACINE / perimetre):
            relatif = chemin.relative_to(RACINE).as_posix()
            try:
                arbre = ast.parse(chemin.read_text(encoding="utf-8"))
            except SyntaxError:
                continue
            for noeud in ast.walk(arbre):
                if isinstance(noeud, ast.Name):
                    noter(noeud.id, relatif)
                elif isinstance(noeud, ast.Attribute):
                    noter(noeud.attr, relatif)
                elif isinstance(noeud, ast.alias):
                    noter(noeud.name.split(".")[-1], relatif)
                    if noeud.asname:
                        noter(noeud.asname, relatif)
                elif isinstance(noeud, ast.Constant) and isinstance(noeud.value, str):
                    # Un nom glissé dans une chaîne : getattr, point d'entrée,
                    # table de dispatch. Le doute profite au code vivant.
                    for mot in noeud.value.replace(".", " ").replace(",", " ").split():
                        noter(mot.strip("\"'()[]{}:"), relatif)
    return vus


def cites_dans_la_doc() -> set[str]:
    """Les mots des fichiers de ``docs/``, pour les contrats publiés."""
    mots: set[str] = set()
    docs = RACINE / "docs"
    if not docs.is_dir():
        return mots
    for chemin in docs.rglob("*.md"):
        texte = chemin.read_text(encoding="utf-8", errors="replace")
        for brut in texte.replace("`", " ").replace("(", " ").replace(")", " ").split():
            mots.add(brut.strip(".,:;|*_\"'[]"))
    return mots


def morts() -> list[Symbole]:
    """Les symboles qu'aucun périmètre ne nomme ailleurs que chez eux."""
    vus = usages()
    doc = cites_dans_la_doc()
    resultat: list[Symbole] = []
    for symbole in definitions():
        if symbole.nom in SURFACE_PUBLIQUE or symbole.fichier in SURFACE_PUBLIQUE:
            continue
        if symbole.nom in doc:
            continue
        ailleurs = vus.get(symbole.nom, set()) - {symbole.fichier}
        if ailleurs:
            continue
        # Un symbole nommé ne serait-ce qu'une fois DANS son propre fichier est
        # vivant : un helper privé n'a pas à être appelé de l'extérieur pour
        # servir. Seule l'absence TOTALE d'usage hors de sa définition compte.
        # Ce choix rend le contrôle conservateur, et c'est voulu : il doit
        # pouvoir faire échouer un commit, donc il ne doit jamais se tromper.
        if _usages_internes(symbole) >= 1:
            continue
        resultat.append(symbole)
    return sorted(resultat, key=lambda s: s.cle)


def _usages_internes(symbole: Symbole) -> int:
    """Combien de fois le fichier de définition **lit** ce symbole.

    Seules les lectures comptent. Une affectation est un ``ast.Name`` comme une
    autre, et la compter donnait un usage à toute constante : ``ETATS = (...)``
    passait pour vivante parce qu'elle était écrite une fois.
    """
    arbre = ast.parse((RACINE / symbole.fichier).read_text(encoding="utf-8"))
    compte = 0
    for noeud in ast.walk(arbre):
        if isinstance(noeud, ast.Name):
            nomme = noeud.id == symbole.nom
        elif isinstance(noeud, ast.Attribute):
            nomme = noeud.attr == symbole.nom
        else:
            continue
        if nomme and isinstance(noeud.ctx, ast.Load):
            compte += 1
    return compte


def _charger_reference() -> dict[str, str]:
    if not REFERENCE.is_file():
        return {}
    donnees = json.loads(REFERENCE.read_text(encoding="utf-8"))
    return {str(c): str(m) for c, m in donnees.get("tolere", {}).items()}


def figer(liste: list[Symbole], reference: dict[str, str]) -> None:
    """Entérine l'état courant, en gardant les motifs déjà écrits."""
    document = {
        "_lire": (
            "Code mort toléré, produit par « python3 scripts/code-mort.py --figer ». "
            "Chaque entrée doit porter un motif écrit à la main : un symbole "
            "toléré sans raison est un symbole que personne n'osera retirer. "
            "Tout nouveau mort fait échouer le hook."
        ),
        "tolere": {
            s.cle: reference.get(s.cle, "À MOTIVER : pourquoi ce symbole reste-t-il ?")
            for s in liste
        },
    }
    REFERENCE.write_text(
        json.dumps(document, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )


def main() -> int:
    analyseur = argparse.ArgumentParser(description="Code mort de src/dsoxlab.")
    analyseur.add_argument("--verifier", action="store_true", help="sort 1 s'il y a du neuf")
    analyseur.add_argument("--figer", action="store_true", help="entérine l'état courant")
    options = analyseur.parse_args()

    liste = morts()
    reference = _charger_reference()

    if options.figer:
        figer(liste, reference)
        print(f"Relevé écrit : scripts/{REFERENCE.name} ({len(liste)} symboles tolérés).")
        return 0

    if not options.verifier:
        if not liste:
            print("Aucun symbole de niveau module sans appelant.")
            return 0
        print(f"{len(liste)} symbole(s) sans appelant hors de leur fichier :")
        for symbole in liste:
            motif = reference.get(symbole.cle)
            marque = "toléré" if motif else "NOUVEAU"
            print(
                f"  [{marque}] {symbole.fichier}:{symbole.ligne} "
                f"{symbole.genre} {symbole.nom}"
            )
            if motif:
                print(f"            motif : {motif}")
        return 0

    nouveaux = [s for s in liste if s.cle not in reference]
    disparus = sorted(set(reference) - {s.cle for s in liste})

    if nouveaux:
        print("Du code sans appelant est apparu :", file=sys.stderr)
        for symbole in nouveaux:
            print(
                f"  ✘ {symbole.fichier}:{symbole.ligne} {symbole.genre} {symbole.nom}",
                file=sys.stderr,
            )
        print(
            "\nTrois issues : le retirer, le brancher sur son appelant, ou le tolérer\n"
            "sciemment par « python3 scripts/code-mort.py --figer » en écrivant le\n"
            "motif dans le relevé. Un symbole toléré sans raison est un symbole que\n"
            "personne n'osera plus retirer.",
            file=sys.stderr,
        )
        return 1

    if disparus:
        print(f"{len(disparus)} symbole(s) ne sont plus morts : le relevé est en retard.")
        for cle in disparus:
            print(f"  ✔ {cle}")
        print("\nEntériner : python3 scripts/code-mort.py --figer")
        return 1

    print(f"Aucun code mort nouveau ({len(reference)} symbole(s) tolérés).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
