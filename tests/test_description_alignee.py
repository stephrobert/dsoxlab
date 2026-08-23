"""La description du produit dit la même chose aux quatre endroits (#120).

Elle vit dans `pyproject.toml`, sur la page GitHub, en tête des deux README et
dans `fullhelp`. Rien ne les tenait ensemble, et elles avaient divergé : le
`fullhelp` promettait encore un « conteneur incus ou VM KVM » que le contrat
n'expose plus depuis longtemps.

Ce test ne juge pas la formulation, qui appartient à l'auteur. Il vérifie que
les trois qualités que le produit revendique restent nommées partout : un
environnement **reproductible** (le contrat, pas un script), **exécutable**
(plusieurs runtimes) et **vérifiable** (des tests qui prouvent l'état).

La description GitHub n'est pas dans le dépôt, donc hors de portée d'un test.
"""

from __future__ import annotations

import tomllib
from pathlib import Path

from dsoxlab.i18n.strings.en import STRINGS as EN
from dsoxlab.i18n.strings.fr import STRINGS as FR

RACINE = Path(__file__).resolve().parent.parent

TRIPTYQUE_EN = ("reproducible", "runnable", "verifiable")
TRIPTYQUE_FR = ("reproductibles", "exécutables", "vérifiables")


def test_le_pyproject_annonce_les_trois_qualites() -> None:
    """C'est la phrase que lit PyPI, et souvent la seule qu'on lise."""
    with (RACINE / "pyproject.toml").open("rb") as f:
        description = tomllib.load(f)["project"]["description"]

    for mot in TRIPTYQUE_EN:
        assert mot in description.lower(), f"« {mot} » a disparu de la description"


def test_les_deux_readme_ouvrent_sur_la_meme_idee() -> None:
    for nom, mots in (("README.md", TRIPTYQUE_EN), ("README.fr.md", TRIPTYQUE_FR)):
        # Le premier paragraphe seulement : plus bas, tout est déjà dit autrement.
        tete = (RACINE / nom).read_text(encoding="utf-8")[:2500].lower()
        for mot in mots:
            assert mot in tete, f"{nom} : « {mot} » manque en tête"


def test_le_fullhelp_dit_la_meme_chose_dans_les_deux_langues() -> None:
    """C'est la version que lit un utilisateur qui n'ouvrira jamais le README."""
    for strings, mots in ((EN, TRIPTYQUE_EN), (FR, TRIPTYQUE_FR)):
        concept = strings["fullhelp_concept"].lower()
        for mot in mots:
            assert mot in concept, f"fullhelp_concept : « {mot} » manque"


def test_le_fullhelp_ne_promet_pas_de_runtime_qui_nexiste_pas() -> None:
    """Le contrat n'expose que `shell` et `vm`.

    Incus est un backend de `vm`, choisi par le `meta.yml` du catalogue : le
    présenter comme un runtime à part apprenait une chose fausse du contrat.
    """
    for strings in (EN, FR):
        concept = strings["fullhelp_concept"].lower()
        assert "incus" not in concept
        assert "kvm" not in concept
