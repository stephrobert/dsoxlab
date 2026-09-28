"""`dsoxlab export` — un document que personne n'a à deviner.

Le site affichera ce que l'apprenant a pratiqué et prouvé, sans compte ni
serveur : il exporte depuis sa machine et importe dans son navigateur. Ce
fichier fige le format, parce qu'un document consommé ailleurs ne peut pas
changer de sens sans prévenir.

Quatre choses manquaient à `scores --json`, et chacune obligeait le lecteur à
deviner : le verdict n'était pas explicite, le catalogue n'était pas nommé, le
type du lab était absent, et l'export était tronqué sans le dire.
"""
from __future__ import annotations

import json
from pathlib import Path

from typer.testing import CliRunner

from dsoxlab.cli import app
from dsoxlab.sessions.store import record_result

runner = CliRunner()


def _exporter(catalogue: Path) -> dict:
    resultat = runner.invoke(app, ["export"])
    assert resultat.exit_code == 0, resultat.stdout
    return json.loads(resultat.stdout)


class TestLeDocument:
    def test_il_porte_son_schema_et_sa_provenance(self, catalogue: Path) -> None:
        """Un document lu ailleurs doit dire d'où il vient et ce qu'il est."""
        document = _exporter(catalogue)

        assert document["schema"] == 1
        assert document["tool"]["name"] == "dsoxlab"
        assert document["tool"]["version"]
        assert document["generated_at"].endswith("+00:00"), "UTC, pas l'heure locale"
        assert document["catalog"]["id"]
        assert document["catalog"]["path"] == str(catalogue)

    def test_un_historique_vide_reste_un_document(self, catalogue: Path) -> None:
        """Rien joué n'est pas rien à dire : le consommateur doit pouvoir lire."""
        document = _exporter(catalogue)

        assert document["results"] == []
        assert document["count"] == 0


class TestLeVerdict:
    """Le point central : `validated` est écrit, plus déduit."""

    def test_tous_les_tests_passes_vaut_valide(self, catalogue: Path) -> None:
        record_result(
            catalogue, lab_id="premier", section="domaine", score=100,
            max_score=100, passed_tests=5, total_tests=5, hints_used=0,
        )
        (ligne,) = _exporter(catalogue)["results"]

        assert ligne["validated"] is True

    def test_une_tentative_ratee_est_exportee_et_dite_fausse(
        self, catalogue: Path
    ) -> None:
        """Elle reste dans le document : un échec fait partie de l'historique.

        Et elle se distingue d'un lab jamais tenté, qui est simplement absent.
        """
        record_result(
            catalogue, lab_id="premier", section="domaine", score=40,
            max_score=100, passed_tests=2, total_tests=5, hints_used=0,
        )
        document = _exporter(catalogue)

        (ligne,) = document["results"]
        assert ligne["validated"] is False
        assert ligne["passed_tests"] == 2
        # Le lab jamais tenté du catalogue n'apparaît nulle part.
        assert {r["lab_id"] for r in document["results"]} == {"premier"}

    def test_zero_test_joue_ne_vaut_pas_validation(self, catalogue: Path) -> None:
        """0 sur 0 est vrai arithmétiquement, et faux en pratique.

        Sans cette moitié de la règle, un lab dont rien n'a pu tourner serait
        exporté comme validé.
        """
        record_result(
            catalogue, lab_id="premier", section="domaine", score=0,
            max_score=100, passed_tests=0, total_tests=0, hints_used=0,
        )
        (ligne,) = _exporter(catalogue)["results"]

        assert ligne["validated"] is False


class TestCeQueChaqueLigneDoitPorter:
    def test_le_catalogue_et_le_type_du_lab_sont_joints(self, catalogue: Path) -> None:
        """Sans eux, un site qui fusionne plusieurs catalogues devine.

        Les identifiants sont distincts aujourd'hui, mais aucun contrat ne le
        garantit ; et le type décide si la ligne se range en pratique ou en
        preuve.
        """
        record_result(
            catalogue, lab_id="premier", section="domaine", score=100,
            max_score=100, passed_tests=5, total_tests=5, hints_used=0,
        )
        (ligne,) = _exporter(catalogue)["results"]

        assert ligne["catalog"] == _exporter(catalogue)["catalog"]["id"]
        assert ligne["lab_type"] == "lab"

    def test_un_lab_disparu_garde_son_resultat(self, catalogue: Path) -> None:
        """Le lab a été renommé ou supprimé ; le résultat, lui, a eu lieu."""
        record_result(
            catalogue, lab_id="lab-supprime-depuis", section="domaine", score=100,
            max_score=100, passed_tests=3, total_tests=3, hints_used=0,
        )
        (ligne,) = _exporter(catalogue)["results"]

        assert ligne["lab_id"] == "lab-supprime-depuis"
        assert ligne["lab_type"] is None, "inconnu se dit, il ne s'invente pas"
        assert ligne["validated"] is True

    def test_l_horodatage_ne_prejuge_plus_du_verdict(self, catalogue: Path) -> None:
        """`validated_at` sur une tentative ratée était un contresens."""
        record_result(
            catalogue, lab_id="premier", section="domaine", score=0,
            max_score=100, passed_tests=0, total_tests=4, hints_used=0,
        )
        (ligne,) = _exporter(catalogue)["results"]

        assert "recorded_at" in ligne
        assert "validated_at" not in ligne
        assert ligne["validated"] is False


class TestAucuneTroncature:
    def test_au_dela_de_la_limite_d_affichage(self, catalogue: Path) -> None:
        """`scores` plafonne à 20, la base à 50. Un export ne plafonne pas.

        Un document qui s'arrête sans le dire est pire qu'un document absent :
        celui qui le lit croit tout avoir.
        """
        for i in range(60):
            record_result(
                catalogue, lab_id=f"lab-{i:02d}", section="domaine", score=100,
                max_score=100, passed_tests=1, total_tests=1, hints_used=0,
            )
        document = _exporter(catalogue)

        assert document["count"] == 60
        assert len(document["results"]) == 60
