"""`status: draft` : un lab poussé pour être partagé n'est pas un lab publié (#369).

Avant la 0.9.3, un lab était un brouillon tant qu'il n'était pas poussé, et rien
d'autre ne le disait. Un auteur ne pouvait donc pas publier un lab en cours sur
`main` sans l'exposer dans `list-labs`, dans `next`, dans `progress`, et sans que
ses tentatives partent à l'export et au portail.

Ce fichier tient les deux moitiés du contrat :

- **ce qu'un brouillon quitte** : `list-labs` (sauf `--drafts`), `next`,
  `course` (sauf `--drafts`), `progress`, l'export et `push` ;
- **ce qu'il garde** : `run`, `check`, `submit` et `show` par son identifiant,
  avec une ligne qui dit que c'est un brouillon, et `validate-structure`.

Le catalogue d'essai est celui de `conftest.py` ; `second` y devient brouillon.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from typer.testing import CliRunner

from dsoxlab.cli import app
from dsoxlab.models.lab import LabDefinition, ValidationConfig
from dsoxlab.models.runtime import RuntimeConfig, RuntimeType
from dsoxlab.services.progress_service import next_pending_lab
from dsoxlab.sessions.store import record_result
from dsoxlab.validators import metadata

runner = CliRunner()


def _brouillon(catalogue: Path, ident: str = "second", valeur: str = "draft") -> None:
    lab_yaml = catalogue / "labs" / "domaine" / ident / "lab.yaml"
    lab_yaml.write_text(
        lab_yaml.read_text(encoding="utf-8") + f"status: {valeur}\n", encoding="utf-8"
    )


def _tentative(catalogue: Path, lab_id: str) -> None:
    record_result(
        catalogue, lab_id=lab_id, section="domaine", score=80, max_score=100,
        passed_tests=4, total_tests=5, hints_used=0,
    )


def _lab(chemin: Path, ident: str, status: str = "published") -> LabDefinition:
    return LabDefinition(
        id=ident, title=ident, level="l1", path=chemin,
        doc_url="https://exemple.test/guide",
        runtime=RuntimeConfig(type=RuntimeType.SHELL, workdir="work"),
        skills=["x"], distros=["alma10"], validation=ValidationConfig(),
        status=status,
    )


def _json(sortie: str) -> Any:
    return json.loads(sortie)


# ── le champ, lu par le parseur ──────────────────────────────────────────────


class TestLeChamp:
    def test_absent_il_vaut_published(self, catalogue: Path) -> None:
        """Aucun catalogue existant ne change : le défaut publie."""
        lab = LabDefinition.from_yaml(catalogue / "labs/domaine/premier/lab.yaml")
        assert lab.status == "published" and not lab.is_draft

    def test_draft_est_lu(self, catalogue: Path) -> None:
        _brouillon(catalogue)
        lab = LabDefinition.from_yaml(catalogue / "labs/domaine/second/lab.yaml")
        assert lab.status == "draft" and lab.is_draft

    def test_une_valeur_inconnue_est_toleree_puis_signalee(self, catalogue: Path) -> None:
        """Même politique que `feedback` : gardée telle quelle, signalée par
        `validate-structure`, et sans effet (le lab reste publié)."""
        _brouillon(catalogue, valeur="drfat")
        lab = LabDefinition.from_yaml(catalogue / "labs/domaine/second/lab.yaml")
        assert lab.status == "drfat" and not lab.is_draft
        rapport = metadata.validate_metadata(lab)
        assert [i.field for i in rapport.issues] == ["status"]

    def test_une_valeur_malformee_ne_leve_pas_hors_contrat(self, catalogue: Path) -> None:
        """Une liste ne doit lever ni TypeError ni rien qui sorte du contrat du
        parseur : elle est mise en chaîne, et signalée comme une valeur inconnue."""
        _brouillon(catalogue, valeur="[draft, published]")
        lab = LabDefinition.from_yaml(catalogue / "labs/domaine/second/lab.yaml")
        assert not lab.is_draft
        assert not metadata.validate_metadata(lab).ok

    def test_un_brouillon_se_valide_comme_les_autres(self, tmp_path: Path) -> None:
        assert metadata.validate_metadata(_lab(tmp_path, "b", status="draft")).ok

    def test_validate_structure_passe_sur_un_brouillon(self, catalogue: Path) -> None:
        """La clé est connue du lint des clés hors contrat, et le brouillon est
        validé, pas sauté."""
        _brouillon(catalogue)
        resultat = runner.invoke(app, ["validate-structure", "--json"])
        assert resultat.exit_code == 0, resultat.stdout
        document = _json(resultat.stdout)
        assert document["labs_checked"] == 2
        assert document["counts"]["unknown_key"] == 0

    def test_validate_structure_signale_une_valeur_inconnue(self, catalogue: Path) -> None:
        _brouillon(catalogue, valeur="brouillon")
        resultat = runner.invoke(app, ["validate-structure", "--json"])
        assert resultat.exit_code == 1
        assert _json(resultat.stdout)["counts"]["metadata"] == 1


# ── ce qu'un brouillon quitte ────────────────────────────────────────────────


class TestListLabs:
    def test_un_brouillon_n_est_pas_liste(self, catalogue: Path) -> None:
        _brouillon(catalogue)
        document = _json(runner.invoke(app, ["list-labs", "--json"]).stdout)
        assert [lab["id"] for lab in document["labs"]] == ["premier"]

    def test_drafts_le_montre_avec_son_etat(self, catalogue: Path) -> None:
        _brouillon(catalogue)
        document = _json(runner.invoke(app, ["list-labs", "--json", "--drafts"]).stdout)
        etats = {lab["id"]: lab["status"] for lab in document["labs"]}
        assert etats == {"premier": "published", "second": "draft"}

    def test_la_ligne_d_un_brouillon_porte_sa_marque(self, tmp_path: Path) -> None:
        """Le titre porte la marque traduite ; un lab publié n'en porte aucune."""
        from dsoxlab.i18n import _
        from dsoxlab.reporting.console import _titre_de_ligne

        assert _("lab_brouillon_marque") in _titre_de_ligne(_lab(tmp_path, "b", "draft"))
        assert _("lab_brouillon_marque") not in _titre_de_ligne(_lab(tmp_path, "p"))


class TestNextProgressPush:
    """Le critère d'acceptation de l'issue, tenu sur les trois commandes."""

    def test_next_ne_propose_jamais_un_lab_brouillon(self, tmp_path: Path) -> None:
        brouillon = _lab(tmp_path, "brouillon", status="draft")
        publie = _lab(tmp_path, "publie")
        assert next_pending_lab([brouillon, publie], {}) is publie
        assert next_pending_lab([brouillon], {}) is None

    def test_next_en_cli_ne_le_compte_pas_restant(self, catalogue: Path) -> None:
        _brouillon(catalogue)
        _tentative(catalogue, "premier")
        document = _json(runner.invoke(app, ["next", "--json"]).stdout)
        assert document["next"] is None
        assert document["remaining"] == 0
        assert document["all_done"] is True

    def test_progress_ne_compte_jamais_un_brouillon(self, catalogue: Path) -> None:
        _brouillon(catalogue)
        _tentative(catalogue, "second")
        document = _json(runner.invoke(app, ["progress", "--json"]).stdout)
        assert [lab["id"] for lab in document["labs"]] == ["premier"]
        assert document["summary"] == {
            "total": 1, "attempted": 0, "points": 0, "max_points": 0,
        }

    def test_push_n_envoie_pas_les_tentatives_d_un_brouillon(
        self, catalogue: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from dsoxlab.cli import compte
        from dsoxlab.services import sync_service

        _brouillon(catalogue)
        _tentative(catalogue, "premier")
        _tentative(catalogue, "second")
        envoyes: list[dict[str, Any]] = []

        def pousser(portail: object, document: dict[str, Any]) -> sync_service.Envoi:
            envoyes.append(document)
            return sync_service.Envoi(
                ajoutees=document["count"], doublons=0, ecartees={},
                revision=1, rejoue=False, total=document["count"],
            )

        monkeypatch.setattr(compte, "_portail", lambda root: object())
        monkeypatch.setattr(sync_service, "pousser", pousser)

        resultat = runner.invoke(app, ["push"])

        assert resultat.exit_code == 0, resultat.stdout
        assert [ligne["lab_id"] for ligne in envoyes[0]["results"]] == ["premier"]


class TestExport:
    def test_l_export_complet_ecarte_un_brouillon(self, catalogue: Path) -> None:
        _brouillon(catalogue)
        _tentative(catalogue, "premier")
        _tentative(catalogue, "second")
        document = _json(runner.invoke(app, ["export"]).stdout)
        assert [ligne["lab_id"] for ligne in document["results"]] == ["premier"]

    def test_une_preuve_de_brouillon_est_bien_refusee(self, catalogue: Path) -> None:
        _brouillon(catalogue)
        _tentative(catalogue, "second")
        resultat = runner.invoke(app, ["export", "--lab", "second"])
        assert resultat.exit_code == 1
        assert resultat.stdout == ""


class TestCourse:
    def test_course_refuse_un_brouillon(self, catalogue: Path) -> None:
        _brouillon(catalogue)
        resultat = runner.invoke(app, ["course", "second", "--no-pager"])
        assert resultat.exit_code == 1

    def test_drafts_ouvre_le_cours_a_son_auteur(self, catalogue: Path) -> None:
        _brouillon(catalogue)
        resultat = runner.invoke(app, ["course", "second", "--drafts", "--no-pager"])
        assert resultat.exit_code == 0, resultat.stdout


# ── ce qu'un brouillon garde ─────────────────────────────────────────────────


@pytest.fixture
def lignes_dites(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    """Les lignes que `_dire_si_brouillon` émet, sur stdout comme sur stderr.

    On capture l'appel plutôt que de lire le rendu Rich, qui coupe les lignes
    longues à la largeur du terminal de test."""
    from dsoxlab.cli import _commun

    dites: list[str] = []
    monkeypatch.setattr(_commun, "info", dites.append)
    monkeypatch.setattr(_commun, "note", dites.append)
    return dites


def _dit_brouillon(dites: list[str]) -> bool:
    return any("second" in ligne and "status: draft" in ligne for ligne in dites)


class TestJouableParSonIdentifiant:
    def test_show_le_montre_en_le_disant(
        self, catalogue: Path, lignes_dites: list[str]
    ) -> None:
        _brouillon(catalogue)
        resultat = runner.invoke(app, ["show", "second"])
        assert resultat.exit_code == 0, resultat.stdout
        assert _dit_brouillon(lignes_dites)

    def test_show_json_porte_l_etat(self, catalogue: Path) -> None:
        _brouillon(catalogue)
        document = _json(runner.invoke(app, ["show", "second", "--json"]).stdout)
        assert document["lab"]["status"] == "draft"

    def test_check_le_joue_en_le_disant(
        self, catalogue: Path, lignes_dites: list[str]
    ) -> None:
        _brouillon(catalogue)
        resultat = runner.invoke(app, ["check", "second", "--json"])
        assert resultat.exit_code == 0, resultat.stdout
        assert _json(resultat.stdout)["lab"]["id"] == "second"
        assert _dit_brouillon(lignes_dites)

    def test_submit_le_joue_en_le_disant(
        self, catalogue: Path, lignes_dites: list[str]
    ) -> None:
        _brouillon(catalogue)
        resultat = runner.invoke(app, ["submit", "second"])
        assert resultat.exit_code == 0, resultat.stdout
        assert _dit_brouillon(lignes_dites)

    def test_run_le_demarre_en_le_disant(
        self, catalogue: Path, lignes_dites: list[str], monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from dsoxlab.cli import parcours

        _brouillon(catalogue)
        monkeypatch.setattr(parcours, "open_lab_session", lambda lab: None)
        resultat = runner.invoke(app, ["run", "second"])
        assert resultat.exit_code == 0, resultat.stdout
        assert _dit_brouillon(lignes_dites)

    def test_un_lab_publie_ne_dit_rien(
        self, catalogue: Path, lignes_dites: list[str]
    ) -> None:
        """Le contre-exemple : sans lui, les tests du dessus passeraient sur un
        message affiché pour tous les labs."""
        assert runner.invoke(app, ["show", "premier"]).exit_code == 0
        assert not any("status: draft" in ligne for ligne in lignes_dites)

    def test_scores_garde_l_historique_local(self, catalogue: Path) -> None:
        """Décision : `scores` est l'historique de ce qui a été joué SUR CETTE
        machine, et rien n'en sort. Une tentative de brouillon y reste visible :
        la cacher masquerait une note réellement inscrite."""
        _brouillon(catalogue)
        _tentative(catalogue, "second")
        document = _json(runner.invoke(app, ["scores", "--json"]).stdout)
        assert [r["lab_id"] for r in document["results"]] == ["second"]
