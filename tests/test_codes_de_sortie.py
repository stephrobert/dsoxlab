"""Les codes de sortie sont une interface : ces tests la tiennent.

Un code de sortie n'a ni schéma, ni version, ni message. Il ne peut donc ni se
déprécier en douceur, ni s'expliquer : un script qui lit `7` aujourd'hui doit
lire `7` demain, et un code que personne n'a documenté est un contrat illisible.

Trois invariants, et une raison pour chacun :

- **aucune valeur en double** — un doublon dans un ``IntEnum`` ne lève pas, il
  crée un alias silencieux, et deux causes distinctes se diraient du même code ;
- **chaque code figure dans les deux pages de documentation** — c'est le seul
  contrôle qui attrape un code ajouté au code sans un mot pour l'expliquer ;
- **aucun littéral d'interface aux points d'appel** — les codes au-delà de 4
  désignent des causes précises, sur lesquelles un script agit ; les écrire en
  clair est le chemin par lequel une valeur se dédouble.

Les alias historiques sont vérifiés aussi : ils sont importés ailleurs, et leur
valeur est publiée depuis plusieurs versions.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

from dsoxlab.exit_codes import ExitCode
from dsoxlab.infra.inventory import EXIT_HOTES_INJOIGNABLES
from dsoxlab.interrupt import EXIT_INTERRUPTED
from dsoxlab.locking import EXIT_LOCKED
from dsoxlab.services.doctor import (
    EXIT_DOCTOR_INDETERMINE,
    EXIT_DOCTOR_REQUIS_KO,
)

_RACINE = Path(__file__).resolve().parents[1]
_SOURCES = _RACINE / "src" / "dsoxlab"
_DOCS = (_RACINE / "docs" / "exit-codes.md", _RACINE / "docs" / "exit-codes.fr.md")

#: En deçà, le code est générique (« non » et « impossible ») et s'écrit en clair
#: aux dizaines de points d'appel qui le lèvent. Au-delà, il désigne une cause
#: précise, sur laquelle un script agit : il passe par l'énuméré.
_SEUIL_INTERFACE = 4


def test_aucun_code_n_est_attribue_deux_fois_ici() -> None:
    """Le doublon ne lève pas en Python : il se déguise en alias.

    ``list(ExitCode)`` perd le second membre d'une valeur partagée, là où
    ``__members__`` les garde tous les deux. Comparer les deux est donc le seul
    moyen de voir le doublon.
    """
    uniques = list(ExitCode)
    noms = list(ExitCode.__members__)

    assert len(uniques) == len(noms), (
        "deux noms partagent une valeur : "
        f"{sorted(set(noms) - {membre.name for membre in uniques})}"
    )


@pytest.mark.parametrize("page", _DOCS, ids=lambda p: p.name)
def test_chaque_code_est_documente(page: Path) -> None:
    """Un code absent de la page est un contrat que personne ne peut lire."""
    texte = page.read_text(encoding="utf-8")

    manquants = [
        f"{membre.value} ({membre.name})"
        for membre in ExitCode
        if f"`{membre.value}`" not in texte or membre.name not in texte
    ]

    assert not manquants, f"{page.name} ne documente pas : {manquants}"


def test_les_deux_pages_documentent_la_meme_table() -> None:
    """La parité EN/FR, sur le document le plus mécanique du dépôt.

    Une page qui décrirait un code de plus que l'autre serait pire qu'une page
    incomplète : elle ferait croire que la table dépend de la langue.
    """
    en, fr = (page.read_text(encoding="utf-8") for page in _DOCS)

    for membre in ExitCode:
        assert (membre.name in en) == (membre.name in fr), (
            f"{membre.name} n'est décrit que d'un côté"
        )


def _sorties_litterales(fichier: Path) -> list[tuple[int, int]]:
    """Les ``typer.Exit(<nombre>)`` du fichier, en (ligne, valeur)."""
    arbre = ast.parse(fichier.read_text(encoding="utf-8"), filename=str(fichier))
    trouves: list[tuple[int, int]] = []
    for noeud in ast.walk(arbre):
        if not isinstance(noeud, ast.Call):
            continue
        cible = noeud.func
        nom = (
            cible.attr if isinstance(cible, ast.Attribute)
            else cible.id if isinstance(cible, ast.Name)
            else ""
        )
        if nom not in {"Exit", "SystemExit"}:
            continue
        for argument in noeud.args:
            if isinstance(argument, ast.Constant) and isinstance(argument.value, int):
                trouves.append((noeud.lineno, argument.value))
    return trouves


def test_aucun_code_d_interface_n_est_ecrit_en_clair() -> None:
    """Le garde-fou qui empêche la dispersion de revenir.

    C'est ainsi que le 127 avait fini écrit en clair dans ``_socle.py``, seul de
    son espèce, sans constante ni documentation.
    """
    fautifs: list[str] = []
    for fichier in sorted(_SOURCES.rglob("*.py")):
        for ligne, valeur in _sorties_litterales(fichier):
            if valeur > _SEUIL_INTERFACE:
                relatif = fichier.relative_to(_RACINE)
                fautifs.append(f"{relatif}:{ligne} → Exit({valeur})")

    assert not fautifs, (
        "ces codes désignent une cause précise et doivent passer par ExitCode : "
        + ", ".join(fautifs)
    )


def test_les_alias_historiques_gardent_leur_valeur() -> None:
    """Ces quatre noms sont importés ailleurs, et leurs valeurs sont publiées.

    Les ranger dans un énuméré ne doit rien changer pour un appelant : ni la
    valeur, ni la comparaison à un entier, qu'``IntEnum`` préserve.
    """
    assert EXIT_LOCKED == 7
    assert EXIT_HOTES_INJOIGNABLES == 8
    assert EXIT_DOCTOR_REQUIS_KO == 9
    assert EXIT_DOCTOR_INDETERMINE == 10
    assert EXIT_INTERRUPTED == 130

    # Et ce sont bien les membres de l'énuméré, pas des entiers parallèles.
    assert EXIT_LOCKED is ExitCode.VERROU
    assert EXIT_INTERRUPTED is ExitCode.INTERROMPU
