"""Les commandes que l'interface propose sont-elles jouables ?

Défaut signalé en usage réel : la barre de navigation du cours affichait
« → dsoxlab course --next », l'apprenant la tapait, et tombait sur un autre
lab. La commande existait, l'option aussi : c'est l'argument manquant qui la
rendait fausse. Mais en cherchant la famille du défaut, il est apparu que
**rien** ne vérifiait les commandes écrites dans les chaînes traduites.

Or elles y sont par dizaines, et ce sont elles que l'utilisateur recopie. Une
commande renommée, une option retirée, une faute de frappe : le message
continue de s'afficher, parfaitement rendu, et envoie dans le mur.

Ce contrôle les extrait des deux tables de traduction et les confronte à
l'objet Click, pas à une liste tenue à la main. On interroge le modèle, jamais
un rendu : une liste écrite à côté du code diverge du code.
"""

from __future__ import annotations

import re

import typer
from typer.core import TyperGroup

import dsoxlab.i18n.strings.en as en
import dsoxlab.i18n.strings.fr as fr
from dsoxlab.cli import app

# `click` n'est plus importable : typer 0.27 l'embarque au lieu d'en dépendre.
# On passe donc par les types que typer réexporte, et par `make_context` pour
# le contexte dont `get_command` a besoin.

#: Une commande se reconnaît à son **balisage** : l'interface la met toujours
#: en évidence, `[bold]dsoxlab check[/bold]`. Chercher le mot « dsoxlab » dans
#: le texte brut attrapait au contraire des phrases entières (« dsoxlab pilote
#: tout », « dsoxlab lit »), soit trente signalements dont aucun n'était vrai.
#: Un contrôle qui crie à tort s'apprend à ignorer.
_SEGMENT_BALISE = re.compile(
    r"\[(?:bold|green|cyan|yellow|dim|red)[^\]]*\](.*?)\[/", re.DOTALL
)
#: `dsoxlab <mot> [<mot>] [--options]`, ancré au début du segment balisé.
_COMMANDE = re.compile(
    r"^dsoxlab((?:\s+[a-z][a-z0-9-]*)+)((?:\s+--?[a-z][a-z0-9-]*)*)"
)


def _arbre() -> TyperGroup:
    commande = typer.main.get_command(app)
    assert isinstance(commande, TyperGroup)
    return commande


def _resoudre(groupe: TyperGroup, mots: list[str]) -> tuple[object | None, list[str]]:
    """Descend dans les sous-commandes tant que le mot en est une."""
    courant: object = groupe
    consommes: list[str] = []
    for mot in mots:
        sous = getattr(courant, "commands", None)
        if not isinstance(sous, dict) or mot not in sous:
            break
        courant = sous[mot]
        consommes.append(mot)
    return (courant if consommes else None), consommes


def _options(commande: object) -> set[str]:
    noms: set[str] = set()
    for parametre in getattr(commande, "params", []):
        noms.update(parametre.opts)
        noms.update(parametre.secondary_opts)
    return noms


def _gestes() -> list[tuple[str, str, str]]:
    """Chaque commande citée dans une chaîne : (langue, clé, commande)."""
    trouves: list[tuple[str, str, str]] = []
    for langue, table in (("en", en.STRINGS), ("fr", fr.STRINGS)):
        for cle, texte in table.items():
            if not isinstance(texte, str) or "dsoxlab" not in texte:
                continue
            for segment in _SEGMENT_BALISE.findall(texte):
                trouve = _COMMANDE.match(segment.strip())
                if trouve is not None:
                    trouves.append(
                        (langue, cle, (trouve.group(1) + trouve.group(2)).strip())
                    )
    return trouves


def test_il_y_a_bien_des_commandes_a_verifier() -> None:
    """Le contre-test du contrôle : une regex qui ne capture rien passerait
    tous les autres tests au vert sans rien mesurer."""
    assert len(_gestes()) > 40


def test_toute_commande_citee_existe() -> None:
    groupe = _arbre()
    fautes = [
        f"[{langue}] « {cle} » cite « dsoxlab {geste} », "
        f"dont « {geste.split()[0]} » n'est pas une commande"
        for langue, cle, geste in _gestes()
        if _resoudre(groupe, [m for m in geste.split() if not m.startswith("-")])[0] is None
    ]
    assert not fautes, (
        "Une commande citée qui n'existe pas s'affiche parfaitement et envoie "
        "dans le mur :\n  " + "\n  ".join(fautes)
    )


def test_toute_option_citee_est_acceptee() -> None:
    groupe = _arbre()
    fautes: list[str] = []
    for langue, cle, geste in _gestes():
        mots = geste.split()
        commande, consommes = _resoudre(groupe, [m for m in mots if not m.startswith("-")])
        if commande is None:
            continue  # l'existence est le sujet du test précédent
        acceptees = _options(commande)
        for option in (m for m in mots if m.startswith("-")):
            if option not in acceptees:
                fautes.append(
                    f"[{langue}] « {cle} » cite « dsoxlab {' '.join(consommes)} "
                    f"{option} », que cette commande n'accepte pas"
                )
    assert not fautes, (
        "Une option citée qui n'existe plus fait échouer la commande que "
        "l'utilisateur vient de recopier :\n  " + "\n  ".join(fautes)
    )
