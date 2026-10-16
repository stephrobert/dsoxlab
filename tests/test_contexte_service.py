"""Ce que `dsoxlab use` accepte, et ce qu'il refuse en le disant.

Les trois refus viennent de pièges observés, pas de principes. Le plus vicieux
est `dsoxlab use incus` : le nom ressemble à un provider, la commande posait
une SECTION nommée « incus », et `list-labs` répondait ensuite « Aucun lab
trouvé ». L'apprenant concluait que son catalogue était vide.

Chaque refus est éprouvé avec son contre-cas : un garde-fou qui refuserait
aussi ce qui est légitime coûte plus cher que le défaut qu'il couvre.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from dsoxlab.services.contexte_service import (
    Declarations,
    MetaIllisible,
    decouper,
    lire_declarations,
    refus_eventuel,
)

META = """\
repo:
  id: demo
  category: demo
infra:
  provider: [kvm, incus]
sections:
  - id: linux
    title: Linux
  - id: reseau
    title: Réseau
"""


def _poser(racine: Path, contenu: str) -> Path:
    (racine / "meta.yml").write_text(contenu, encoding="utf-8")
    return racine


class TestCeQueLeMetaDeclare:
    def test_un_depot_sans_meta_ne_declare_rien(self, tmp_path: Path) -> None:
        """Ce n'est pas une erreur : un `meta.yml` absent ne filtre rien."""
        assert lire_declarations(tmp_path) == Declarations()

    def test_une_liste_de_providers_est_lue_en_entier(self, tmp_path: Path) -> None:
        declarations = lire_declarations(_poser(tmp_path, META))
        assert declarations.providers == ("kvm", "incus")
        assert declarations.sections == ("linux", "reseau")

    def test_un_provider_unique_ecrit_en_chaine_est_lu(self, tmp_path: Path) -> None:
        contenu = "repo:\n  id: demo\ninfra:\n  provider: kvm\n"
        assert lire_declarations(_poser(tmp_path, contenu)).providers == ("kvm",)

    def test_un_meta_illisible_se_distingue_d_un_meta_absent(
        self, tmp_path: Path
    ) -> None:
        """Les deux situations appellent des gestes opposés : réparer le
        fichier, ou ne rien filtrer."""
        _poser(tmp_path, "repo:\n  id: [non fermé\n")
        with pytest.raises(MetaIllisible):
            lire_declarations(tmp_path)


class TestLesRefus:
    def test_un_provider_pris_pour_une_section_est_refuse(self) -> None:
        declarations = Declarations(providers=("kvm", "incus"), sections=("linux",))

        refus = refus_eventuel(declarations, context="incus")

        assert refus is not None
        assert refus.cle == "provider_not_a_section"
        assert refus.params == {"name": "incus"}

    def test_un_nom_qui_est_les_deux_passe(self) -> None:
        """Un catalogue a le droit d'appeler une section comme son provider :
        le refus ne vaut que si la section n'existe pas."""
        declarations = Declarations(providers=("kvm",), sections=("kvm", "linux"))
        assert refus_eventuel(declarations, context="kvm") is None

    def test_une_section_inconnue_est_refusee_en_montrant_les_vraies(self) -> None:
        declarations = Declarations(sections=("linux", "reseau"))

        refus = refus_eventuel(declarations, context="windows")

        assert refus is not None
        assert refus.cle == "section_unknown"
        assert refus.params == {"name": "windows", "sections": "linux, reseau"}

    def test_un_niveau_ne_fait_pas_echouer_sa_section(self) -> None:
        """`linux/l2` vise la section `linux` : c'est elle qu'on valide."""
        declarations = Declarations(sections=("linux",))
        assert refus_eventuel(declarations, context="linux/l2") is None

    def test_un_depot_sans_sections_declarees_ne_filtre_rien(self) -> None:
        """Sinon tout dépôt sans bloc « sections » refuserait tout."""
        assert refus_eventuel(Declarations(), context="nimporte-quoi") is None

    def test_un_provider_inconnu_est_refuse_a_la_commande(self) -> None:
        """Et non au `provision` suivant, loin de la commande fautive."""
        declarations = Declarations(providers=("kvm", "incus"))

        refus = refus_eventuel(declarations, provider="aws")

        assert refus is not None
        assert refus.cle == "provider_unknown"
        assert refus.params == {"name": "aws", "candidates": "kvm, incus"}

    def test_un_depot_sans_provider_declare_accepte_le_choix(self) -> None:
        assert refus_eventuel(Declarations(), provider="kvm") is None

    def test_la_section_est_jugee_avant_le_provider(self) -> None:
        """Deux fautes à la fois : on nomme celle que l'apprenant a tapée en
        premier, plutôt que de lui en signaler une qu'il n'a pas encore lue."""
        declarations = Declarations(providers=("kvm",), sections=("linux",))

        refus = refus_eventuel(declarations, context="windows", provider="aws")

        assert refus is not None
        assert refus.cle == "section_unknown"


class TestLeDecoupage:
    def test_une_section_seule(self) -> None:
        assert decouper("linux") == ("linux", None)

    def test_une_section_et_un_niveau(self) -> None:
        assert decouper("linux/l2") == ("linux", "l2")

    def test_un_niveau_peut_porter_une_barre(self) -> None:
        """Le découpage s'arrête à la première : le reste appartient au niveau."""
        assert decouper("linux/l2/avance") == ("linux", "l2/avance")

    def test_les_espaces_autour_ne_comptent_pas(self) -> None:
        assert decouper("  linux  ") == ("linux", None)

    def test_une_chaine_vide_ne_pose_aucune_section(self) -> None:
        assert decouper("") == (None, None)
