"""Un paramètre passé à `_()` arrive-t-il bien dans le texte affiché ?

Défaut constaté en usage réel sur la barre de navigation du cours : le rendu
appelait `_("course_nav_next", id=lab.id)`, et aucune des deux chaînes ne
portait `{id}`. L'identifiant partait donc à la poubelle sans un mot, la barre
proposait « dsoxlab course --next », et l'apprenant qui tapait cette commande
tombait sur un autre lab, celui que le contexte gardait pour actif.

Rien ne pouvait le voir : la chaîne était bien formée, la traduction présente
dans les deux langues, et un test qui vérifiait l'affichage de la barre voyait
une barre parfaitement rendue. C'est le genre de défaut qu'on ne trouve qu'en
se servant de l'outil, ou par ce contrôle.

Il porte sur les deux sens :

- un paramètre passé que la chaîne ne place pas, qui est le cas ci-dessus ;
- une chaîne qui place un trou qu'aucun appelant ne remplit, qui lève un
  `KeyError` au moment de s'afficher.

Et sur les deux langues, parce qu'une traduction peut perdre un `{trou}` que
l'original avait.
"""

from __future__ import annotations

import ast
import pathlib
import re

import dsoxlab.i18n.strings.en as en
import dsoxlab.i18n.strings.fr as fr

SRC = pathlib.Path(__file__).resolve().parent.parent / "src" / "dsoxlab"
TROU = re.compile(r"\{(\w+)[^}]*\}")

#: Ces appels construisent la clé ou les paramètres à l'exécution : on ne sait
#: pas, en lisant le source, ce qui sera passé. Les exclure est honnête ; les
#: compter produirait de faux positifs qu'on apprendrait à ignorer.
def _cle_litterale(appel: ast.Call) -> str | None:
    if not appel.args:
        return None
    premier = appel.args[0]
    if isinstance(premier, ast.Constant) and isinstance(premier.value, str):
        return premier.value
    return None


def _appels_traduits() -> list[tuple[pathlib.Path, int, str, set[str]]]:
    """Chaque `_("cle", a=..., b=...)` du paquet, avec ses noms de paramètres."""
    trouves: list[tuple[pathlib.Path, int, str, set[str]]] = []
    for fichier in sorted(SRC.rglob("*.py")):
        if "i18n/strings" in fichier.as_posix():
            continue
        arbre = ast.parse(fichier.read_text(encoding="utf-8"))
        for noeud in ast.walk(arbre):
            if not isinstance(noeud, ast.Call):
                continue
            cible = noeud.func
            nom = cible.attr if isinstance(cible, ast.Attribute) else getattr(cible, "id", "")
            if nom != "_":
                continue
            cle = _cle_litterale(noeud)
            if cle is None:
                continue
            # `**params` : le détail n'est pas lisible au source.
            if any(kw.arg is None for kw in noeud.keywords):
                continue
            trouves.append((
                fichier, noeud.lineno, cle, {kw.arg for kw in noeud.keywords if kw.arg},
            ))
    return trouves


def test_tout_parametre_passe_est_place_dans_les_deux_langues() -> None:
    """Le défaut de `course_nav_next`, généralisé à tout le paquet."""
    fautes: list[str] = []
    for fichier, ligne, cle, params in _appels_traduits():
        for langue, table in (("en", en.STRINGS), ("fr", fr.STRINGS)):
            texte = table.get(cle)
            if texte is None:
                continue  # l'absence de clé est le sujet d'un autre contrôle
            trous = set(TROU.findall(texte))
            oublies = params - trous
            if oublies:
                fautes.append(
                    f"{fichier.relative_to(SRC.parent.parent)}:{ligne} "
                    f"passe {sorted(oublies)} à « {cle} », "
                    f"que la chaîne {langue} ne place pas"
                )
    assert not fautes, (
        "Un paramètre qu'aucune chaîne ne place disparaît sans un mot, et le "
        "message affiché est faux sans en avoir l'air :\n  " + "\n  ".join(fautes)
    )


def test_les_deux_langues_placent_les_memes_trous() -> None:
    """Une traduction qui perd un `{trou}` rend un message incomplet dans une
    langue seulement, ce qu'une relecture monolingue ne voit jamais."""
    fautes = [
        f"« {cle} » : en={sorted(TROU.findall(texte))} "
        f"fr={sorted(TROU.findall(fr.STRINGS[cle]))}"
        for cle, texte in en.STRINGS.items()
        if cle in fr.STRINGS
        and set(TROU.findall(texte)) != set(TROU.findall(fr.STRINGS[cle]))
    ]
    assert not fautes, "Trous différents entre les deux langues :\n  " + "\n  ".join(fautes)
