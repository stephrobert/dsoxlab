"""Afficher une valeur de catalogue sans lui laisser piloter le terminal.

Une valeur du contrat est une **donnée**. Rendue dans une chaîne de balisage
Rich, elle devient une **instruction** : ``title: "[red]"`` colore le tableau,
``[link=…]`` y pose un hyperlien vers où il veut, et un ``\\x1b]0;…\\x07`` glissé
dans un champ renomme la fenêtre du terminal.

Le défaut n'était pas théorique. Mesuré sur un catalogue d'essai avant d'être
corrigé, avec un titre valant ``Titre [red]hostile[/red] et [/] non apparié`` :

.. code-block:: text

    $ dsoxlab list-labs
    MarkupError: closing tag '[/]' at position 28 has nothing to close
    $ dsoxlab show mauvais
    MarkupError: closing tag '[/]' at position 113 has nothing to close

Les deux commandes sortaient en trace Python. Un catalogue tiers pouvait donc
rendre le catalogue entier inaffichable avec un caractère.

Deux protections, à deux niveaux
================================

:func:`texte_affichable` est la protection **exacte** : elle s'applique aux
valeurs du contrat au moment où on les rend, et elle empêche la falsification
du rendu — couleurs, hyperliens, séquences d'échappement.

La console du moteur porte en plus un **filet** (``ConsoleSure`` dans
``reporting/console.py``) qui rend littéralement ce qu'elle ne sait pas
analyser, au lieu de lever. Les deux sont utiles : le filet couvre les points
d'affichage que personne n'a encore pensé à protéger, ce qui est précisément la
catégorie où le prochain défaut se trouvera.
"""

from __future__ import annotations

from rich.markup import escape

from . import _PLAGES_INTERDITES

#: Ce qui remplace un caractère qui n'a rien à faire dans un champ affiché. Un
#: caractère visible plutôt qu'une suppression : une valeur amputée en silence
#: se lit comme une valeur normale, et personne ne va voir le catalogue.
REMPLACEMENT = "·"


def neutraliser(valeur: str) -> str:
    """Remplace ce qui pilote un terminal, et garde le reste intact.

    À employer quand la valeur ne traverse **pas** l'analyseur de balisage —
    dans un ``rich.text.Text``, par exemple, qui rend les crochets littéralement
    mais laisse passer une séquence d'échappement telle quelle.

    On **neutralise** ici au lieu de refuser, à l'inverse de
    :func:`dsoxlab.security.identifiant_sur` : afficher est le service rendu, et
    un titre douteux ne justifie pas qu'une commande de lecture échoue. Un
    identifiant qui **part** vers un tiers, lui, se refuse — une valeur faussée
    en silence y romprait le rattachement d'une preuve à son lab.

    Les retours à la ligne et les tabulations tombent aussi : les champs
    concernés (``title``, ``level``, ``skills``…) tiennent sur une ligne, et un
    ``\\n`` injecté dans une cellule de tableau y fabrique une ligne de plus.
    """
    return "".join(
        REMPLACEMENT
        if any(debut <= ord(c) <= fin for debut, fin, _ in _PLAGES_INTERDITES)
        else c
        for c in valeur
    )


def texte_affichable(valeur: str) -> str:
    """La valeur telle qu'on peut l'interpoler dans une chaîne de balisage Rich.

    :func:`neutraliser`, puis le balisage est **échappé** : il s'affiche tel
    qu'il est écrit plutôt que d'agir. Les crochets restent lisibles, ce qui
    compte — un titre qui parle de ``[sic]`` doit s'afficher entier.
    """
    return escape(neutraliser(valeur))
