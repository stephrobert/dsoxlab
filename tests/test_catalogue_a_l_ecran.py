"""Le tableau du catalogue tient-il dans le terminal qu'on a ?

Le défaut corrigé, mesuré avant de l'être : les huit colonnes de ``list-labs``
exigeaient **160 colonnes** de terminal pour ne rien tronquer. À 80, la largeur
d'un terminal ouvert sans redimensionnement et celle d'un tmux coupé en deux,
six colonnes sur huit tombaient à une lettre (``│ L… │ l… │ a… │``) : le rendu
comptait **104 troncatures** sur un catalogue aux identifiants longs. Le tableau
le plus consulté du parcours était illisible par défaut.

Ces tests interrogent la fonction qui **décide** des colonnes, jamais le rendu :
lire une sortie Rich mesurerait la mise en forme de Rich, pas le comportement du
dépôt. C'est la règle qui tient toute cette suite.

Trois invariants, et une raison pour chacun :

- **l'identifiant, le titre et le score sont toujours là**, même dans un
  terminal très étroit : sans l'identifiant il n'y a rien à taper, sans le
  titre rien à comprendre, sans le score rien à reprendre ;
- **l'ordre d'affichage ne change jamais**, parce que quiconque connaît ce
  tableau cherche le score à droite ;
- **``--long`` passe outre la largeur**, parce qu'une capture d'écran pour un
  document ou un terminal très large n'a pas à subir une heuristique.
"""

from __future__ import annotations

import tempfile
from pathlib import Path

import pytest

from dsoxlab.models.lab import LabDefinition, ValidationConfig
from dsoxlab.models.runtime import RuntimeConfig, RuntimeType
from dsoxlab.reporting.console import (
    _COLONNES_CATALOGUE,
    _ORDRE_AFFICHAGE,
    colonnes_du_catalogue,
    largeurs_du_catalogue,
)


def _lab(lab_id: str, *, niveau: str = "l1", section: str = "linux") -> LabDefinition:
    return LabDefinition(
        id=lab_id,
        title=f"Titre de {lab_id}",
        level=niveau,
        # Un chemin qui n'est jamais lu : seules les largeurs comptent ici.
        path=Path(tempfile.gettempdir()) / lab_id,
        section=section,
        skills=["demo"],
        distros=["any"],
        doc_url="https://example.invalid/guide",
        validation=ValidationConfig(),
        runtime=RuntimeConfig(type=RuntimeType.SHELL, workdir="challenge/work"),
    )


#: Les trois colonnes sans lesquelles le tableau ne sert à rien.
INDISPENSABLES = ("id", "title", "score")


class TestChoixDesColonnes:
    @pytest.mark.parametrize("largeur", [40, 60, 80, 100, 120, 160, 400])
    def test_les_trois_indispensables_sont_toujours_la(self, largeur: int) -> None:
        colonnes = colonnes_du_catalogue(largeur)
        for nom in INDISPENSABLES:
            assert nom in colonnes, f"{nom} manque à {largeur} colonnes"

    def test_un_terminal_de_80_colonnes_garde_lessentiel(self) -> None:
        """La largeur par défaut d'un terminal, et celle d'un tmux divisé."""
        colonnes = colonnes_du_catalogue(80)
        assert set(colonnes) >= set(INDISPENSABLES)
        assert len(colonnes) <= 5

    def test_un_terminal_large_recoit_tout(self) -> None:
        assert len(colonnes_du_catalogue(200)) == len(_COLONNES_CATALOGUE)

    def test_le_nombre_de_colonnes_croit_avec_la_largeur(self) -> None:
        """Monotonie : élargir son terminal n'a jamais fait perdre une colonne."""
        comptes = [len(colonnes_du_catalogue(w)) for w in range(60, 200, 5)]
        assert comptes == sorted(comptes)

    def test_lordre_daffichage_est_toujours_respecte(self) -> None:
        for largeur in (80, 100, 120, 160):
            colonnes = colonnes_du_catalogue(largeur)
            rangs = [_ORDRE_AFFICHAGE.index(nom) for nom in colonnes]
            assert rangs == sorted(rangs), f"ordre cassé à {largeur}"

    def test_long_passe_outre_la_largeur(self) -> None:
        assert colonnes_du_catalogue(40, tout=True) == _ORDRE_AFFICHAGE

    def test_les_deux_jeux_de_colonnes_decrivent_les_memes_colonnes(self) -> None:
        """Priorité et affichage sont deux ordres du même ensemble.

        Sans ce test, ajouter une colonne à l'un et pas à l'autre la ferait
        disparaître du rendu, ou lever un KeyError selon le sens de l'oubli.
        """
        assert set(_COLONNES_CATALOGUE) == set(_ORDRE_AFFICHAGE)
        assert len(_COLONNES_CATALOGUE) == len(_ORDRE_AFFICHAGE)

    def test_chaque_colonne_a_ses_reglages_et_sa_cle_de_traduction(self) -> None:
        """Une colonne sans réglage lèverait au rendu, pas au test."""
        from dsoxlab.i18n.strings import en, fr
        from dsoxlab.reporting.console import _REGLAGES_COLONNES

        for nom in _COLONNES_CATALOGUE:
            assert nom in _REGLAGES_COLONNES, f"{nom} n'a pas de réglage de colonne"
            assert f"col_{nom}" in fr.STRINGS, f"col_{nom} manque en français"
            assert f"col_{nom}" in en.STRINGS, f"col_{nom} manque en anglais"


class TestLeNiveauEstUnRepere:
    """Le retour qui a corrigé la première version : « on ne voit plus L1/L2 ».

    Les largeurs étaient ESTIMÉES, et le niveau à 12 colonnes. Il vaut `l1` à
    `l4` sur les catalogues linux et ansible, soit deux caractères, et il y
    situe un lab dans la progression. Estimé large, il tombait de l'affichage
    à 80 colonnes ; mesuré, il coûte 9 colonnes et y tient.
    """

    def _catalogue_a_niveaux(self) -> list[LabDefinition]:
        return [
            _lab("l1-first-terminal", niveau="l1"),
            _lab("l1-navigate-filesystem", niveau="l1"),
            _lab("l2-file-permissions", niveau="l2"),
            _lab("l3-selinux-contexts", niveau="l3"),
        ]

    def test_le_niveau_est_la_a_80_colonnes_quand_il_varie(self) -> None:
        assert "level" in colonnes_du_catalogue(80, self._catalogue_a_niveaux())

    def test_le_niveau_resiste_a_des_identifiants_tres_longs(self) -> None:
        """Le cas `ansible-training`, dont les identifiants font 36 caractères."""
        labs = [
            _lab("decouvrir-declaratif-vs-imperatif-et-plus", niveau="l1"),
            _lab("collections-creer-une-collection-complete", niveau="l2"),
        ]
        assert "level" in colonnes_du_catalogue(80, labs)

    def test_la_largeur_du_niveau_est_mesuree_et_non_estimee(self) -> None:
        courts = largeurs_du_catalogue(self._catalogue_a_niveaux())
        longs = largeurs_du_catalogue([_lab("x", niveau="automatisation")])
        assert courts["level"] < longs["level"]

    def test_un_niveau_identique_partout_nest_pas_reserve(self) -> None:
        """Un niveau identique partout ne distingue aucun lab : il passe après.

        C'est le cas de `python-dsoxlab-training`, dont les sept labs sont tous
        « automatisation », et celui d'une section filtrée par `use`, où le
        bandeau de contexte annonce déjà le niveau. La colonne n'est pas
        retirée pour autant : si la place existe, autant la montrer.
        """
        from dsoxlab.reporting.console import _colonne_constante, _colonnes_reservees

        constants = [_lab(f"a-{i}", niveau="automatisation") for i in range(4)]
        varies = [_lab(f"b-{i}", niveau=f"l{i + 1}") for i in range(4)]

        assert _colonne_constante(constants, "level")
        assert not _colonne_constante(varies, "level")
        assert "level" not in _colonnes_reservees(constants)
        assert "level" in _colonnes_reservees(varies)

    def test_un_niveau_constant_tombe_avant_un_niveau_qui_varie(self) -> None:
        """À largeur égale et serrée, c'est la colonne qui informe qui reste."""
        constants = [
            _lab(f"catalogue-au-nom-interminable-{i}", niveau="automatisation")
            for i in range(4)
        ]
        varies = [
            _lab(f"catalogue-au-nom-interminable-{i}", niveau=f"l{i + 1}")
            for i in range(4)
        ]
        etroit = 68
        assert "level" in colonnes_du_catalogue(etroit, varies)
        assert "level" not in colonnes_du_catalogue(etroit, constants)

    def test_lidentifiant_nest_jamais_rogne(self) -> None:
        """Un identifiant tronqué ne se tape pas et ne se copie pas.

        Une version intermédiaire le plafonnait à 28 colonnes, et il
        s'affichait « decouvrir-declaratif-vs… » sur ansible-training. La
        largeur réservée à l'identifiant doit donc toujours couvrir le plus
        long d'entre eux.
        """
        long_id = "decouvrir-declaratif-vs-imperatif-et-plus-encore"
        largeurs = largeurs_du_catalogue([_lab(long_id), _lab("court")])
        assert largeurs["id"] >= len(long_id)
