"""Le moteur fait-il ce que le contrat déclare ?

Deux défauts de la même famille, et c'est pourquoi ils sont testés ensemble :
l'auteur d'un catalogue écrit quelque chose, et le moteur en fait autre chose.

* **Une section déclarée était écrasée** (#87). Le défaut par défaut de
  ``LabDefinition.section`` était ``"linux"``, et le scanner s'en servait comme
  sentinelle « rien de déclaré ». La valeur ``linux`` devenait donc
  indiscernable de l'absence, et un nom de domaine vivait dans le moteur — ce
  que la règle d'architecture la plus stricte du projet interdit.

* **Quatre clés étaient écrites et jamais lues** (#126), dont un
  ``exam_passing_score`` dans onze labs d'examen. Un apprenant qui rendait
  40/100 sur un examen blanc ne lisait nulle part qu'il avait échoué.

Le vrai livrable du second n'est pas de solder quatre clés : c'est qu'une
cinquième ne puisse plus s'installer en silence. D'où les tests du garde-fou,
qui vérifient surtout qu'il *mord*.
"""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest

from dsoxlab.discovery.scanner import discover_labs
from dsoxlab.models.lab import LabDefinition
from dsoxlab.models.repo import RepoMetadata
from dsoxlab.services.progress_service import exam_percentage, exam_verdict
from dsoxlab.validators.contract import validate_unknown_keys
from dsoxlab.validators.metadata import validate_metadata

LAB_SANS_SECTION = """\
id: {id}
title: {id}
level: l1
skills: [demo]
distros: [any]
doc_url: https://example.test/docs/{id}/
runtime:
  type: shell
  workdir: challenge/work
"""


def _catalogue(racine: Path, *, category: str = "terraform") -> None:
    (racine / "meta.yml").write_text(
        f"repo:\n  id: catalogue-test\n  category: {category}\n",
        encoding="utf-8",
    )


def _lab(racine: Path, lab_id: str, extra: str = "") -> Path:
    dossier = racine / "labs" / "bloc" / lab_id
    dossier.mkdir(parents=True)
    (dossier / "lab.yaml").write_text(
        LAB_SANS_SECTION.format(id=lab_id) + extra, encoding="utf-8"
    )
    return dossier


# ── #87 : la section déclarée est la section retenue ─────────────────────────


class TestSectionDeclaree:
    def test_le_modele_ne_pose_aucune_section_par_defaut(self, tmp_path: Path) -> None:
        """La sentinelle est None, jamais un nom de domaine."""
        (tmp_path / "lab.yaml").write_text(
            LAB_SANS_SECTION.format(id="sans-section"), encoding="utf-8"
        )
        assert LabDefinition.from_yaml(tmp_path / "lab.yaml").section is None

    def test_section_linux_survit_dans_un_catalogue_terraform(
        self, tmp_path: Path
    ) -> None:
        """Le cas exact de l'issue : deux labs, une seule déclaration honorée.

        Avant correction, `lab-a` ressortait en `terraform` parce que sa valeur
        déclarée était celle qui servait de sentinelle.
        """
        _catalogue(tmp_path, category="terraform")
        _lab(tmp_path, "lab-a", extra="section: linux\n")
        _lab(tmp_path, "lab-b", extra="section: reseau\n")
        _lab(tmp_path, "lab-c")

        sections = {lab.id: lab.section for lab in discover_labs(tmp_path)}
        assert sections == {
            "lab-a": "linux",
            "lab-b": "reseau",
            "lab-c": "terraform",
        }

    def test_le_mode_legacy_infere_encore_depuis_le_chemin(
        self, tmp_path: Path
    ) -> None:
        """Sans meta.yml, la section vient du chemin — comportement conservé."""
        dossier = tmp_path / "labs" / "reseau" / "l1" / "lab-x"
        dossier.mkdir(parents=True)
        (dossier / "lab.yaml").write_text(
            LAB_SANS_SECTION.format(id="lab-x"), encoding="utf-8"
        )
        assert discover_labs(tmp_path)[0].section == "reseau"

    def test_le_mode_legacy_ne_devine_rien_quand_il_ne_sait_pas(
        self, tmp_path: Path
    ) -> None:
        """Le chemin ne porte pas de section : None, et surtout pas « linux »."""
        dossier = tmp_path / "labs" / "l1" / "lab-y"
        dossier.mkdir(parents=True)
        (dossier / "lab.yaml").write_text(
            LAB_SANS_SECTION.format(id="lab-y"), encoding="utf-8"
        )
        assert discover_labs(tmp_path)[0].section is None


#: Modules qui *interprètent le catalogue* : ils lisent le contrat, en tirent
#: des décisions et l'affichent. Un nom de domaine ne peut y être qu'une valeur
#: métier — jamais le nom d'un outil qu'on invoque, ce qui est le cas légitime
#: qu'on trouve ailleurs (`infra/terraform.py`, `services/doctor.py`).
_MODULES_DU_CATALOGUE = ("models/", "discovery/", "reporting/", "validators/")

#: Ces deux-là ne sont le nom d'aucun outil que dsoxlab lance : leur présence
#: en littéral, où que ce soit dans le paquet, est forcément une valeur métier.
_DOMAINES_JAMAIS_OUTILS = frozenset({"linux", "kubernetes"})

_DOMAINES = frozenset({"linux", "ansible", "kubernetes", "terraform", "docker"})


def _litteraux(source: str) -> set[str]:
    """Les chaînes écrites en dur, docstrings exclues.

    Les commentaires et les docstrings ont le droit de nommer un domaine : ils
    donnent des exemples, et le contrat en a besoin pour être lisible. C'est la
    chaîne que le code manipule qui est en cause, jamais celle qui l'explique.
    """
    import ast

    arbre = ast.parse(source)
    docstrings = {
        noeud.body[0].value
        for noeud in ast.walk(arbre)
        if isinstance(
            noeud, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)
        )
        and noeud.body
        and isinstance(noeud.body[0], ast.Expr)
        and isinstance(noeud.body[0].value, ast.Constant)
    }
    return {
        noeud.value
        for noeud in ast.walk(arbre)
        if isinstance(noeud, ast.Constant)
        and isinstance(noeud.value, str)
        and noeud not in docstrings
    }


def _sources_du_paquet() -> list[tuple[str, str]]:
    import dsoxlab

    racine = Path(dsoxlab.__file__).parent
    return [
        (chemin.relative_to(racine).as_posix(), chemin.read_text(encoding="utf-8"))
        for chemin in sorted(racine.rglob("*.py"))
    ]


class TestMoteurAgnostique:
    def test_aucun_domaine_dans_ce_qui_lit_le_catalogue(self) -> None:
        coupables = [
            f"{nom}: {sorted(_DOMAINES & _litteraux(source))}"
            for nom, source in _sources_du_paquet()
            if nom.startswith(_MODULES_DU_CATALOGUE)
            and _DOMAINES & _litteraux(source)
        ]
        assert not coupables, (
            "Un nom de domaine sert de valeur métier dans le moteur :\n  "
            + "\n  ".join(coupables)
        )

    def test_deux_domaines_sont_bannis_du_paquet_entier(self) -> None:
        """`linux` et `kubernetes` ne sont le nom d'aucun outil qu'on lance."""
        coupables = [
            f"{nom}: {sorted(_DOMAINES_JAMAIS_OUTILS & _litteraux(source))}"
            for nom, source in _sources_du_paquet()
            if _DOMAINES_JAMAIS_OUTILS & _litteraux(source)
        ]
        assert not coupables, "\n  ".join(coupables)

    def test_le_garde_fou_mord_et_ignore_les_docstrings(self) -> None:
        """Un test qui ne peut pas échouer ne prouve rien."""
        assert _DOMAINES & _litteraux('section = "linux"\n')
        assert not _DOMAINES & _litteraux('"""Exemple : category: linux."""\n')
        assert not _DOMAINES & _litteraux("# category: linux\nx = 1\n")


# ── #126 : `exam_passing_score`, un examen rend un verdict ───────────────────


class TestVerdictDExamen:
    def test_sous_le_seuil_le_verdict_est_un_echec(self) -> None:
        assert exam_verdict(40, 100, 70) is False

    def test_au_seuil_exact_le_verdict_est_une_reussite(self) -> None:
        assert exam_verdict(70, 100, 70) is True

    def test_le_seuil_ne_s_arrondit_pas_en_faveur_du_candidat(self) -> None:
        """139/200 = 69,5 %, qu'un arrondi rendrait à 70 : c'est un échec."""
        assert exam_verdict(139, 200, 70) is False
        assert exam_verdict(140, 200, 70) is True

    def test_un_lab_ordinaire_ne_rend_aucun_verdict(self) -> None:
        """None, pas False : « pas un examen » n'est pas « recalé »."""
        assert exam_verdict(0, 100, 0) is None

    def test_un_bareme_nul_ne_vaut_pas_une_reussite(self) -> None:
        assert exam_verdict(0, 0, 70) is False
        assert exam_percentage(0, 0) == 0

    def test_le_seuil_est_lu_depuis_le_lab_yaml(self, tmp_path: Path) -> None:
        (tmp_path / "lab.yaml").write_text(
            LAB_SANS_SECTION.format(id="capstone")
            + "lab_type: capstone\nexam_passing_score: 70\n",
            encoding="utf-8",
        )
        assert LabDefinition.from_yaml(tmp_path / "lab.yaml").exam_passing_score == 70

    def test_un_lab_sans_seuil_vaut_zero(self, tmp_path: Path) -> None:
        (tmp_path / "lab.yaml").write_text(
            LAB_SANS_SECTION.format(id="ordinaire"), encoding="utf-8"
        )
        assert LabDefinition.from_yaml(tmp_path / "lab.yaml").exam_passing_score == 0

    @pytest.mark.parametrize("valeur", [101, -5])
    def test_un_seuil_hors_bornes_est_signale(
        self, tmp_path: Path, valeur: int
    ) -> None:
        """Un pourcentage hors 1..100 décrit un examen impossible à passer."""
        (tmp_path / "lab.yaml").write_text(
            LAB_SANS_SECTION.format(id="capstone")
            + f"exam_passing_score: {valeur}\n",
            encoding="utf-8",
        )
        rapport = validate_metadata(LabDefinition.from_yaml(tmp_path / "lab.yaml"))
        assert [i.field for i in rapport.issues] == ["exam_passing_score"]


# ── #126 : `meta.<lang>.yml`, la traduction par fichier ──────────────────────


class TestTraductionDuMetaYml:
    META = """\
repo:
  id: catalogue-test
  category: demo
  title: Demo catalogue
sections:
  - id: bloc-un
    title: First bloc
  - id: bloc-deux
    title: Second bloc
"""

    def test_sans_fichier_de_traduction_le_meta_yml_gagne(
        self, tmp_path: Path
    ) -> None:
        (tmp_path / "meta.yml").write_text(self.META, encoding="utf-8")
        meta = RepoMetadata.from_yaml(tmp_path / "meta.yml", lang="fr")
        assert meta.sections[0].title == "First bloc"

    def test_les_titres_sont_traduits_dans_la_langue_demandee(
        self, tmp_path: Path
    ) -> None:
        (tmp_path / "meta.yml").write_text(self.META, encoding="utf-8")
        (tmp_path / "meta.fr.yml").write_text(
            "repo:\n  title: Catalogue de démonstration\n"
            "sections:\n  - id: bloc-un\n    title: Premier bloc\n",
            encoding="utf-8",
        )
        meta = RepoMetadata.from_yaml(tmp_path / "meta.yml", lang="fr")
        assert meta.title == "Catalogue de démonstration"
        assert meta.sections[0].title == "Premier bloc"
        # Section non traduite : l'anglais reste, il ne disparaît pas.
        assert meta.sections[1].title == "Second bloc"

    def test_l_anglais_ignore_le_fichier_de_traduction(self, tmp_path: Path) -> None:
        (tmp_path / "meta.yml").write_text(self.META, encoding="utf-8")
        (tmp_path / "meta.fr.yml").write_text(
            "sections:\n  - id: bloc-un\n    title: Premier bloc\n", encoding="utf-8"
        )
        meta = RepoMetadata.from_yaml(tmp_path / "meta.yml", lang="en")
        assert meta.sections[0].title == "First bloc"

    def test_les_sections_sont_appariees_par_id_pas_par_position(
        self, tmp_path: Path
    ) -> None:
        """Une section insérée en tête décalerait sinon toutes les traductions."""
        (tmp_path / "meta.yml").write_text(self.META, encoding="utf-8")
        (tmp_path / "meta.fr.yml").write_text(
            "sections:\n  - id: bloc-deux\n    title: Second bloc en français\n",
            encoding="utf-8",
        )
        meta = RepoMetadata.from_yaml(tmp_path / "meta.yml", lang="fr")
        assert meta.sections[0].title == "First bloc"
        assert meta.sections[1].title == "Second bloc en français"

    def test_une_traduction_illisible_ne_casse_pas_le_catalogue(
        self, tmp_path: Path
    ) -> None:
        (tmp_path / "meta.yml").write_text(self.META, encoding="utf-8")
        (tmp_path / "meta.fr.yml").write_text("repo: [non fermé\n", encoding="utf-8")
        meta = RepoMetadata.from_yaml(tmp_path / "meta.yml", lang="fr")
        assert meta.sections[0].title == "First bloc"


# ── #126 : le garde-fou contre la cinquième clé ──────────────────────────────


class TestClesInconnues:
    def test_un_catalogue_conforme_ne_dit_rien(self, tmp_path: Path) -> None:
        _catalogue(tmp_path)
        _lab(tmp_path, "lab-a")
        assert validate_unknown_keys(tmp_path).ok

    def test_les_quatre_cles_mortes_de_l_issue_sont_vues(
        self, tmp_path: Path
    ) -> None:
        """Les quatre clés réelles, chacune à son niveau du contrat."""
        (tmp_path / "meta.yml").write_text(
            "repo:\n  id: catalogue-test\n  category: demo\n"
            "sections:\n  - id: bloc\n    title: Bloc\n"
            "    title_en: Bloc\n    description_en: A bloc\n",
            encoding="utf-8",
        )
        # `hosts_required` continue le bloc runtime ; la clé racine vient après.
        _lab(
            tmp_path,
            "lab-a",
            extra="  hosts_required: 2\nexam_passing_score_typo: 70\n",
        )

        rapport = validate_unknown_keys(tmp_path)
        assert not rapport.ok
        assert {i.params["field"] for i in rapport.issues} == {
            "sections[].title_en",
            "sections[].description_en",
            "exam_passing_score_typo",
            "runtime.hosts_required",
        }

    def test_la_faute_de_frappe_est_nommee_avec_sa_correction(
        self, tmp_path: Path
    ) -> None:
        _catalogue(tmp_path)
        _lab(tmp_path, "lab-a", extra="skils: [demo]\n")
        anomalie = validate_unknown_keys(tmp_path).issues[0]
        assert anomalie.key == "unknown_key_suggest"
        assert anomalie.params["suggestion"] == "skills"

    def test_la_suggestion_reste_au_meme_niveau(self, tmp_path: Path) -> None:
        """`snapshot_required` n'existe que sous `runtime` : à la racine, pas de piste.

        Proposer `runtime.snapshot_required` à quelqu'un qui a écrit la clé au
        mauvais niveau serait juste ; la proposer sans le dire, avec la même
        phrase qu'une faute de frappe, enverrait sur une fausse piste dès que
        la ressemblance est fortuite. Le contrôle se tait plutôt que d'inventer.
        """
        _catalogue(tmp_path)
        _lab(tmp_path, "lab-a", extra="snapshot_required: true\n")
        anomalie = validate_unknown_keys(tmp_path).issues[0]
        assert anomalie.key == "unknown_key"
        assert anomalie.params["suggestion"] == ""

    def test_les_mappings_libres_du_contrat_restent_libres(
        self, tmp_path: Path
    ) -> None:
        """`roles`, `env` et `infra.providers` appartiennent au catalogue."""
        (tmp_path / "meta.yml").write_text(
            "repo:\n  id: catalogue-test\n  category: demo\n"
            "infra:\n  hosts:\n    - name: a.lab\n"
            "  providers:\n    kvm:\n      storage_pool: pool\n"
            "      nimporte_quoi: 3\n",
            encoding="utf-8",
        )
        _lab(
            tmp_path,
            "lab-a",
            extra=(
                "  targets:\n    - name: t\n      host: a.lab\n"
                "      roles:\n        server: a.lab\n"
                "  services:\n    - name: s\n      image: img:1\n"
                "      env:\n        UN_NOM_LIBRE: valeur\n"
            ),
        )
        assert validate_unknown_keys(tmp_path).ok

    def test_une_traduction_de_lab_ne_peut_porter_que_ses_champs(
        self, tmp_path: Path
    ) -> None:
        """`skills` dans un lab.fr.yaml serait ignoré : c'est le même défaut."""
        _catalogue(tmp_path)
        dossier = _lab(tmp_path, "lab-a")
        (dossier / "lab.fr.yaml").write_text(
            "id: lab-a\ntitle: Titre\ndescription: Desc\nskills: [demo]\n",
            encoding="utf-8",
        )
        rapport = validate_unknown_keys(tmp_path)
        assert [i.params["field"] for i in rapport.issues] == ["skills"]

    def test_une_traduction_de_meta_ne_peut_pas_reordonner(
        self, tmp_path: Path
    ) -> None:
        """`labs:` dans meta.fr.yml serait ignoré : l'ordre vit dans meta.yml."""
        _catalogue(tmp_path)
        (tmp_path / "meta.fr.yml").write_text(
            "sections:\n  - id: bloc\n    title: Bloc\n    labs:\n      - bloc/lab-a\n",
            encoding="utf-8",
        )
        rapport = validate_unknown_keys(tmp_path)
        assert [i.params["field"] for i in rapport.issues] == ["sections[].labs"]

    def test_un_fichier_illisible_n_est_pas_son_sujet(self, tmp_path: Path) -> None:
        """Un YAML cassé est signalé ailleurs ; ici, il n'y a rien à en dire."""
        _catalogue(tmp_path)
        dossier = tmp_path / "labs" / "bloc" / "casse"
        dossier.mkdir(parents=True)
        (dossier / "lab.yaml").write_text("id: [non fermé\n", encoding="utf-8")
        assert validate_unknown_keys(tmp_path).ok


# ── #126 : le verdict arrive jusqu'à l'apprenant ─────────────────────────────
#
# Les tests ci-dessus prouvent le calcul ; ceux-ci prouvent le câblage. Une
# fonction juste que personne n'appelle laisse le défaut d'origine intact.


@pytest.fixture
def anglais(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    """Fige la langue du rendu, que la machine soit francophone ou non.

    `get_lang()` retombe sur `$LANG` : sans ce verrou, ces tests passeraient
    ici et échoueraient sur un poste anglophone, ou l'inverse.
    """
    from dsoxlab.i18n import get_lang, set_lang

    precedent = get_lang()
    monkeypatch.setenv("DSOXLAB_LANG", "en")
    set_lang("en")
    yield
    set_lang(precedent)


@pytest.mark.usefixtures("anglais")
class TestVerdictAffiche:
    def _resultat(self, lab_id: str, score: int) -> dict[str, object]:
        return {
            "lab_id": lab_id,
            "section": "demo",
            "score": score,
            "max_score": 100,
            "passed_tests": 2,
            "total_tests": 5,
            "hints_used": 0,
            "validated_at": "2026-08-21T10:00:00",
        }

    def _rendu(self, resultats: list[dict[str, object]], seuils: dict[str, int]) -> str:
        from dsoxlab.reporting.console import console, print_scores_table

        with console.capture() as capture:
            print_scores_table(resultats, seuils)  # type: ignore[arg-type]
        return " ".join(capture.get().split())

    def test_le_tableau_des_scores_nomme_le_recale(self) -> None:
        rendu = self._rendu([self._resultat("mock-exam", 40)], {"mock-exam": 70})
        assert "Verdict" in rendu
        assert "failed (70%)" in rendu

    def test_le_tableau_des_scores_nomme_celui_qui_est_recu(self) -> None:
        rendu = self._rendu([self._resultat("mock-exam", 85)], {"mock-exam": 70})
        assert "passed (70%)" in rendu

    def test_sans_examen_le_tableau_ne_porte_pas_la_colonne(self) -> None:
        """Un catalogue sans examen n'a pas à afficher une colonne de tirets."""
        rendu = self._rendu([self._resultat("lab-a", 100)], {})
        assert "Verdict" not in rendu

    def test_submit_dit_a_l_apprenant_qu_il_a_echoue(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Le défaut d'origine, vu depuis la commande : 40/100 sans un mot.

        `_run_check` est remplacé pour ne pas lancer pytest : ce qu'on éprouve
        ici est le rendu du verdict, pas la notation, déjà couverte ailleurs.
        """
        from typer.testing import CliRunner

        from dsoxlab import cli
        from dsoxlab.services.lab_service import CheckResult

        _catalogue(tmp_path, category="demo")
        _lab(tmp_path, "mock-exam", extra="exam_passing_score: 70\n")

        monkeypatch.setattr(
            # `_validation` et non `cli` : `progression.submit` importe
            # `_run_check` par son nom, donc poser l'attribut sur le paquet
            # ne l'atteint pas. Le patch était inerte avant 0.1.69, et ces
            # tests passaient sur le vrai résultat (0/100), jamais sur les
            # 40/100 qu'ils annoncent.
            cli._validation,
            "_run_check",
            lambda *a, **k: (CheckResult(False, "", 2, 5), 40, 100),
        )
        resultat = CliRunner().invoke(
            cli.app, ["submit", "mock-exam", "--lab-home", str(tmp_path)]
        )

        assert resultat.exit_code == 0, resultat.output
        sortie = " ".join(resultat.output.split())
        assert "Exam failed" in sortie, sortie
        assert "70%" in sortie, sortie

    def test_submit_reste_muet_sur_un_lab_ordinaire(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Aucun seuil déclaré : pas de verdict, et surtout pas « recalé »."""
        from typer.testing import CliRunner

        from dsoxlab import cli
        from dsoxlab.services.lab_service import CheckResult

        _catalogue(tmp_path, category="demo")
        _lab(tmp_path, "lab-a")

        monkeypatch.setattr(
            cli._validation,
            "_run_check",
            lambda *a, **k: (CheckResult(False, "", 2, 5), 40, 100),
        )
        resultat = CliRunner().invoke(
            cli.app, ["submit", "lab-a", "--lab-home", str(tmp_path)]
        )

        assert resultat.exit_code == 0, resultat.output
        assert "Exam" not in resultat.output, resultat.output
