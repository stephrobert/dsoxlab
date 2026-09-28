"""Une valeur de catalogue s'affiche, elle ne pilote pas le terminal.

Le défaut a été mesuré avant d'être corrigé, sur un catalogue d'essai dont un
lab portait ``title: "Titre [red]hostile[/red] et [/] non apparié"`` :

.. code-block:: text

    $ dsoxlab list-labs
    MarkupError: closing tag '[/]' at position 28 has nothing to close
    $ dsoxlab show casse
    MarkupError: closing tag '[/]' at position 113 has nothing to close

Les deux commandes sortaient en **trace Python**. Un catalogue tiers rendait
donc le catalogue entier inaffichable avec un caractère, et pouvait par ailleurs
colorer ce qu'il voulait, poser un hyperlien vers où il voulait, ou renommer la
fenêtre du terminal avec une séquence ``OSC``.

Deux natures de valeur sont employées ici, et il faut les deux :

- un balisage **invalide** (``[/]`` non apparié) éprouve le filet de
  ``ConsoleSure`` : sans lui, la commande lève ;
- un balisage **valide** (``[bold]…[/bold]``) éprouve l'échappement : le filet
  ne s'active pas, et la balise **agit** au lieu de s'écrire. C'est le seul
  révélateur d'un échappement oublié, et c'est ainsi qu'un oubli de plus a été
  trouvé après le premier correctif — le titre de section du ``meta.yml``,
  affiché par ``progress``.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from typer.testing import CliRunner

from dsoxlab.cli import app
from dsoxlab.security.terminal import REMPLACEMENT, neutraliser, texte_affichable

runner = CliRunner()

#: Un balisage valide : s'il disparaît de la sortie, c'est qu'il a été exécuté.
VALIDE = "[bold]VOLE[/bold]"
#: Un balisage invalide : il faisait sortir la commande en MarkupError.
INVALIDE = "Titre [red]x[/red] et [/] non apparié"


# ── la primitive ─────────────────────────────────────────────────────────────

def test_le_balisage_est_echappe_pas_supprime() -> None:
    """Un titre qui parle de ``[sic]`` doit s'afficher entier."""
    assert texte_affichable("[sic]") == r"\[sic]"


def test_une_sequence_de_terminal_est_neutralisee() -> None:
    """``\\x1b]0;…\\x07`` renomme la fenêtre de qui lit un catalogue."""
    propre = neutraliser("titre\x1b]0;vole\x07")
    assert "\x1b" not in propre
    assert "\x07" not in propre
    assert REMPLACEMENT in propre


def test_une_surcharge_de_direction_tombe() -> None:
    """``lab\\u202egnp.exe`` se lit ``labexe.png`` : c'est fait pour tromper."""
    surcharge = chr(0x202E)  # RIGHT-TO-LEFT OVERRIDE, écrit par son code
    assert surcharge not in neutraliser(f"lab{surcharge}gnp.exe")


def test_une_valeur_ordinaire_reste_lisible() -> None:
    """Un contrôle qui abîme l'usage normal se fait retirer."""
    assert texte_affichable("Gérer le swap (l2) — 30 min") == "Gérer le swap (l2) — 30 min"


# ── le filet : un balisage illisible ne fait pas échouer une lecture ─────────

def test_le_filet_rend_ce_qu_il_ne_sait_pas_lire() -> None:
    """`ConsoleSure` est la ceinture, l'échappement la bretelle.

    Mesuré en retirant le filet : les tests de commandes ci-dessous passent
    quand même, parce que tout ce qu'ils affichent est déjà échappé. Ils ne
    mesurent donc pas le filet — celui-ci se prouve ici, sur un point
    d'affichage volontairement non protégé, qui est exactement la situation du
    prochain défaut : un message que personne n'a pensé à échapper.
    """
    from rich.panel import Panel

    from dsoxlab.reporting.console import ConsoleSure

    console = ConsoleSure()
    with console.capture() as capture:
        console.print(Panel(f"[bold]voulu[/bold] {INVALIDE}"))
    rendu = capture.get()

    assert INVALIDE in rendu.replace("\n", "")
    # Le balisage voulu tombe avec le reste : c'est le prix, et il est explicite.
    assert "[bold]voulu[/bold]" in rendu


def test_le_filet_laisse_agir_un_balisage_valide() -> None:
    """Sans quoi il dégraderait tout l'affichage pour se protéger d'un cas rare."""
    from dsoxlab.reporting.console import ConsoleSure

    console = ConsoleSure()
    with console.capture() as capture:
        console.print("[bold]gras[/bold]")

    assert capture.get().strip() == "gras"



#: Assez large pour que le tableau ne tronque pas la valeur sous test. Rich
#: lit `COLUMNS` à chaque rendu ; sans cela il suppose 80 colonnes, la cellule
#: est coupée à « [bold]V… », et le test échouerait sur la largeur au lieu de
#: mesurer l'échappement.
LARGE = {"COLUMNS": "250"}


def _rendre_hostile(catalogue: Path, champ: str, valeur: str) -> None:
    lab = catalogue / "labs" / "domaine" / "premier" / "lab.yaml"
    lignes = []
    for ligne in lab.read_text(encoding="utf-8").splitlines():
        if ligne.startswith(f"{champ}:"):
            lignes.append(f'{champ}: "{valeur}"')
        else:
            lignes.append(ligne)
    lab.write_text("\n".join(lignes) + "\n", encoding="utf-8")


@pytest.mark.parametrize("commande", [
    ["list-labs"],
    ["show", "premier"],
    ["next"],
    ["progress"],
    ["status", "premier"],
])
def test_un_balisage_invalide_ne_leve_pas(
    catalogue: Path, commande: list[str]
) -> None:
    _rendre_hostile(catalogue, "title", INVALIDE)
    runner.invoke(app, ["use", "domaine"])

    resultat = runner.invoke(app, commande, env=LARGE)

    assert resultat.exit_code == 0, resultat.stdout
    # `exception` porterait la MarkupError : l'exiger absente dit mieux la
    # régression que de chercher un texte dans la sortie.
    assert resultat.exception is None


# ── l'échappement : une balise valide s'écrit, elle n'agit pas ───────────────

@pytest.mark.parametrize("commande", [
    ["list-labs"],
    ["show", "premier"],
    ["next"],
])
def test_un_balisage_valide_ne_s_applique_pas(
    catalogue: Path, commande: list[str]
) -> None:
    _rendre_hostile(catalogue, "title", VALIDE)
    runner.invoke(app, ["use", "domaine"])

    resultat = runner.invoke(app, commande, env=LARGE)

    assert resultat.exit_code == 0, resultat.stdout
    # Rendu tel qu'il est écrit. S'il avait agi, il serait absent de la sortie —
    # remplacé par « VOLE » en gras.
    assert VALIDE in resultat.stdout.replace("\n", "")


def test_le_titre_de_section_du_meta_est_echappe(catalogue: Path) -> None:
    """Il est affiché par `progress`, et il vient du `meta.yml` du catalogue.

    Oublié au premier correctif : les labs étaient protégés, la section non.
    """
    meta = catalogue / "meta.yml"
    meta.write_text(
        meta.read_text(encoding="utf-8").replace(
            "title: Domaine", f'title: "{VALIDE}"'
        ),
        encoding="utf-8",
    )

    resultat = runner.invoke(app, ["progress"], env=LARGE)

    assert resultat.exit_code == 0, resultat.stdout
    assert VALIDE in resultat.stdout.replace("\n", "")


def test_le_guide_ne_devient_pas_un_lien_pose(catalogue: Path) -> None:
    """Plus de ``[link=…]`` : la cible d'un hyperlien n'est pas ce que l'œil lit.

    L'adresse s'affiche en clair, et `dsoxlab guide --open` reste le geste qui
    l'ouvre — demandé, jamais déclenché par une valeur déclarée.
    """
    resultat = runner.invoke(app, ["show", "premier"], env=LARGE)

    assert resultat.exit_code == 0
    assert "link=" not in resultat.stdout
    assert "exemple.test/guide" in resultat.stdout.replace("\n", "")


def test_un_doc_url_refuse_dit_pourquoi(catalogue: Path) -> None:
    """`show` n'échoue pas sur un `doc_url` hostile, et ne le recopie pas.

    Afficher la fiche d'un lab est une lecture : elle doit aboutir même quand un
    champ est inutilisable. Mais la chaîne fautive n'a rien à faire à l'écran.
    """
    _rendre_hostile(catalogue, "doc_url", "javascript:alert(1)")

    resultat = runner.invoke(app, ["show", "premier"])

    assert resultat.exit_code == 0, resultat.stdout
    assert "javascript:" not in resultat.stdout
    assert "rejected" in resultat.stdout
