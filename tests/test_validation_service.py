"""La validation d'un catalogue, éprouvée hors de la CLI.

``validate-structure`` était la fonction la plus complexe du dépôt : 280
lignes, complexité cyclomatique 53, cognitive 65, mesurées le 2026-10-16. Elle
répétait sept fois le même patron de trois instructions, et la validation
n'était appelable que par la CLI : une CI de catalogue ne pouvait l'utiliser
qu'en lançant un sous-processus et en analysant du JSON.

Deux choses s'éprouvent ici, et la seconde est la plus importante :

1. chaque famille de contrôles trouve ce qu'elle doit trouver ;
2. **la forme du document ``--json`` ne bouge pas**. Il est joué en CI dans les
   dépôts de labs : un champ qui disparaît casse un pipeline sans un mot.

Le refactoring a été vérifié en comparant le document avant et après sur les
cinq catalogues réels et sur un catalogue volontairement cassé. Cette
comparaison n'a pourtant **pas** vu deux régressions d'affichage : la rubrique
du `meta.yml` répétait les anomalies de contrat, et les quatre anomalies de
structure avaient disparu de l'écran. Le document, lui, était identique. D'où
les tests de rubrique en fin de fichier.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from dsoxlab.discovery.scanner import discover_labs
from dsoxlab.services.validation_service import (
    FAMILLES,
    TABLE,
    RapportValidation,
    valider,
)

META = """\
schema_version: 1
repo:
  id: casse
  category: test
sections:
  - id: test
    title: Section de test
    labs:
      - test/present
      - test/declare-mais-absent
"""

LAB_PRESENT = """\
id: present
title: Un lab présent
level: l1
skills: [demo]
distros: [any]
doc_url: https://example.invalid/guide
runtime:
  type: shell
  workdir: challenge/work
  fixtures:
    - jamais-posee.txt
"""

LAB_CLE_INCONNUE = """\
id: cle-inconnue
title: Un lab avec une clé hors contrat
level: l1
skills: [demo]
distros: [any]
doc_url: https://example.invalid/guide
exam_pasing_score: 70
runtime:
  type: shell
  workdir: challenge/work
"""

LAB_METADONNEES = """\
id: metadonnees-fausses
title: Un lab aux métadonnées refusées
level: l1
skills: []
distros: []
doc_url: pas-une-url
runtime:
  type: shell
  workdir: challenge/work
"""


@pytest.fixture
def catalogue_casse(tmp_path: Path) -> Path:
    """Un catalogue qui déclenche six des sept familles d'anomalies.

    Les catalogues réels sont sains : leur document est vide, et ne
    protégerait donc aucun refactoring. Celui-ci porte un `lab.yaml` illisible,
    un lab déclaré et absent, une clé hors contrat, un lab sans structure, un
    `schema_version` du futur, des liens morts, une fixture fantôme et des
    métadonnées refusées.
    """
    racine = tmp_path / "casse"
    (racine / "labs").mkdir(parents=True)
    (racine / "meta.yml").write_text(META, encoding="utf-8")

    for nom, contenu in (
        ("present", LAB_PRESENT),
        ("cle-inconnue", LAB_CLE_INCONNUE),
        ("metadonnees-fausses", LAB_METADONNEES),
    ):
        base = racine / "labs" / "test" / nom
        (base / "challenge" / "tests").mkdir(parents=True)
        (base / "challenge" / "work").mkdir(parents=True)
        (base / "lab.yaml").write_text(contenu, encoding="utf-8")
        (base / "README.md").write_text(
            f"# {nom}\n\nUn [lien mort](./absent.md).\n", encoding="utf-8"
        )
        (base / "scenario.md").write_text(f"# {nom}\n\nContexte.\n", encoding="utf-8")
        (base / "challenge" / "tests" / "test_functional.py").write_text(
            "def test_rien() -> None:\n    assert True\n", encoding="utf-8"
        )

    illisible = racine / "labs" / "test" / "illisible"
    illisible.mkdir(parents=True)
    (illisible / "lab.yaml").write_text("id: [ouvert\n  mais: pas: ferme\n", encoding="utf-8")

    sans_structure = racine / "labs" / "test" / "sans-structure"
    sans_structure.mkdir(parents=True)
    (sans_structure / "lab.yaml").write_text(
        LAB_PRESENT.replace("id: present", "id: sans-structure").replace(
            "  fixtures:\n    - jamais-posee.txt\n", ""
        ),
        encoding="utf-8",
    )

    trop_recent = racine / "labs" / "test" / "trop-recent"
    trop_recent.mkdir(parents=True)
    (trop_recent / "lab.yaml").write_text(
        "schema_version: 99\nid: trop-recent\ntitle: Du futur\nlevel: l1\n"
        "skills: [demo]\ndistros: [any]\ndoc_url: https://example.invalid/g\n"
        "runtime:\n  type: shell\n  workdir: challenge/work\n",
        encoding="utf-8",
    )
    return racine


def _rapport(racine: Path) -> RapportValidation:
    return valider(racine, discover_labs(racine))


class TestChaqueFamilleTrouveCeQuElleDoit:
    def test_un_schema_version_du_futur_est_signale(self, catalogue_casse: Path) -> None:
        """En premier, et à la source : un lab écarté faute de version n'est
        pas découvert, donc tous les contrôles suivants l'ignoreraient."""
        rapport = _rapport(catalogue_casse)
        assert rapport.par_famille("contract"), "le lab du futur doit être nommé"

    def test_un_lab_illisible_et_un_lab_absent_sont_signales(
        self, catalogue_casse: Path
    ) -> None:
        """Les deux façons dont un lab disparaît sans un mot (issue #198)."""
        cles = {a.cle for a in _rapport(catalogue_casse).par_famille("catalog")}
        assert "lab_yaml_illisible_position" in cles
        assert "lab_declare_absent" in cles

    def test_une_cle_hors_contrat_est_signalee_avec_la_plus_proche(
        self, catalogue_casse: Path
    ) -> None:
        anomalies = _rapport(catalogue_casse).par_famille("unknown_key")
        assert anomalies
        assert anomalies[0].params.get("suggestion") == "exam_passing_score"

    def test_un_lab_sans_structure_est_signale(self, catalogue_casse: Path) -> None:
        anomalies = _rapport(catalogue_casse).par_famille("structure")
        assert anomalies
        assert all(a.lab == "sans-structure" for a in anomalies)

    def test_les_liens_morts_et_la_fixture_fantome_sont_signales(
        self, catalogue_casse: Path
    ) -> None:
        anomalies = _rapport(catalogue_casse).par_famille("content")
        assert len(anomalies) >= 4
        assert all(a.lab for a in anomalies), "une anomalie de contenu nomme son lab"

    def test_les_metadonnees_refusees_nomment_leur_champ(
        self, catalogue_casse: Path
    ) -> None:
        anomalies = _rapport(catalogue_casse).par_famille("metadata")
        champs = {a.champ for a in anomalies}
        assert {"skills", "distros", "doc_url"} <= champs

    def test_un_catalogue_sain_ne_rend_rien(self, tmp_path: Path) -> None:
        """Le contre-test : sans lui, une validation qui crie toujours passerait."""
        racine = tmp_path / "sain"
        (racine / "labs").mkdir(parents=True)
        (racine / "meta.yml").write_text(
            "repo:\n  id: sain\n  category: test\n", encoding="utf-8"
        )
        rapport = _rapport(racine)
        assert rapport.ok
        assert rapport.anomalies == []


class TestLaFormeDuDocumentNeBougePas:
    """Le document ``--json`` est joué en CI dans les dépôts de labs."""

    def test_toutes_les_familles_figurent_dans_les_comptes(
        self, catalogue_casse: Path
    ) -> None:
        """À zéro s'il le faut : un tableau de bord qui n'aurait pas la clé ne
        saurait pas si la famille est saine ou si l'outil ne la connaît pas."""
        comptes = _rapport(catalogue_casse).comptes()
        assert set(comptes) == set(FAMILLES)

    def test_les_comptes_collent_aux_anomalies(self, catalogue_casse: Path) -> None:
        rapport = _rapport(catalogue_casse)
        assert sum(rapport.comptes().values()) == len(rapport.anomalies)

    def test_un_guide_injoignable_nest_pas_une_anomalie(self) -> None:
        """Un contrôle qui n'a pas pu regarder ne conclut pas au rouge.

        Peindre en rouge pour une coupure de réseau apprend surtout à relancer
        la CI sans lire le message.
        """
        from dsoxlab.services.validation_service import Anomalie

        rapport = RapportValidation(labs_examines=1)
        rapport.urls_injoignables.append(
            Anomalie("doc_url", "content_doc_url_unreachable", {"url": "https://x"})
        )
        assert rapport.ok, "les guides muets ne font pas échouer la validation"

    def test_les_urls_ne_sont_pas_verifiees_par_defaut(
        self, catalogue_casse: Path
    ) -> None:
        """Le seul contrôle réseau, et il reste optionnel."""
        assert _rapport(catalogue_casse).urls_examinees is False


class TestLesRubriquesDAffichage:
    """Ce que la comparaison du document n'a pas vu, et qui était cassé."""

    def test_chaque_anomalie_porte_une_rubrique_connue(
        self, catalogue_casse: Path
    ) -> None:
        connues = {famille.entete for famille in TABLE} | {"doc_url_issues_header"}
        for anomalie in _rapport(catalogue_casse).anomalies:
            assert anomalie.rubrique in connues, anomalie.cle

    def test_les_deux_rubriques_du_contrat_ne_se_confondent_pas(
        self, catalogue_casse: Path
    ) -> None:
        """La famille `contract` a DEUX titres : les versions de schéma, et les
        champs du `meta.yml`. Grouper sur la famille affichait les mêmes
        anomalies sous les deux."""
        rubriques = {a.rubrique for a in _rapport(catalogue_casse).par_famille("contract")}
        assert rubriques == {"contract_issues_header"}, (
            "aucune anomalie de version ne doit porter la rubrique du meta.yml"
        )

    def test_la_structure_a_un_titre_pour_sapprocher(self, catalogue_casse: Path) -> None:
        """Sans titre, ses anomalies étaient dans le document et pas à l'écran."""
        anomalies = _rapport(catalogue_casse).par_famille("structure")
        assert anomalies
        assert all(a.rubrique == "structure_issues_header" for a in anomalies)

    def test_chaque_rubrique_de_la_table_a_sa_traduction(self) -> None:
        from dsoxlab.i18n.strings import en, fr

        for famille in TABLE:
            assert famille.entete in fr.STRINGS, famille.entete
            assert famille.entete in en.STRINGS, famille.entete
