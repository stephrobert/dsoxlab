"""Le nom lu dans la sortie pytest est celui de la FONCTION, et son message suit.

TROIS DÉFAUTS, mesurés le 2026-11-03 en faisant échouer un test de chaque forme
et en lisant la sortie réelle de pytest, reproduite ci-dessous mot pour mot.

    forme de test        nom extrait                 message d'assertion
    dans une classe      TestDansUneClasse  ✘        perdu  ✘
    simple               test_simple_echoue ✔        montré ✔
    paramétré            test_parametre_echoue ✔     perdu  ✘

Le premier était SILENCIEUX et grave : un `exam_blocking_checks` nommant un test
rangé dans une classe n'aurait jamais correspondu, et l'exigence critique aurait
été désarmée sans un mot. C'est exactement le défaut que ce champ existe pour
fermer.

Le troisième n'était pas latent : trois labs du catalogue emploient
`parametrize`, et le message perdu est la phrase bilingue que l'auteur du lab a
écrite pour l'apprenant. Un échec rendait donc un nom de test et rien d'autre.
"""
from __future__ import annotations

import pytest

from dsoxlab.services.lab_service import echecs_de_tests

# Sortie pytest RÉELLE, relevée le 2026-11-03 sur un fichier portant un test
# dans une classe, un test simple et un test paramétré à deux cas, tous en
# échec. Elle est reproduite plutôt que reconstituée : une sortie inventée
# aurait validé le motif qu'on venait d'écrire, et non celui dont pytest a
# besoin.
SORTIE = """\
============================= test session starts ==============================
collected 4 items

test_formes.py FFFF                                                      [100%]

=================================== FAILURES ===================================
___________________ TestDansUneClasse.test_en_classe_echoue ____________________

self = <test_formes.TestDansUneClasse object at 0x7f0000000000>

    def test_en_classe_echoue(self):
>       assert False, "le message de la classe"
E       AssertionError: le message de la classe
E       assert False

test_formes.py:6: AssertionError
______________________________ test_simple_echoue ______________________________

    def test_simple_echoue():
>       assert False, "le message simple"
E       AssertionError: le message simple
E       assert False

test_formes.py:10: AssertionError
__________________________ test_parametre_echoue[a-1] __________________________

cas = 'a-1'

    @pytest.mark.parametrize("cas", ["a-1", "b-2"])
    def test_parametre_echoue(cas):
>       assert False, f"le message {cas}"
E       AssertionError: le message a-1
E       assert False

test_formes.py:15: AssertionError
__________________________ test_parametre_echoue[b-2] __________________________

cas = 'b-2'

    @pytest.mark.parametrize("cas", ["a-1", "b-2"])
    def test_parametre_echoue(cas):
>       assert False, f"le message {cas}"
E       AssertionError: le message b-2
E       assert False

test_formes.py:15: AssertionError
=========================== short test summary info ============================
FAILED test_formes.py::TestDansUneClasse::test_en_classe_echoue - AssertionEr...
FAILED test_formes.py::test_simple_echoue - AssertionError: le message simple
FAILED test_formes.py::test_parametre_echoue[a-1] - AssertionError: le messag...
FAILED test_formes.py::test_parametre_echoue[b-2] - AssertionError: le messag...
============================== 4 failed in 0.03s ===============================
"""


@pytest.fixture(scope="module")
def par_nom() -> dict[str, str | None]:
    return {echec.nom: echec.message for echec in echecs_de_tests(SORTIE)}


class TestLeNomEstCeluiDeLaFonction:

    def test_un_test_en_classe_rend_le_test_et_non_la_classe(self, par_nom):
        """Le défaut silencieux : `::(\\w+)` prenait le PREMIER segment.

        Sans ce test, `exam_blocking_checks: [test_en_classe_echoue]` ne
        correspondrait à rien, et l'épreuve serait reçue alors que son exigence
        critique a échoué.
        """
        assert "test_en_classe_echoue" in par_nom
        assert "TestDansUneClasse" not in par_nom

    def test_aucun_nom_de_classe_ne_passe(self, par_nom):
        """Le garde-fou général, qui vaut pour une classe nommée autrement."""
        assert not [nom for nom in par_nom if nom[:1].isupper()], (
            f"un nom en majuscule initiale ressemble à une classe : {par_nom}"
        )

    def test_un_test_parametre_rend_un_seul_nom(self, par_nom):
        """Deux cas en échec, un seul test : l'apprenant lit un nom, pas deux."""
        assert "test_parametre_echoue" in par_nom
        assert "test_parametre_echoue[a-1]" not in par_nom

    def test_les_trois_formes_sont_vues(self, par_nom):
        assert set(par_nom) == {
            "test_en_classe_echoue", "test_simple_echoue", "test_parametre_echoue",
        }


class TestLeMessageSuitLeNom:
    """Le message d'assertion est ce que l'auteur du lab a écrit pour l'apprenant."""

    def test_le_message_dun_test_en_classe_nest_plus_perdu(self, par_nom):
        assert par_nom["test_en_classe_echoue"] == "le message de la classe"

    def test_le_message_dun_test_parametre_nest_plus_perdu(self, par_nom):
        """Celui-là touchait trois labs du catalogue, aujourd'hui."""
        assert par_nom["test_parametre_echoue"] == "le message a-1"

    def test_un_test_parametre_rend_le_message_du_PREMIER_cas(self, par_nom):
        """Le premier à avoir cassé, et pas le dernier lu.

        `_sections_dechec` conserve les lignes au lieu de les réinitialiser à
        chaque section du même nom : sans cela, on rendrait `le message b-2`,
        c'est-à-dire le dernier cas, qui n'est pas celui qui renseigne.
        """
        assert par_nom["test_parametre_echoue"] != "le message b-2"

    def test_le_message_dun_test_simple_na_pas_regresse(self, par_nom):
        """Le seul cas qui marchait avant : il doit continuer de marcher."""
        assert par_nom["test_simple_echoue"] == "le message simple"

    def test_la_reconstruction_de_pytest_est_ecartee(self, par_nom):
        """`assert False` est du bruit pour qui apprend l'administration."""
        for nom, message in par_nom.items():
            assert message is not None
            assert "assert False" not in message, nom


class TestCeQuiNeChangePas:

    def test_une_sortie_sans_rien_de_reconnaissable_rend_une_liste_vide(self):
        """L'appelant doit alors montrer la sortie brute, qui est tout ce qu'il a."""
        assert echecs_de_tests("pytest s'est effondré avant de collecter") == []

    def test_un_message_portant_des_deux_points_ne_trompe_pas_la_lecture(self):
        """La recherche est bornée au nodeid, et c'est nécessaire.

        Prendre le dernier segment `::` de la ligne ENTIÈRE rendrait un
        fragment du message dès qu'il en contient, ce qui arrive avec un
        chemin ou un nodeid cité dans l'assertion.
        """
        sortie = (
            "FAILED test_x.py::test_le_vrai_nom - AssertionError: "
            "attendu fichier.py::autre_chose\n"
        )
        assert [e.nom for e in echecs_de_tests(sortie)] == ["test_le_vrai_nom"]
