"""La page des invariants nomme des tests : ils doivent exister.

`docs/design-principles.md` tire toute sa valeur de sa troisième colonne — le
test qui tient chaque règle. C'est ce qui la sépare d'une liste de bonnes
intentions : elle dit ce qui est **réellement gardé**, et ce qui ne l'est pas.

Or un test se renomme, se fusionne, disparaît. Le jour où la page nomme un
fichier absent, elle affirme une garantie qui n'existe plus — et elle le fait
avec l'autorité d'un document d'architecture. C'est exactement la dérive que
`test_documentation_synchrone.py` traque sur les commandes et les chemins, ici
appliquée aux garde-fous eux-mêmes.

Les deux langues sont contrôlées : une page traduite qui dérive de l'autre est
une page qui dira deux vérités.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

RACINE = Path(__file__).resolve().parent.parent
PAGES = ("docs/design-principles.md", "docs/design-principles.fr.md")

#: `tests/quelque_chose.py` cité dans du code en ligne. On ne lit que le code
#: entre accents graves : la prose peut parler d'un test sans le nommer.
_CITE = re.compile(r"`(tests/[a-z0-9_]+\.py)`")

#: Les autres fichiers du dépôt que la page cite, et qui portent une garantie.
_AUTRES = re.compile(r"`(packer/[a-z0-9_/.-]+)`")


def _citations(page: str, motif: re.Pattern[str]) -> set[str]:
    return set(motif.findall((RACINE / page).read_text(encoding="utf-8")))


@pytest.mark.parametrize("page", PAGES)
def test_chaque_test_nomme_existe(page: str) -> None:
    """Un test cité et absent, c'est une garantie affirmée et disparue."""
    cites = _citations(page, _CITE)
    assert cites, f"{page} ne nomme aucun test : la colonne des garde-fous est vide"

    absents = sorted(nom for nom in cites if not (RACINE / nom).is_file())
    assert absents == [], (
        f"{page} nomme des tests qui n'existent pas : {absents}\n"
        "Renommez-les dans la page, ou retirez la garantie qu'ils portaient."
    )


@pytest.mark.parametrize("page", PAGES)
def test_chaque_fichier_nomme_existe(page: str) -> None:
    """Même règle pour les scripts cités comme tenant une règle."""
    absents = sorted(
        nom for nom in _citations(page, _AUTRES) if not (RACINE / nom).exists()
    )
    assert absents == [], f"{page} nomme des fichiers absents : {absents}"


def test_les_deux_pages_nomment_les_memes_tests() -> None:
    """Une traduction qui dérive dirait deux vérités sur ce qui est gardé."""
    anglais = _citations(PAGES[0], _CITE)
    francais = _citations(PAGES[1], _CITE)

    assert anglais == francais, (
        "les deux pages ne nomment pas les mêmes tests\n"
        f"seulement en anglais : {sorted(anglais - francais)}\n"
        f"seulement en français : {sorted(francais - anglais)}"
    )


def test_la_page_est_referencee_ou_on_la_cherche() -> None:
    """Un document que rien ne pointe n'est pas lu, donc ne tient rien.

    Trois entrées, et chacune correspond à un moment où l'on en a besoin :
    l'index de la documentation, le guide de contribution, et le gabarit de PR
    — celui-ci renvoyant au document plutôt que de recopier la liste, qui
    dériverait.
    """
    for source, attendu in (
        ("docs/README.md", "design-principles.md"),
        ("docs/README.fr.md", "design-principles.fr.md"),
        ("CONTRIBUTING.md", "design-principles.md"),
        ("CONTRIBUTING.fr.md", "design-principles.fr.md"),
        (".github/PULL_REQUEST_TEMPLATE.md", "design-principles.md"),
    ):
        texte = (RACINE / source).read_text(encoding="utf-8")
        assert attendu in texte, f"{source} ne renvoie pas à {attendu}"


def test_aucun_invariant_sans_incident() -> None:
    """La règle d'écriture de la page, tenue sur sa forme.

    Chaque ligne de tableau porte trois colonnes : l'invariant, l'incident qui
    l'a révélé, le test qui le tient. Une ligne à deux colonnes est un principe
    sans son histoire — et un principe sans son histoire se discute.
    """
    for page in PAGES:
        for ligne in (RACINE / page).read_text(encoding="utf-8").splitlines():
            if not ligne.startswith("| ") or ligne.startswith("| ---"):
                continue
            colonnes = [c.strip() for c in ligne.strip("|").split(" | ")]
            if len(colonnes) < 3:
                continue  # les tableaux des promesses n'ont pas cette forme
            invariant, incident, tenu = colonnes[0], colonnes[1], colonnes[2]
            assert incident, f"{page} : « {invariant[:60]} » sans incident"
            assert tenu, f"{page} : « {invariant[:60]} » sans colonne de garde"
