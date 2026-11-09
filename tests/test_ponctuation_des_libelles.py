"""Aucun libellé affiché ne porte de tiret long, ni en français ni en anglais.

Ce que ce test défend, et pourquoi #333 n'a pas suffi
----------------------------------------------------

#333 a retiré le tiret cadratin des chaînes de `fr.py`, avec pour critère
« aucune chaîne française affichée ne contient de `—` ». Trois trous sont
restés, et chacun montre pourquoi un critère énoncé sans garde-fou se périme :

1. les libellés **composés dans le code**, hors des tables i18n : le titre du
   panneau de `status`, la règle de `challenge`, la fiche de `show`, l'en-tête
   d'une section de cours, le récapitulatif d'une tâche ansible en échec. Ils
   s'affichent dans les deux langues, et aucune relecture de `fr.py` ne les
   voit (issue #353) ;
2. `en.py`, que le critère excluait par sa formulation même, alors que les
   sorties anglaises se recopient tout autant ;
3. `fr.py` lui-même, où le remplacement avait laissé des « espace virgule »
   (« tous les autres contrôles , et de ») et un tiret demi-cadratin dans une
   plage numérique.

Le tiret long n'est pas un détail de goût ici : la formation DSOXLab du site
recopie ces sorties mot pour mot, sa charte interdit le caractère, et son
contrôle de relecture refuse une page qui en porte. Une sortie qu'on ne peut pas
citer oblige à la paraphraser, et une leçon qui paraphrase une sortie finit par
la décrire faux.

Comment il mesure
-----------------

Par l'arbre syntaxique, et non par `grep` : seules les chaînes **utilisées comme
valeurs** comptent. Une chaîne posée en instruction (docstring de module, de
classe, de fonction ou d'attribut) n'atteint jamais l'écran, et ce dépôt les
écrit en français soigné, tirets compris. Les commentaires ne sont pas des
chaînes : l'AST ne les voit pas, ce qui est exactement voulu.

Ce test ne lit donc aucun rendu. Il regarde ce que le code peut écrire, pas ce
qu'un terminal en a fait.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

#: Les trois tirets longs qu'un clavier ou un correcteur automatique produit.
#: Cadratin, barre horizontale, demi-cadratin. Le tiret ordinaire `-` reste
#: autorisé partout : c'est lui qui remplace les trois.
TIRETS_LONGS = ("—", "―", "–")

RACINE = Path(__file__).resolve().parent.parent / "src" / "dsoxlab"


def _chaines_de_valeur(fichier: Path) -> list[tuple[int, str]]:
    """Les littéraux de chaîne du module, docstrings exclues, avec leur ligne."""
    arbre = ast.parse(fichier.read_text(encoding="utf-8"))
    posees_en_instruction = {
        id(noeud.value)
        for noeud in ast.walk(arbre)
        if isinstance(noeud, ast.Expr)
        and isinstance(noeud.value, ast.Constant)
        and isinstance(noeud.value.value, str)
    }
    return [
        (noeud.lineno, noeud.value)
        for noeud in ast.walk(arbre)
        if isinstance(noeud, ast.Constant)
        and isinstance(noeud.value, str)
        and id(noeud) not in posees_en_instruction
    ]


MODULES = sorted(RACINE.rglob("*.py"))


@pytest.mark.parametrize(
    "fichier", MODULES, ids=[str(f.relative_to(RACINE)) for f in MODULES]
)
def test_aucun_libelle_ne_porte_de_tiret_long(fichier: Path) -> None:
    fautifs = [
        f"{fichier.relative_to(RACINE)}:{ligne}: {texte[:70]!r}"
        for ligne, texte in _chaines_de_valeur(fichier)
        if any(tiret in texte for tiret in TIRETS_LONGS)
    ]
    assert not fautifs, (
        "tiret long dans un libellé : remplacer par deux-points, une virgule, "
        "des parenthèses, un point médian ou un tiret ordinaire\n"
        + "\n".join(fautifs)
    )


def test_la_mesure_voit_bien_un_tiret_qu_on_lui_donne(tmp_path: Path) -> None:
    """Le contrôle sait-il refuser ? Sans ce témoin, il ne mesurerait rien.

    Deux cas opposés dans un seul fichier : un libellé fautif, qui doit être
    relevé, et une docstring qui en porte un, qui ne doit pas l'être. Un
    contrôle qui attraperait les docstrings serait rouge en permanence, donc
    désactivé le jour même.
    """
    temoin = tmp_path / "temoin.py"
    temoin.write_text(
        '"""Une docstring — avec son tiret, qui n\'atteint aucun écran."""\n'
        'LIBELLE = "État du lab — {id}"\n'
        'PROPRE = "État du lab : {id}"\n',
        encoding="utf-8",
    )

    trouves = [
        texte for _, texte in _chaines_de_valeur(temoin)
        if any(tiret in texte for tiret in TIRETS_LONGS)
    ]

    assert trouves == ["État du lab — {id}"], (
        "la mesure rate le libellé fautif, ou relève la docstring"
    )
