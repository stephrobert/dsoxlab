"""Les événements d'ansible et de terraform, traduits en avancement.

Ces tests n'existaient pas, et ils ne pouvaient pas exister : la lecture des
événements vivait dans une fermeture, au milieu d'une barre Rich, dans un
``dict`` d'état capturé. Mesuré le 2026-10-16 avant l'extraction :
``_run_terraform_with_progress`` affichait une complexité cognitive de 77 pour
une cyclomatique de 4, une profondeur d'imbrication de 8, et ``cli/_barres.py``
une couverture de **19 %**, la plus basse du dépôt.

On ne teste pas une fermeture sans monter un terminal. Maintenant qu'un suivi
est un objet, il suffit de lui donner une liste.

Les séquences d'événements ci-dessous suivent les formats réels :
``ansible-runner`` pour les playbooks, ``terraform -json`` pour les plans.
"""

from __future__ import annotations

from dsoxlab.interrupt import EVENT_INTERRUPT
from dsoxlab.reporting.evenements import (
    AVIS,
    CHANGE,
    DETAIL,
    ECHEC,
    IGNORE,
    OK,
    SuiviAnsible,
    SuiviTerraform,
    SuiviTerraformInit,
    nom_court,
)

#: L'opération de retrait, nommée ici une seule fois : l'écrire en clair dans
#: vingt tests ferait du bruit, et le mot est celui du contrat de `SuiviTerraform`.
RETRAIT = "destroy"


def _tache(nom: str) -> dict[str, object]:
    return {"event": "playbook_on_task_start", "event_data": {"name": nom}}


def _resultat(
    type_: str, hote: str = "web1.lab", tache: str = "Installer", **res: object
) -> dict[str, object]:
    return {"event": type_, "event_data": {"host": hote, "task": tache, "res": res}}


def _planifie(action: str) -> dict[str, object]:
    return {"type": "planned_change", "change": {"action": action}}


def _etape(type_: str, adresse: str, secondes: float = 0) -> dict[str, object]:
    return {
        "type": type_,
        "hook": {"resource": {"addr": adresse}, "elapsed_seconds": secondes},
    }


class TestSuiviAnsible:
    def test_une_tache_qui_passe_avance_le_compteur(self) -> None:
        suivi = SuiviAnsible(playbook="setup.yaml")
        suivi(_tache("Installer nginx"))
        avancement = suivi(_resultat("runner_on_ok"))

        assert avancement is not None
        assert avancement.fait == 1
        assert avancement.lignes[0].marque == OK

    def test_une_tache_qui_change_se_distingue_dune_tache_sans_effet(self) -> None:
        """La distinction qu'Ansible fait, et qui dit si le playbook a agi."""
        suivi = SuiviAnsible(playbook="setup.yaml")
        sans_effet = suivi(_resultat("runner_on_ok", changed=False))
        avec_effet = suivi(_resultat("runner_on_ok", changed=True))

        assert sans_effet is not None and sans_effet.lignes[0].marque == OK
        assert avec_effet is not None and avec_effet.lignes[0].marque == CHANGE

    def test_un_echec_navance_pas_le_compteur(self) -> None:
        """Le fond du sujet : une tâche en échec n'est pas une tâche passée.

        La faire avancer donnait une barre qui atteignait cent pour cent sur un
        playbook qui avait échoué.
        """
        suivi = SuiviAnsible(playbook="setup.yaml")
        suivi(_resultat("runner_on_ok"))
        avant = suivi.faits
        avancement = suivi(_resultat("runner_on_failed", msg="pas de paquet"))

        assert suivi.faits == avant
        assert avancement is not None
        assert avancement.fait is None
        assert [ligne.marque for ligne in avancement.lignes] == [ECHEC, DETAIL]
        assert "pas de paquet" in avancement.lignes[1].texte

    def test_un_echec_sans_message_ne_rend_quune_ligne(self) -> None:
        suivi = SuiviAnsible(playbook="setup.yaml")
        avancement = suivi(_resultat("runner_on_failed"))

        assert avancement is not None
        assert len(avancement.lignes) == 1

    def test_une_tache_ignoree_avance_le_compteur_sans_etre_un_echec(self) -> None:
        suivi = SuiviAnsible(playbook="setup.yaml")
        avancement = suivi(_resultat("runner_on_skipped"))

        assert avancement is not None
        assert avancement.fait == 1
        assert avancement.lignes[0].marque == IGNORE

    def test_un_hote_injoignable_est_dit_avec_sa_cause(self) -> None:
        suivi = SuiviAnsible(playbook="setup.yaml")
        avancement = suivi(
            _resultat("runner_on_unreachable", hote="db1.lab", msg="timeout ssh")
        )

        assert avancement is not None
        assert "db1.lab" in avancement.lignes[0].texte
        assert "timeout ssh" in avancement.lignes[0].texte

    def test_le_nom_de_la_tache_courante_sert_de_repli(self) -> None:
        """Certains événements ne portent pas le nom de la tâche."""
        suivi = SuiviAnsible(playbook="setup.yaml")
        suivi(_tache("Poser la clé"))
        avancement = suivi({"event": "runner_on_ok", "event_data": {"host": "web1"}})

        assert avancement is not None
        assert "Poser la clé" in avancement.lignes[0].texte

    def test_un_evenement_inconnu_ne_change_rien_du_tout(self) -> None:
        """ansible-runner en émet des dizaines : les ignorer est le comportement."""
        assert SuiviAnsible(playbook="x")({"event": "verbose"}) is None

    def test_un_evenement_sans_donnees_compte_quand_meme(self) -> None:
        """Le flux vient d'ansible-runner : il n'est jamais garanti complet.

        Un `runner_on_ok` sans `event_data` dit tout de même qu'une tâche est
        passée : le compteur avance, et l'hôte inconnu s'affiche « ? ». Lever
        ici ferait échouer un playbook pour un défaut d'affichage.
        """
        avancement = SuiviAnsible(playbook="x")({"event": "runner_on_ok"})

        assert avancement is not None
        assert avancement.fait == 1

    def test_linterruption_est_dite_plus_fermement_la_seconde_fois(self) -> None:
        suivi = SuiviAnsible(playbook="x")
        premier = suivi({"event": EVENT_INTERRUPT, "count": 1})
        second = suivi({"event": EVENT_INTERRUPT, "count": 2})

        assert premier is not None and second is not None
        assert premier.lignes[0].marque == AVIS
        assert premier.lignes[0].texte != second.lignes[0].texte


class TestSuiviTerraform:
    def test_seule_laction_attendue_est_comptee(self) -> None:
        """Un plan qui remplace une ressource annonce deux actions pour elle.

        Les compter toutes les deux donnait un total faux, et une barre qui
        n'atteignait jamais cent pour cent.
        """
        suivi = SuiviTerraform(operation="provision")
        suivi(_planifie("create"))
        suivi(_planifie("delete"))
        suivi(_planifie("create"))

        assert suivi.total == 2

    def test_un_retrait_compte_les_suppressions(self) -> None:
        suivi = SuiviTerraform(operation=RETRAIT)
        suivi(_planifie("delete"))
        suivi(_planifie("create"))

        assert suivi.total == 1

    def test_une_ressource_terminee_avance_le_compteur(self) -> None:
        suivi = SuiviTerraform(operation="provision")
        suivi(_planifie("create"))
        suivi(_etape("apply_start", "libvirt_domain.web1"))
        avancement = suivi(_etape("apply_complete", "libvirt_domain.web1", 12))

        assert avancement is not None
        assert avancement.fait == 1
        assert avancement.lignes[0].marque == OK
        assert "web1" in avancement.lignes[0].texte

    def test_la_description_nomme_ce_qui_prend_du_temps(self) -> None:
        """Une barre figée sans explication fait croire à un blocage."""
        suivi = SuiviTerraform(operation="provision")
        suivi(_etape("apply_start", "libvirt_domain.web1"))
        suivi(_etape("apply_start", "libvirt_domain.db1"))
        suivi(_etape("apply_progress", "libvirt_domain.db1", 90))

        description = suivi.description()
        assert "db1" in description
        assert description.index("db1") < description.index("web1"), "la plus lente"

    def test_la_description_borne_ce_quelle_liste(self) -> None:
        """Douze adresses dans une barre de progression ne se lisent plus."""
        suivi = SuiviTerraform(operation="provision")
        for i in range(5):
            suivi(_etape("apply_start", f"libvirt_domain.hote{i}"))

        description = suivi.description(combien=2)
        assert description.count("hote") == 2
        assert "+3" in description

    def test_une_ressource_terminee_quitte_la_description(self) -> None:
        suivi = SuiviTerraform(operation="provision")
        suivi(_etape("apply_start", "libvirt_domain.web1"))
        suivi(_etape("apply_complete", "libvirt_domain.web1", 3))

        assert "web1" not in suivi.description()

    def test_une_ressource_en_echec_navance_pas_le_compteur(self) -> None:
        suivi = SuiviTerraform(operation="provision")
        suivi(_etape("apply_start", "libvirt_domain.web1"))
        avancement = suivi(_etape("apply_errored", "libvirt_domain.web1"))

        assert suivi.faits == 0
        assert avancement is not None
        assert avancement.lignes[0].marque == ECHEC

    def test_un_diagnostic_derreur_est_repris(self) -> None:
        suivi = SuiviTerraform(operation="provision")
        avancement = suivi(
            {
                "type": "diagnostic",
                "@level": "error",
                "diagnostic": {"summary": "pool introuvable"},
            }
        )

        assert avancement is not None
        assert "pool introuvable" in avancement.lignes[0].texte

    def test_un_diagnostic_purement_informatif_est_ignore(self) -> None:
        avancement = SuiviTerraform(operation="provision")(
            {"type": "diagnostic", "@level": "info", "diagnostic": {"summary": "x"}}
        )
        assert avancement is None

    def test_un_plan_vide_le_dit_a_la_fin(self) -> None:
        """« Rien à faire » plutôt qu'une barre à zéro sur zéro."""
        fin = SuiviTerraform(operation="provision").fin()
        assert fin.total == 1
        assert fin.fait == 1

    def test_un_plan_non_vide_termine_a_cent_pour_cent(self) -> None:
        suivi = SuiviTerraform(operation="provision")
        suivi(_planifie("create"))
        suivi(_planifie("create"))

        assert suivi.fin().fait == 2

    def test_un_hook_malforme_ne_leve_pas(self) -> None:
        """Le flux vient d'un outil externe : il n'est jamais garanti."""
        suivi = SuiviTerraform(operation="provision")
        assert suivi({"type": "apply_start"}) is not None
        assert (
            suivi({"type": "apply_complete", "hook": {"elapsed_seconds": "x"}})
            is not None
        )


class TestSuiviTerraformInit:
    def test_les_phrases_qui_disent_le_progres_sont_reprises(self) -> None:
        suivi = SuiviTerraformInit()
        avancement = suivi(
            {
                "type": "log",
                "@level": "info",
                "@message": "Installing dmacvicar/libvirt",
            }
        )

        assert avancement is not None
        assert "Installing" in (avancement.description or "")

    def test_le_journal_ordinaire_est_ignore(self) -> None:
        avancement = SuiviTerraformInit()(
            {"type": "log", "@level": "info", "@message": "Terraform initialized"}
        )
        assert avancement is None

    def test_une_erreur_est_affichee(self) -> None:
        avancement = SuiviTerraformInit()(
            {"type": "diagnostic", "@level": "error", "@message": "registre injoignable"}
        )

        assert avancement is not None
        assert avancement.lignes[0].marque == ECHEC


class TestNomCourt:
    def test_le_type_de_la_ressource_est_retire(self) -> None:
        """Il est le même pour toutes les ressources d'un plan."""
        assert (
            nom_court("outscale_security_group_rule.bastion_ssh_in") == "bastion_ssh_in"
        )

    def test_une_adresse_sans_point_reste_entiere(self) -> None:
        assert nom_court("web1") == "web1"
