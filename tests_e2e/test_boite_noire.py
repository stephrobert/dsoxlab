"""La règle de cette suite, tenue par un test plutôt que par la bonne volonté.

**Aucun fichier de `tests_e2e/` n'importe `dsoxlab`.** C'est ce qui fait la
différence entre « les fonctions font ce qu'elles disent » et « le programme
installé se comporte comme promis ». Un import, même innocent, même dans un
helper, rouvre la porte : on se remettrait à interroger le paquet source au
lieu du binaire, et l'empaquetage cesserait d'être testé sans que la suite
change de couleur.

Le principe est celui de `tests/test_i18n_coverage.py`, qui analyse `cli.py`
pour interdire les chaînes en dur : une règle écrite en prose ne tient pas, une
règle vérifiée tient. Trois portes, parce qu'une seule se contourne :

1. l'analyse syntaxique attrape `import dsoxlab` et `from dsoxlab… import …` ;
2. elle attrape aussi l'import dynamique, `importlib.import_module("dsoxlab")`
   et `__import__("dsoxlab")`, qu'aucune lecture d'`ast.Import` ne verrait ;
3. et l'état du processus tranche à l'exécution : si le paquet avait été chargé
   par un chemin auquel personne n'a pensé, il serait dans `sys.modules`.

Pour vérifier que ce garde-fou mord, ajoutez `import dsoxlab` en tête de
n'importe quel fichier de ce répertoire : les trois tests passent au rouge.
"""

from __future__ import annotations

import ast
import sys
from pathlib import Path

#: Tous les fichiers Python de la suite, conftest compris. `rglob` et non
#: `glob` : un sous-répertoire d'aides ne doit pas échapper à la règle.
SUITE = sorted(Path(__file__).resolve().parent.rglob("*.py"))

#: Le paquet interdit. Écrit une fois, pour que la règle se lise.
INTERDIT = "dsoxlab"

#: Les portes d'entrée de l'import dynamique.
IMPORTEURS = {"import_module", "__import__"}


def _vise_le_paquet(nom: str | None) -> bool:
    """Le nom de module désigne-t-il `dsoxlab` ou l'un de ses sous-modules ?"""
    return bool(nom) and (nom == INTERDIT or str(nom).startswith(f"{INTERDIT}."))


def _arbre(fichier: Path) -> ast.Module:
    return ast.parse(fichier.read_text(encoding="utf-8"), filename=str(fichier))


def test_la_suite_a_bien_des_fichiers_a_controler() -> None:
    """Un garde-fou qui ne regarde rien est vert pour de mauvaises raisons.

    Si la découverte cassait, les trois tests suivants passeraient sur une
    liste vide et ne prouveraient plus rien.
    """
    noms = {fichier.name for fichier in SUITE}
    assert "conftest.py" in noms, f"suite introuvable depuis {Path(__file__).parent}"
    assert len(SUITE) >= 3, f"suite anormalement courte : {sorted(noms)}"


def test_aucun_fichier_de_la_suite_n_importe_le_paquet() -> None:
    """`import dsoxlab` et `from dsoxlab import …` : la règle de base."""
    coupables: list[str] = []
    for fichier in SUITE:
        for noeud in ast.walk(_arbre(fichier)):
            if isinstance(noeud, ast.Import):
                coupables += [
                    f"{fichier.name}:{noeud.lineno} — import {alias.name}"
                    for alias in noeud.names
                    if _vise_le_paquet(alias.name)
                ]
            elif isinstance(noeud, ast.ImportFrom) and _vise_le_paquet(noeud.module):
                coupables.append(f"{fichier.name}:{noeud.lineno} — from {noeud.module}")

    assert not coupables, (
        "Cette suite est une boîte noire : elle parle au programme installé, "
        "jamais au paquet source. Un import de dsoxlab lui ferait tester "
        "autre chose que la roue.\n  " + "\n  ".join(coupables)
    )


def test_aucun_import_dynamique_du_paquet() -> None:
    """`importlib.import_module("dsoxlab")` contourne l'analyse des imports."""
    coupables: list[str] = []
    for fichier in SUITE:
        for noeud in ast.walk(_arbre(fichier)):
            if not isinstance(noeud, ast.Call):
                continue
            appele = noeud.func
            nom = appele.attr if isinstance(appele, ast.Attribute) else (
                appele.id if isinstance(appele, ast.Name) else None
            )
            if nom not in IMPORTEURS or not noeud.args:
                continue
            premier = noeud.args[0]
            if isinstance(premier, ast.Constant) and _vise_le_paquet(
                premier.value if isinstance(premier.value, str) else None
            ):
                coupables.append(f"{fichier.name}:{noeud.lineno} — {nom}({premier.value!r})")

    assert not coupables, (
        "Import dynamique du paquet : même règle, autre porte.\n  "
        + "\n  ".join(coupables)
    )


def test_le_paquet_n_est_pas_charge_dans_ce_processus() -> None:
    """La preuve à l'exécution, celle qu'aucune astuce syntaxique n'esquive.

    Les modules de la suite sont tous importés avant que le premier test ne
    s'exécute : un import en tête de fichier serait donc déjà là.
    """
    charges = sorted(
        module
        for module in sys.modules
        if module == INTERDIT or module.startswith(f"{INTERDIT}.")
    )

    assert not charges, (
        "Le paquet a été chargé dans le processus de test. La suite ne mesure "
        f"plus l'empaquetage mais l'arborescence source : {charges}"
    )
