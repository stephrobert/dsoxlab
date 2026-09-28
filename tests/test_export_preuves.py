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
from typing import ClassVar

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

        assert document["schema"] == "dsoxlab-evidence-v1", (
            "le document se nomme lui-même : il sera lu loin d'ici"
        )
        assert document["producer"]["name"] == "dsoxlab"
        assert document["producer"]["version"]
        assert document["generated_at"].endswith("+00:00"), "UTC, pas l'heure locale"
        assert document["catalog"]["id"]

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

        assert "attempted_at" in ligne
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


class TestLeContratNeBougePasEnSilence:
    """Le document quitte dsoxlab : en changer les clés casse ailleurs.

    Un consommateur — portail de formation, LMS statique, extension d'éditeur,
    outil de suivi local — lit ce document sans rien savoir de nos internes.
    Renommer un champ, en retirer un, ou en ajouter un sans le documenter se
    voit ici, et pas trois semaines plus tard chez quelqu'un d'autre.
    """

    ENVELOPPE: ClassVar[frozenset[str]] = frozenset({
        "schema", "generated_at", "producer", "catalog", "results", "count",
    })
    LIGNE: ClassVar[frozenset[str]] = frozenset({
        "catalog", "lab_id", "lab_type", "section", "validated", "score",
        "max_score", "passed_tests", "total_tests", "hints_used",
        "attempted_at", "exam",
    })

    def test_les_cles_de_l_enveloppe_restent_figees(self, catalogue: Path) -> None:
        assert set(_exporter(catalogue)) == self.ENVELOPPE

    def test_les_cles_d_une_ligne_sont_figees(self, catalogue: Path) -> None:
        record_result(
            catalogue, lab_id="premier", section="domaine", score=100,
            max_score=100, passed_tests=5, total_tests=5, hints_used=0,
        )
        (ligne,) = _exporter(catalogue)["results"]

        assert set(ligne) == self.LIGNE

    def test_le_nom_du_schema_est_le_contrat(self, catalogue: Path) -> None:
        """Une chaîne auto-descriptive, pas un entier.

        `{"schema": 1}` ne dit pas de quoi il est le schéma 1, et ce fichier
        se retrouvera dans un navigateur, un LMS, ou un répertoire de
        téléchargements trois mois plus tard.
        """
        assert _exporter(catalogue)["schema"] == "dsoxlab-evidence-v1"

    def test_aucun_domaine_n_est_code_en_dur(self, catalogue: Path) -> None:
        """Le document ne suppose aucun portail, aucun site, aucun domaine.

        C'est la condition pour qu'un formateur tiers l'utilise : dsoxlab
        produit une preuve, il ne désigne pas qui la consomme.
        """
        brut = json.dumps(_exporter(catalogue))

        assert "http://" not in brut
        assert "https://" not in brut


class TestCeQueLaPreuveNeDoitJamaisPorter:
    """Le modèle de menace, tenu par des tests négatifs.

    Un catalogue est une **entrée non fiable** : `dsoxlab catalog add <url>`
    clone un dépôt git arbitraire. Et ce document est fait pour sortir de la
    machine — vers un portail, un LMS, un fichier qu'on transfère. Les deux
    ensemble imposent une règle simple : la preuve ne transporte que des
    données pédagogiques, construites par **allowlist positive**, jamais par
    sérialisation d'un objet interne dont on retirerait ensuite des clés.

    Ces tests disent ce qui ne doit jamais s'y trouver. Ils échoueront le jour
    où quelqu'un ajoutera un champ « utile pour déboguer ».
    """

    def _document_brut(self, catalogue: Path) -> str:
        record_result(
            catalogue, lab_id="premier", section="domaine", score=100,
            max_score=100, passed_tests=5, total_tests=5, hints_used=0,
        )
        return json.dumps(_exporter(catalogue))

    def test_aucun_chemin_absolu(self, catalogue: Path) -> None:
        """Un chemin publie un nom d'utilisateur, parfois un nom de famille."""
        brut = self._document_brut(catalogue)

        assert str(catalogue) not in brut
        assert "/home/" not in brut
        assert "/Users/" not in brut
        assert "C:\\" not in brut

    def test_aucune_identite_de_machine(self, catalogue: Path) -> None:
        """Ni hostname, ni utilisateur : la preuve décrit un travail, pas un poste."""
        import getpass
        import socket

        brut = self._document_brut(catalogue)

        assert socket.gethostname() not in brut
        assert getpass.getuser() not in brut

    def test_aucune_variable_d_environnement(self, catalogue: Path) -> None:
        """Un environnement complet est un réservoir à secrets."""
        import os

        brut = self._document_brut(catalogue)
        interessantes = [
            v for v in os.environ.values() if len(v) > 12 and "/" not in v
        ]

        for valeur in interessantes[:40]:
            assert valeur not in brut

    def test_aucune_sortie_de_test_brute(self, catalogue: Path) -> None:
        """La sortie de pytest contient des chemins, des noms, parfois des secrets.

        Le document porte des compteurs — combien de tests, combien réussis —
        et jamais le texte qui les a produits.
        """
        document = json.loads(self._document_brut(catalogue))
        (ligne,) = document["results"]

        assert "output" not in ligne
        assert "stdout" not in ligne
        assert "stderr" not in ligne

    def test_rien_de_l_infrastructure(self, catalogue: Path) -> None:
        """Ni provider, ni cible, ni inventaire : un portail n'en a que faire.

        Et ce sont précisément les champs qui désignent des machines et des
        accès.
        """
        document = json.loads(self._document_brut(catalogue))
        (ligne,) = document["results"]

        for interdit in ("provider", "target", "host", "inventory", "ssh"):
            assert interdit not in ligne
            assert interdit not in document["catalog"]
