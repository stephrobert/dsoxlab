"""La documentation ne peut plus mentir sur la CLI.

Tout ce qu'un binaire peut affirmer de lui-même ne doit pas être recopié à la
main : une commande renommée, retirée ou ajoutée laisse sinon derrière elle une
documentation qui décrit un outil qui n'existe plus. Personne ne s'en aperçoit,
parce que rien ne lit la documentation en même temps que le code.

Ce module ferme les deux sens :

1. **Toute commande citée dans la documentation existe** dans la CLI.
2. **Toute commande de la CLI est décrite** dans `fullhelp`, en anglais comme en
   français. C'est la règle que le projet s'était donnée sans pouvoir la tenir :
   « ne jamais laisser le fullhelp décrire une commande qui n'existe plus ».

Il attrape donc aussi bien la commande oubliée que la commande fantôme.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from dsoxlab.cli import app
from dsoxlab.i18n.strings.en import STRINGS as EN
from dsoxlab.i18n.strings.fr import STRINGS as FR

RACINE = Path(__file__).resolve().parent.parent

#: Documents qui s'adressent à un utilisateur ou à un contributeur, et qui
#: peuvent donc citer des commandes. Le CHANGELOG en est exclu : il raconte le
#: passé, où une commande retirée a toute sa place.
DOCUMENTS = [
    "README.md",
    "README.fr.md",
    "CONTRIBUTING.md",
    "CONTRIBUTING.fr.md",
    "RELEASING.md",
]

#: `dsoxlab <mot>` dans un texte. On ignore ce qui suit un tiret : `dsoxlab
#: --version` est une option, pas une commande.
_APPEL = re.compile(r"(?<![\w/.-])dsoxlab[ \t]+(?!-)([a-z][a-z0-9-]*)")

#: Bloc de code clôturé, et code en ligne entre accents graves.
_BLOC = re.compile(r"```.*?```", re.DOTALL)
_EN_LIGNE = re.compile(r"`([^`\n]+)`")


def _appels_de_commande(texte: str) -> set[str]:
    """Les commandes appelées dans un document, et elles seules.

    On ne lit QUE le code : blocs clôturés et accents graves. La prose emploie
    le même mot sans l'appeler (« dsoxlab lui-même », « dsoxlab itself »,
    « dsoxlab tourne »), et une extraction naïve prenait ces mots pour des
    commandes inexistantes. Un contrôle qui crie au loup sur de la grammaire
    finit désactivé, ce qui est pire que son absence.
    """
    fragments = _BLOC.findall(texte)
    fragments += _EN_LIGNE.findall(_BLOC.sub("", texte))
    return {m.group(1) for fragment in fragments for m in _APPEL.finditer(fragment)}


def _commandes_cli() -> set[str]:
    """Les noms de commandes réellement enregistrés sur l'application Typer."""
    noms = {c.name for c in app.registered_commands if c.name}
    for groupe in app.registered_groups:
        if groupe.name:
            noms.add(groupe.name)
    return noms


COMMANDES = _commandes_cli()


def test_la_cli_declare_bien_des_commandes() -> None:
    """Garde-fou : une extraction cassée rendrait tout ce module vert à vide."""
    assert len(COMMANDES) >= 20, f"seulement {len(COMMANDES)} commandes trouvées"
    assert "check" in COMMANDES and "doctor" in COMMANDES


@pytest.mark.parametrize("document", DOCUMENTS)
def test_les_commandes_citees_existent(document: str) -> None:
    """Une commande renommée laisse une documentation qui envoie dans le mur."""
    chemin = RACINE / document
    if not chemin.is_file():
        pytest.skip(f"{document} absent de ce dépôt")

    citees = _appels_de_commande(chemin.read_text(encoding="utf-8"))
    inconnues = sorted(citees - COMMANDES)
    assert not inconnues, (
        f"{document} cite des commandes qui n'existent pas : {inconnues}\n"
        f"Commandes réelles : {sorted(COMMANDES)}"
    )


@pytest.mark.parametrize("langue", ["en", "fr"])
def test_toute_commande_est_decrite_dans_le_fullhelp(langue: str) -> None:
    """L'inverse, et le plus utile : la commande ajoutée sans sa documentation.

    C'est ce contrôle qui aurait attrapé `support` et `demo` si j'avais oublié
    de les décrire, au lieu de le découvrir chez un utilisateur.
    """
    catalogue = EN if langue == "en" else FR
    fullhelp = catalogue["fullhelp_commands"]

    # `instructor` est un groupe : le fullhelp le décrit par sa sous-commande.
    attendues = COMMANDES - {"instructor"}
    manquantes = sorted(cmd for cmd in attendues if cmd not in fullhelp)

    assert not manquantes, (
        f"fullhelp ({langue}) ne décrit pas : {manquantes}\n"
        "Une commande absente du guide n'existe pas pour qui le lit."
    )


def test_le_fullhelp_ne_decrit_aucune_commande_fantome() -> None:
    """L'autre sens : une commande retirée qui survit dans le guide.

    On ne lit que les lignes en `[cyan]…[/cyan]`, qui sont la liste des
    commandes du guide, pour ne pas confondre avec la prose autour.
    """
    for langue, catalogue in (("en", EN), ("fr", FR)):
        citees = set(
            re.findall(r"\[cyan\]([a-z][a-z0-9-]*)", catalogue["fullhelp_commands"])
        )
        fantomes = sorted(citees - COMMANDES)
        assert not fantomes, (
            f"fullhelp ({langue}) décrit des commandes inexistantes : {fantomes}"
        )


def test_le_catalogue_de_demonstration_ne_cite_que_des_commandes_reelles() -> None:
    """Le lab de démonstration ENSEIGNE la boucle : s'il la nomme mal, il
    apprend une erreur, et c'est le tout premier contact avec l'outil."""
    from dsoxlab.templates import demo_catalog

    inconnues: dict[str, list[str]] = {}
    for markdown in sorted(demo_catalog().rglob("*.md")):
        citees = _appels_de_commande(markdown.read_text(encoding="utf-8"))
        manquantes = sorted(citees - COMMANDES)
        if manquantes:
            inconnues[markdown.name] = manquantes

    assert not inconnues, f"commandes inexistantes citées : {inconnues}"
