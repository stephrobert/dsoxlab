"""Le journal parle une seule langue, et c'est l'anglais (#140).

Le journal mélangeait le français et l'anglais. Ce n'est pas un détail
d'esthétique : c'est le fichier que `dsoxlab support` collecte et qu'un
utilisateur colle dans un rapport de bug.

Les appels `logger.*` sont **délibérément exclus** du garde-fou i18n
(`test_i18n_coverage.py`), et cette exclusion tient toujours : un message de
journal n'est pas un texte d'interface, il ne passe pas par `_()`, et le
traduire à l'exécution rendrait deux rapports incomparables selon la locale de
qui les produit. Mais l'exclusion justifiait de ne pas le **traduire**, pas de
le laisser incohérent.

L'anglais l'emporte pour trois raisons, dans l'ordre de poids :

1. un message de journal se cherche **mot pour mot** dans un moteur de
   recherche ;
2. il se compare entre deux machines aux locales différentes ;
3. il est lu par quelqu'un qui **diagnostique**, pas par quelqu'un qui apprend —
   et il voisine déjà avec les sorties de terraform, ansible et virsh, qui sont
   anglaises.

Sans ce test, la règle se redéfera ligne par ligne, ce qui est exactement ce
qui s'est passé pour l'interface avant que son garde-fou n'existe.
"""

from __future__ import annotations

import ast
import re
from pathlib import Path

import dsoxlab

RACINE = Path(dsoxlab.__file__).resolve().parent

_NIVEAUX = {"debug", "info", "warning", "error", "exception", "critical"}

#: Des mots qui n'existent qu'en français, et qu'aucun nom d'outil, d'option ou
#: de chemin ne porte. La liste est volontairement courte : elle doit produire
#: **zéro** faux positif, faute de quoi on apprendrait à l'ignorer. Elle ne
#: prétend pas détecter tout le français — un message qui y échappe passera,
#: et c'est assumé : ce test est un garde-fou, pas un correcteur.
_MOTS_FRANCAIS = frozenset({
    "aucun", "aucune", "avec", "chemin", "commande", "dans", "depuis", "déjà",
    "échec", "échoué", "écarté", "état", "fichier", "ignoré", "ignorée",
    "illisible", "impossible", "introuvable", "lecture", "les", "mais",
    "nest", "pas", "pour", "sans", "sur", "vers", "verrou",
})

_MOT = re.compile(r"[a-zà-ÿ]+", re.IGNORECASE)


def _messages_de_journal() -> list[tuple[str, int, str]]:
    """Chaque littéral passé en premier argument d'un `logger.*`."""
    trouves: list[tuple[str, int, str]] = []
    for chemin in sorted(RACINE.rglob("*.py")):
        arbre = ast.parse(chemin.read_text(encoding="utf-8"))
        for noeud in ast.walk(arbre):
            if not isinstance(noeud, ast.Call):
                continue
            fonction = noeud.func
            if not (isinstance(fonction, ast.Attribute)
                    and fonction.attr in _NIVEAUX):
                continue
            if getattr(fonction.value, "id", "") != "logger" or not noeud.args:
                continue
            premier = noeud.args[0]
            if isinstance(premier, ast.Constant) and isinstance(premier.value, str):
                trouves.append((
                    str(chemin.relative_to(RACINE)), noeud.lineno, premier.value,
                ))
    return trouves


def _mots_francais(message: str) -> set[str]:
    return {m.lower() for m in _MOT.findall(message)} & _MOTS_FRANCAIS


def test_la_lecture_des_sources_est_representative() -> None:
    """Sans ce contrôle, une lecture cassée rendrait le suivant toujours vert.

    C'est le motif que tout ce lot corrige, et il vaut d'abord pour le
    garde-fou lui-même.
    """
    assert len(_messages_de_journal()) >= 40


def test_aucun_message_de_journal_n_est_en_francais() -> None:
    """La règle, tenue par un test plutôt que par la bonne volonté."""
    coupables = [
        f"{fichier}:{ligne}  {message[:60]}  ← {sorted(mots)}"
        for fichier, ligne, message in _messages_de_journal()
        if (mots := _mots_francais(message))
    ]

    assert coupables == [], (
        "ces messages de journal sont en français ; le journal est en anglais, "
        "parce qu'il se cherche mot pour mot et se compare entre machines :\n  "
        + "\n  ".join(coupables)
    )


def test_le_detecteur_mord_sur_un_message_francais() -> None:
    """L'autre bout : un détecteur qui ne détecte rien passerait aussi au vert.

    Il faut donc lui montrer un message qu'il **doit** attraper, sinon le test
    précédent ne prouve que l'absence de bug dans la liste de mots.
    """
    assert _mots_francais("verrou indisponible sur %s : commande ignorée")
    assert _mots_francais("Contexte illisible, ignoré : %s")


def test_le_detecteur_epargne_l_anglais_et_les_noms_techniques() -> None:
    """Un faux positif ferait désactiver le contrôle plutôt que corriger.

    Les noms d'outils, d'options et de chemins ne doivent jamais le déclencher.
    """
    for message in (
        "lock unavailable on %s (%s): the command proceeds without protection",
        "virsh snapshot-create-as %s %s (external)",
        "run: %s (cwd=%s)",
        "terraform output -json failed: %s",
        "DHCP lease added live: %s -> %s (%s)",
    ):
        assert not _mots_francais(message), f"faux positif sur : {message}"
