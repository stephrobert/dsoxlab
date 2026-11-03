"""Un refus d'épreuve se dit UNE fois, et aucune coche verte ne le referme.

CE QUE CES TESTS DÉFENDENT, et pourquoi ils n'existaient pas avant. La 0.7.0 a
ajouté une ligne nommant le contrôle bloquant ; la 0.7.1 en a ajouté une seconde
pour corriger un motif faux, sans retirer la première. Les deux versions ont été
mesurées séparément, chacune sur sa fonction, et **jamais sur ce que l'apprenant
voit**. Relevé sur la VM avec la 0.7.2, un refus affichait à la suite :

    ℹ Soumission enregistrée : 80/100 pts (4/5 tests réussis). Corrigez et
      soumettez à nouveau si besoin.
    ✘ Un contrôle bloquant a échoué, donc l'épreuve est refusée quel que soit
      le total : <test>
      Cette exigence n'est compensée par aucune note. Corrigez-la, puis
      soumettez à nouveau.
    ✘ Épreuve refusée : un contrôle bloquant a échoué. Vous obtenez 80 % du
      barème, ce qui franchit le seuil de 75 %, et aucune note ne compense
      cette exigence. Corrigez-la, puis soumettez à nouveau.
    ✔ Tentative sauvegardée. Vous pouvez enchaîner avec dsoxlab run <lab> ou
      libérer l'infra avec dsoxlab destroy.

Le refus dit deux fois, « corrigez puis soumettez à nouveau » dit trois fois, et
une coche verte pour refermer un échec.

Ces tests n'interrogent **pas un rendu** : ils lisent le choix de clé et le
contenu des dictionnaires. Lire une sortie Rich mesurerait la mise en forme, qui
n'est pas le sujet.
"""
from __future__ import annotations

import pytest

from dsoxlab.cli.progression import _cle_de_la_suite
from dsoxlab.i18n.strings import en as EN
from dsoxlab.i18n.strings import fr as FR

LANGUES = (("fr", FR.STRINGS), ("en", EN.STRINGS))


class TestLeDernierMotDeSubmit:
    """Le choix de la dernière ligne, qui est un choix et non une mise en forme."""

    def test_un_refus_ne_se_referme_pas_sur_la_ligne_du_succes(self, monkeypatch):
        monkeypatch.delenv("DSOXLAB_LAB_SESSION", raising=False)
        assert _cle_de_la_suite(refusee=True) == "submit_done_refus"

    def test_une_epreuve_non_refusee_garde_la_ligne_habituelle(self, monkeypatch):
        monkeypatch.delenv("DSOXLAB_LAB_SESSION", raising=False)
        assert _cle_de_la_suite(refusee=False) == "submit_done"

    def test_dans_le_sous_shell_le_tape_exit_passe_avant(self, monkeypatch):
        """Le « tape exit » l'emporte, refus ou pas : il y a un shell à fermer.

        Sans ce cas, on pourrait croire que le refus prend toujours la main, et
        un apprenant resterait dans un sous-shell sans savoir en sortir.
        """
        monkeypatch.setenv("DSOXLAB_LAB_SESSION", "1")
        assert _cle_de_la_suite(refusee=True) == "submit_exit_cta"
        assert _cle_de_la_suite(refusee=False) == "submit_exit_cta"


class TestLesMessagesDeRefus:
    """Le contenu des clés, dans les DEUX langues : une seule corrigée est une dette."""

    @pytest.mark.parametrize(("langue", "table"), LANGUES)
    def test_la_ligne_de_cloture_dun_refus_existe(self, langue, table):
        assert "submit_done_refus" in table, (
            f"la clé manque en {langue} : une épreuve refusée se refermerait "
            "sur la ligne du succès"
        )

    @pytest.mark.parametrize(("langue", "table"), LANGUES)
    def test_aucune_coche_verte_derriere_un_refus(self, langue, table):
        message = table["submit_done_refus"]
        assert "✔" not in message, f"une coche referme un refus en {langue}"
        assert "green" not in message, f"du vert referme un refus en {langue}"

    @pytest.mark.parametrize(("langue", "table"), LANGUES)
    def test_le_refus_nomme_les_controles_bloquants(self, langue, table):
        """Le verdict porte les noms : c'est la fusion des deux anciennes lignes.

        Sans ce test, on pourrait retirer la ligne qui nommait les contrôles
        sans que la ligne restante les reprenne, et l'apprenant lirait un refus
        sans savoir sur quoi.
        """
        assert "{checks}" in table["exam_failed_blocking"], (
            f"le refus ne nomme plus les contrôles en {langue}"
        )

    @pytest.mark.parametrize(("langue", "table"), LANGUES)
    def test_le_refus_ne_se_dit_plus_deux_fois(self, langue, table):
        """La clé de la première des deux lignes n'existe plus.

        C'est le seul garde-fou qui empêche la réapparition du doublon : tant
        que la clé existe, un appel peut revenir.
        """
        assert "exam_blocking_failed" not in table, (
            f"la clé du doublon est revenue en {langue}"
        )

    @pytest.mark.parametrize(("langue", "table"), LANGUES)
    def test_un_refus_sur_exigence_ne_parle_pas_dun_seuil_manque(self, langue, table):
        """L'autre sens, et il tient la correction de la 0.7.1.

        Un refus sur contrôle bloquant arrive avec un pourcentage qui FRANCHIT
        le seuil. Dire « sous le seuil » envoyait l'apprenant chercher des
        points qu'aucun point ne lui rend.
        """
        refus = table["exam_failed_blocking"]
        interdits = ("sous le seuil", "below the") if langue == "fr" else ("below the",)
        for mot in interdits:
            assert mot not in refus, f"« {mot} » devant un seuil franchi, en {langue}"

    @pytest.mark.parametrize(("langue", "table"), LANGUES)
    def test_le_score_insuffisant_parle_toujours_du_seuil(self, langue, table):
        """Le contre-sens, sans quoi vider les deux messages passerait ce test.

        `exam_failed` décrit un total réellement insuffisant : lui, doit parler
        du seuil.
        """
        attendu = "seuil" if langue == "fr" else "mark"
        assert attendu in table["exam_failed"], (
            f"le refus sur score ne parle plus du seuil en {langue}"
        )


class TestLaRelationAuSeuilSeCalcule:
    """Le piège qui a mordu TROIS fois, toujours de la même façon.

    Un message qui **énonce** une comparaison au lieu de la faire. La 0.7.0
    disait « 80 % du barème, sous le seuil de 75 % » devant un seuil franchi ;
    la 0.7.1 l'a corrigé en figeant l'autre sens ; et la première écriture de
    la 0.7.3 écrivait donc « vous obtenez 20 % du barème, ce qui franchit le
    seuil de 75 % », relevé tel quel sur la VM.

    Un refus sur contrôle bloquant arrive dans les DEUX situations : avec un
    total au-dessus du seuil, qui est le cas intéressant, et avec un total en
    dessous, où deux choses manquent.
    """

    @staticmethod
    def _cle_choisie(monkeypatch, pct: int, seuil: int) -> str:
        from dsoxlab.cli import progression

        vues: list[str] = []
        monkeypatch.setattr(progression, "error", vues.append)
        monkeypatch.setattr(progression, "_", lambda cle, **k: cle)
        progression._dire_le_verdict(
            recue=False, bloquee=True, pct=pct, seuil=seuil, blocages="  test_x"
        )
        assert len(vues) == 1, "le refus doit se dire une seule fois"
        return vues[0]

    def test_au_dessus_du_seuil_le_message_dit_quil_est_franchi(self, monkeypatch):
        assert self._cle_choisie(monkeypatch, 80, 75) == "exam_failed_blocking"

    def test_au_seuil_exactement_il_est_franchi(self, monkeypatch):
        """Le seuil est un minimum atteint, pas un minimum dépassé."""
        assert self._cle_choisie(monkeypatch, 75, 75) == "exam_failed_blocking"

    def test_sous_le_seuil_le_message_ne_pretend_pas_quil_est_franchi(self, monkeypatch):
        """Le cas relevé sur la VM : 20 % devant un seuil de 75 %."""
        assert self._cle_choisie(monkeypatch, 20, 75) == "exam_failed_blocking_et_score"

    @pytest.mark.parametrize(("langue", "table"), LANGUES)
    def test_le_message_sous_le_seuil_ne_dit_pas_franchi(self, langue, table):
        message = table["exam_failed_blocking_et_score"]
        interdits = ("franchit",) if langue == "fr" else ("clears",)
        for mot in interdits:
            assert mot not in message, (
                f"« {mot} » dans le message d'un seuil NON franchi, en {langue}"
            )

    @pytest.mark.parametrize(("langue", "table"), LANGUES)
    def test_le_message_sous_le_seuil_nomme_les_deux_manques(self, langue, table):
        """Sans quoi l'apprenant corrige l'exigence et reste recalé sur le total."""
        message = table["exam_failed_blocking_et_score"]
        assert "{checks}" in message, f"les contrôles ne sont pas nommés en {langue}"
        assert "{pct}" in message and "{threshold}" in message, (
            f"le total et le seuil ne sont pas dits en {langue}"
        )


class TestLaConfirmationHorsTerminal:
    """« Aborted » n'est pas un message : deux mots, sans sujet et sans geste."""

    @pytest.mark.parametrize(("langue", "table"), LANGUES)
    def test_le_message_existe_et_nomme_loption(self, langue, table):
        message = table["confirmation_sans_terminal"]
        assert "--yes" in message, (
            f"le message ne nomme pas l'option qui débloque, en {langue}"
        )

    def test_hors_terminal_la_commande_sort_en_2_sans_rien_demander(self, monkeypatch):
        """Elle sort, et elle sort en 2 : un refus d'exécution, pas un succès.

        Le piège que ce test ferme : remplacer `Aborted` par un message tout en
        laissant la commande continuer. Elle effacerait alors le travail de
        l'apprenant sans confirmation, ce qui est l'inverse du but.
        """
        import typer

        from dsoxlab.cli import progression

        appels: list[str] = []
        monkeypatch.setattr(progression.sys.stdin, "isatty", lambda: False)
        monkeypatch.setattr(progression, "error", appels.append)
        monkeypatch.setattr(
            progression.typer, "confirm",
            lambda *a, **k: pytest.fail("une confirmation a été demandée sans terminal"),
        )
        with pytest.raises(typer.Exit) as sortie:
            progression._confirmer("confirm_clean", "un-lab")
        assert sortie.value.exit_code == 2
        assert appels, "le refus est sorti sans un mot"

    def test_dans_un_terminal_la_confirmation_est_bien_demandee(self, monkeypatch):
        """L'autre sens : le garde-fou ne doit pas supprimer la question."""
        from dsoxlab.cli import progression

        demandes: list[tuple] = []
        monkeypatch.setattr(progression.sys.stdin, "isatty", lambda: True)
        monkeypatch.setattr(
            progression.typer, "confirm",
            lambda message, **k: demandes.append((message, k)),
        )
        progression._confirmer("confirm_clean", "un-lab")
        assert len(demandes) == 1
        assert demandes[0][1].get("abort") is True, (
            "sans `abort=True`, un « non » laisserait la commande continuer"
        )
