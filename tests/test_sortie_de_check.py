"""Ce que ``check`` montre quand des tests échouent.

Le défaut corrigé, mesuré avant de l'être : sur le lab de démonstration et ses
trois tests rouges, ``check`` déversait **26 lignes** de sortie pytest brute
avant son panneau de résultat. Des ``assert False``, des
``+ where exists = PosixPath('reponses/indice.txt').exists`` et deux
séparateurs de section, affichés à quelqu'un dont le lab porte sur
l'administration d'un système.

L'information utile était pourtant déjà là, dans le **nom** des tests : les labs
de ce contrat les nomment en phrases (``test_le_mot_du_cours``), exactement pour
qu'ils se lisent.

Ces tests tiennent les trois promesses de la correction :

1. par défaut, les noms des tests en échec, pas leurs tracebacks ;
2. la sortie brute reste accessible par ``-v``, pour qui veut creuser ;
3. elle reste **intégralement** dans le document ``--json``, parce qu'un
   programme n'a pas de « -v » à passer et que c'est son seul accès au détail.

La troisième est la plus importante : une sortie qu'on raccourcit pour un humain
ne doit rien retirer à un appelant automatisé.
"""

from __future__ import annotations

from dsoxlab.services.lab_service import echecs_de_tests


def noms(sortie: str) -> list[str]:
    """Les noms seuls, pour les assertions qui ne portent pas sur le message."""
    return [e.nom for e in echecs_de_tests(sortie)]

#: Sortie pytest reprise d'une exécution RÉELLE sur le lab de démonstration,
#: zone FAILURES comprise. La fidélité de cette chaîne est le test lui-même :
#: une première version, écrite de mémoire, omettait les lignes
#: « E   AssertionError: … ». Les tests passaient, et la fonction perdait
#: pourtant le message de l'auteur du lab sur une vraie sortie.
SORTIE_RESUME = """\
=================================== FAILURES ===================================
____________________________ test_le_mot_du_cours _____________________________
labs/demo/premiers-pas/challenge/tests/test_functional.py:44: in test_le_mot_du_cours
    _verifier("cours.txt")
E   AssertionError: reponses/cours.txt manquant. Le mot attendu se lit dans : dsoxlab course premiers-pas
E     Crée le fichier, par exemple : mkdir -p reponses && echo <le mot> > reponses/cours.txt
E   assert False
E    +  where False = exists()
E    +    where exists = PosixPath('reponses/cours.txt').exists
_________________________ test_le_mot_de_la_mission ___________________________
labs/demo/premiers-pas/challenge/tests/test_functional.py:52: in test_le_mot_de_la_mission
    _verifier("mission.txt")
E   AssertionError: reponses/mission.txt manquant. Le mot attendu se lit dans : dsoxlab challenge premiers-pas
E   assert False
=========================== short test summary info ============================
FAILED labs/demo/premiers-pas/challenge/tests/test_functional.py::test_le_mot_du_cours
FAILED labs/demo/premiers-pas/challenge/tests/test_functional.py::test_le_mot_de_la_mission
============================== 2 failed in 0.01s ===============================
"""

#: L'autre forme, un verdict par test, que pytest produit sans « -q ».
SORTIE_VERDICTS = """\
labs/x/challenge/tests/test_functional.py::test_le_service_ecoute FAILED  [ 50%]
labs/x/challenge/tests/test_functional.py::test_la_regle_persiste PASSED  [100%]
"""


class TestExtractionDesEchecs:
    def test_la_section_de_resume_donne_les_noms_des_tests(self) -> None:
        assert noms(SORTIE_RESUME) == [
            "test_le_mot_du_cours",
            "test_le_mot_de_la_mission",
        ]

    def test_les_verdicts_par_test_donnent_les_noms(self) -> None:
        """Sans « -q », pytest écrit le verdict à la suite du nodeid."""
        assert noms(SORTIE_VERDICTS) == ["test_le_service_ecoute"]

    def test_un_test_qui_passe_nest_jamais_cite(self) -> None:
        assert "test_la_regle_persiste" not in noms(SORTIE_VERDICTS)

    def test_un_nom_nest_cite_quune_fois(self) -> None:
        """Le même test apparaît dans les FAILURES et dans le résumé."""
        double = SORTIE_RESUME + SORTIE_RESUME
        assert noms(double).count("test_le_mot_du_cours") == 1

    def test_une_sortie_sans_verdict_ne_rend_rien(self) -> None:
        """pytest planté avant la collecte : il n'y a aucun nom à donner.

        L'appelant doit alors montrer la sortie brute, puisqu'elle est tout ce
        qui existe. Rendre une liste vide est donc la bonne réponse, et non une
        approximation.
        """
        assert echecs_de_tests("ImportError: no module named conftest") == []

    def test_une_erreur_de_collecte_compte_comme_un_echec(self) -> None:
        """``ERROR`` compte autant que ``FAILED`` : le lab est injouable."""
        sortie = "ERROR labs/x/challenge/tests/test_functional.py::test_le_socle\n"
        assert noms(sortie) == ["test_le_socle"]


class TestLeMessageDeLAuteurDuLab:
    """Le second niveau, et la vraie leçon de cette correction.

    Une première version de `echecs_de_tests` ne rendait que les noms. Le
    compteur de lignes de trace était satisfait, et pourtant l'écran avait
    PERDU l'information la plus utile : la phrase que l'auteur du lab écrit
    dans son `assert`, avec le geste de réparation. Une mesure ne l'a pas vu,
    une capture avant/après l'a vu tout de suite.

    D'où ces tests : ils tiennent ce que la métrique ne sait pas tenir.
    """

    def test_le_message_dassertion_est_conserve(self) -> None:
        echecs = echecs_de_tests(SORTIE_RESUME)
        message = echecs[0].message
        assert message is not None
        assert "reponses/cours.txt manquant" in message

    def test_le_geste_de_reparation_survit(self) -> None:
        """La deuxième ligne de l'assertion, celle qui dit quoi taper."""
        message = echecs_de_tests(SORTIE_RESUME)[0].message or ""
        assert "mkdir -p reponses" in message

    def test_la_reconstruction_dexpression_de_pytest_est_ecartee(self) -> None:
        """`assert False` et `+ where exists = PosixPath(...)` ne disent rien
        à qui apprend l'administration d'un système."""
        message = echecs_de_tests(SORTIE_RESUME)[0].message or ""
        assert "assert False" not in message
        assert "where" not in message

    def test_chaque_test_recoit_son_propre_message(self) -> None:
        par_nom = {e.nom: e.message for e in echecs_de_tests(SORTIE_RESUME)}
        assert "cours.txt" in (par_nom["test_le_mot_du_cours"] or "")
        assert "mission.txt" in (par_nom["test_le_mot_de_la_mission"] or "")

    def test_un_echec_sans_message_reste_un_echec(self) -> None:
        """Erreur de collecte : il n'y a pas de zone FAILURES à lire."""
        echec = echecs_de_tests(
            "ERROR labs/x/challenge/tests/test_functional.py::test_le_socle\n"
        )[0]
        assert echec.nom == "test_le_socle"
        assert echec.message is None

    def test_la_phrase_se_lit_sans_le_prefixe_technique(self) -> None:
        echec = echecs_de_tests(SORTIE_VERDICTS)[0]
        assert echec.phrase == "le service ecoute"


class TestLesEchecsQuiSeRessemblentSontGroupes:
    """Cinq tests, une seule cause : une seule phrase.

    Vu en jouant un lab de `linux-dsoxlab-training` dont la fixture n'était pas
    encore posée : les cinq tests rendaient le même « premiers-pas.txt
    introuvable, lance d'abord dsoxlab run », et l'apprenant lisait cinq fois
    la même phrase sur dix lignes.
    """

    def _echecs_meme_cause(self) -> str:
        bloc = (
            "=================================== FAILURES =================================\n"
        )
        for nom in ("test_un", "test_deux", "test_trois"):
            bloc += (
                f"____________________________ {nom} _____________________________\n"
                "E   AssertionError: premiers-pas.txt introuvable, lance dsoxlab run\n"
                "E   assert False\n"
            )
        bloc += "=========================== short test summary info ===========================\n"
        for nom in ("test_un", "test_deux", "test_trois"):
            bloc += f"FAILED labs/x/challenge/tests/test_functional.py::{nom}\n"
        return bloc

    def test_un_message_partage_ne_sort_quune_fois(self) -> None:
        from dsoxlab.reporting.console import _grouper_par_message

        groupes = _grouper_par_message(echecs_de_tests(self._echecs_meme_cause()))

        assert len(groupes) == 1, "une cause, un groupe"
        message, noms = groupes[0]
        assert message is not None and "dsoxlab run" in message
        assert noms == ["un", "deux", "trois"]

    def test_des_messages_distincts_restent_distincts(self) -> None:
        from dsoxlab.reporting.console import _grouper_par_message

        groupes = _grouper_par_message(echecs_de_tests(SORTIE_RESUME))

        assert len(groupes) == 2, "deux causes différentes, deux groupes"

    def test_un_echec_sans_message_nest_pas_groupe_avec_un_autre(self) -> None:
        """Deux absences de message ne sont pas une cause commune."""
        from dsoxlab.reporting.console import _grouper_par_message
        from dsoxlab.services.lab_service import EchecDeTest

        groupes = _grouper_par_message(
            [EchecDeTest(nom="test_a"), EchecDeTest(nom="test_b")]
        )

        assert len(groupes) == 2
