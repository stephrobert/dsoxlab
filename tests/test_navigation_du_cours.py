"""La barre de navigation du cours propose-t-elle une commande qui marche ?

Défaut signalé en usage réel, sur `ckad-expose-service` : la barre affichait
« → dsoxlab course --next », l'apprenant la tapait, et tombait soit sur « Aucun
lab actif en session », soit, pire, sur la section 1 d'un **autre** lab, celui
que le contexte avait gardé comme actif.

La cause tenait en une ligne : le rendu passait bien `id=` aux clés i18n, mais
aucune des deux chaînes ne portait `{id}`. Le paramètre partait donc à la
poubelle sans que rien ne le signale, et un test qui vérifiait la présence de
la barre voyait une barre parfaitement formée.

D'où ces tests, qui portent sur ce que la barre **propose**, pas sur le fait
qu'elle s'affiche.
"""

from __future__ import annotations

from dsoxlab.i18n import _


class TestLeGesteProposeEstJouable:
    def test_le_suivant_nomme_le_lab(self) -> None:
        geste = _("course_nav_next", id="ckad-expose-service")
        assert "ckad-expose-service" in geste, (
            "sans l'identifiant, la commande agit sur le lab ACTIF, qui n'est "
            "pas forcément celui qu'on est en train de lire"
        )
        assert "--next" in geste

    def test_le_precedent_nomme_le_lab(self) -> None:
        geste = _("course_nav_prev", id="ckad-expose-service")
        assert "ckad-expose-service" in geste
        assert "--prev" in geste


class TestLesDeuxLanguesDisentLaMemeCommande:
    def test_aucune_traduction_ne_perd_l_identifiant(self) -> None:
        """Une clé peut être traduite sans son `{id}` : c'est exactement ce qui
        s'est produit, et rien ne l'avait vu."""
        import dsoxlab.i18n.strings.en as en
        import dsoxlab.i18n.strings.fr as fr

        for cle in ("course_nav_next", "course_nav_prev"):
            for nom, table in (("en", en.STRINGS), ("fr", fr.STRINGS)):
                assert "{id}" in table[cle], f"{nom}:{cle} ne place pas l'identifiant"
