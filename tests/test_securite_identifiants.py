"""Ce qu'un identifiant de catalogue a le droit d'être.

Un catalogue est une entrée non fiable, et ses identifiants finissent dans un
document remis à un portail. Le consommateur les refusera s'ils portent de quoi
mentir à l'œil ou casser un analyseur : autant ne pas les émettre, et le dire
là où l'on sait quel champ et quel catalogue sont en cause.

Le repli sur le nom du répertoire compte autant que le `repo.id` : un nom de
dossier est libre.
"""
from __future__ import annotations

import pytest

from dsoxlab.security import IdentifiantRefuse, identifiant_sur


class TestCeQuiPasse:
    @pytest.mark.parametrize("valeur", [
        "linux-dsoxlab-training",
        "l2-swap-management",
        "CKA_capstone.portail-2",
        "é-accentué-mais-lisible",
        "a" * 128,
    ])
    def test_un_identifiant_ordinaire(self, valeur: str) -> None:
        assert identifiant_sur(valeur, champ="catalog.id") == valeur

    def test_une_section_vide_est_permise(self) -> None:
        """Un lab qu'aucune règle ne rattache n'a pas de section, et c'est bon."""
        assert identifiant_sur("", champ="section", vide_permis=True) == ""


class TestCeQuiEstRefuse:
    def test_un_identifiant_vide(self) -> None:
        with pytest.raises(IdentifiantRefuse):
            identifiant_sur("", champ="catalog.id")

    def test_trop_long(self) -> None:
        with pytest.raises(IdentifiantRefuse) as refus:
            identifiant_sur("a" * 129, champ="catalog.id")
        assert refus.value.cle == "securite_identifiant_trop_long"
        assert refus.value.params["max"] == 128

    @pytest.mark.parametrize(("valeur", "nom"), [
        ("lab\r\ninjecte: oui", "retour chariot"),
        ("lab\x00nul", "octet nul"),
        ("lab\x1b[31mrouge", "échappement ANSI"),
        ("lab\u202egnp.exe", "surcharge de direction"),
        ("lab\u200bfantome", "largeur nulle"),
        ("lab\ufeffbom", "BOM"),
    ])
    def test_un_caractere_qui_ment_a_l_oeil(self, valeur: str, nom: str) -> None:
        """Chacun sert à faire lire autre chose que ce que la donnée dit.

        Le plus parlant est la surcharge de direction : `lab\\u202egnp.exe`
        s'affiche `labexe.png` dans un terminal, sans que la valeur change.
        """
        with pytest.raises(IdentifiantRefuse) as refus:
            identifiant_sur(valeur, champ="catalog.id")
        assert refus.value.cle == "securite_identifiant_caractere"
        assert refus.value.params["code"].startswith("U+"), (
            f"{nom} doit être nommé par son code"
        )

    def test_le_champ_fautif_est_nomme(self) -> None:
        """Le message doit dire où chercher, pas seulement que c'est refusé."""
        with pytest.raises(IdentifiantRefuse) as refus:
            identifiant_sur("mauvais\ridentifiant", champ="lab_id")
        assert refus.value.champ == "lab_id"


class TestRefuserPlutotQueNettoyer:
    def test_rien_n_est_assaini_en_silence(self) -> None:
        """Nettoyer romprait le rattachement entre une preuve et son lab.

        Un identifiant faux vaut mieux qu'un identifiant faussé sans le dire :
        le second produit une preuve qui atteste un lab qui n'existe pas.
        """
        with pytest.raises(IdentifiantRefuse):
            identifiant_sur("lab\u200b-swap", champ="lab_id")
