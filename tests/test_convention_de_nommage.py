"""La porte de contribution ne doit pas se refermer sur un faux positif.

Le hook `trufflehog` du dépôt est réglé sur `--results=verified` : il ne bloque
que sur un secret **vérifié**, ce qui est la bonne exigence. Mais son détecteur
*Lob* reconnaît les clés de test de ce service à leur seul préfixe `test_`, et
une clé Lob de test est vérifiée **sans appel réseau**, par nature.

Conséquence mesurée le 2026-08-24, en soumettant des noms de longueurs
croissantes à la commande exacte du hook :

    longueur | déclenche ?
    ---------+-------------
       39    | non
       40    | OUI     ← `test_` suivi de 35 caractères
       41    | non

Un nom de fonction de test de quarante caractères suffit donc à faire échouer un
commit, avec un message qui parle de clé d'API. Six tests du dépôt portaient déjà
cette forme sans jamais rien déclencher, parce que le hook ne lit que le diff :
ils auraient bloqué le premier contributeur qui aurait touché à leur fichier.

**Pourquoi un test plutôt qu'une exclusion du détecteur.** Exclure Lob aurait
réglé le symptôme en retirant une capacité de détection, pour un service que le
projet n'utilise pas aujourd'hui mais dont rien ne dit qu'il ne l'utilisera
jamais. Renommer coûte un mot, ne retire rien au scan, et ce contrôle-ci fait
que le défaut se dit ici — en une seconde, avec sa raison — plutôt qu'au
`pre-push`, sous les traits d'une fuite de secret.
"""

from __future__ import annotations

import re
from pathlib import Path

RACINE = Path(__file__).resolve().parent.parent

#: Longueur exacte qui fait reconnaître un nom de fonction comme une clé Lob de
#: test. Mesurée, pas déduite : 39 et 41 passent, 40 seul déclenche.
_LONGUEUR_INTERDITE = 40

_DEFINITION = re.compile(r"^\s*def (test_[a-z0-9_]+)\s*\(", re.MULTILINE)

#: Les suites dont les fichiers passent par le hook. `fuzz/` en est, ses
#: harnais étant du code versionné comme le reste.
_SUITES = ("tests", "tests_e2e", "fuzz")


def test_aucun_nom_de_test_ne_ressemble_a_une_cle_lob() -> None:
    """Aucun nom de fonction de test ne doit faire exactement quarante caractères."""
    fautifs: list[str] = []
    for suite in _SUITES:
        racine = RACINE / suite
        if not racine.is_dir():
            continue
        for source in sorted(racine.rglob("*.py")):
            texte = source.read_text(encoding="utf-8")
            for nom in _DEFINITION.findall(texte):
                if len(nom) == _LONGUEUR_INTERDITE:
                    relatif = source.relative_to(RACINE)
                    fautifs.append(f"{relatif}::{nom}")

    assert not fautifs, (
        "Ces noms font exactement "
        f"{_LONGUEUR_INTERDITE} caractères, ce que le détecteur Lob de "
        "trufflehog prend pour une clé de test vérifiée :\n  "
        + "\n  ".join(fautifs)
        + "\n\nAjoute ou retire un mot. Le hook pre-commit refuserait le commit "
        "en parlant d'une fuite de secret, ce qui n'aide personne à comprendre."
    )


def test_le_controle_voit_bien_les_fichiers_de_test() -> None:
    """Garde-fou : une expression cassée rendrait le contrôle vert à vide.

    C'est le même piège que partout ailleurs dans ce dépôt : un contrôle qui ne
    mesure plus rien est pire qu'un contrôle absent, parce qu'il rassure.
    """
    trouves = 0
    for source in sorted((RACINE / "tests").rglob("*.py")):
        trouves += len(_DEFINITION.findall(source.read_text(encoding="utf-8")))
    assert trouves > 300, f"seulement {trouves} fonctions de test vues"
