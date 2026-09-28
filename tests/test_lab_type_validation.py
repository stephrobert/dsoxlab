"""`lab_type: validation` — un lab qui défend un guide ne note personne.

Le contrat distinguait trois formes d'exercice, et toutes trois supposaient un
apprenant qui fait. Une quatrième tournait pourtant en production sans avoir de
nom : une suite d'assertions qui défend les faits publiés par un guide, où un
test rouge signale un guide à rafraîchir et non un apprenant en faute.

Ce fichier tient ce que cette valeur change, et surtout ce qu'elle ne change
pas : les tests tournent exactement comme avant, c'est tout l'objet du lab.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from dsoxlab.models.lab import LabDefinition, ValidationConfig
from dsoxlab.models.runtime import RuntimeConfig, RuntimeType
from dsoxlab.services.lab_service import CheckResult, evaluate_lab
from dsoxlab.services.progress_service import next_pending_lab
from dsoxlab.sessions.store import get_results
from dsoxlab.validators import content, metadata


def _lab(chemin: Path, lab_type: str = "validation", id_: str = "garde-guide") -> LabDefinition:
    return LabDefinition(
        id=id_,
        title="Les faits du guide tiennent-ils encore",
        level="l1",
        path=chemin,
        doc_url="https://example.test/guide",
        runtime=RuntimeConfig(type=RuntimeType.SHELL, workdir="work"),
        skills=["veille"],
        distros=["almalinux10"],
        validation=ValidationConfig(),
        lab_type=lab_type,
    )


class TestLEnumere:
    def test_la_valeur_est_acceptee(self, tmp_path: Path) -> None:
        assert metadata.validate_metadata(_lab(tmp_path)).ok

    def test_une_valeur_inventee_reste_refusee(self, tmp_path: Path) -> None:
        """Étendre l'énuméré ne revient pas à l'ouvrir."""
        rapport = metadata.validate_metadata(_lab(tmp_path, lab_type="tp"))
        assert not rapport.ok
        assert any(i.field == "lab_type" for i in rapport.issues)

    @pytest.mark.parametrize("forme", ["lab", "challenge", "capstone"])
    def test_les_trois_formes_restent_des_exercices(
        self, tmp_path: Path, forme: str
    ) -> None:
        assert _lab(tmp_path, lab_type=forme).is_exercise

    def test_une_validation_n_en_est_pas_un(self, tmp_path: Path) -> None:
        assert not _lab(tmp_path).is_exercise


class TestRienNEstInscrit:
    """Le critère central : la base du dépôt de labs reste vierge."""

    def test_aucune_note_n_entre_en_base(self, tmp_path: Path) -> None:
        """Noter reviendrait à noter le GUIDE, et à le mêler à une progression."""
        lab = _lab(tmp_path)
        resultat = CheckResult(ok=True, passed=5, total=5, output="")

        evaluation = evaluate_lab(tmp_path, lab, resultat)

        assert evaluation.enregistre is False
        assert get_results(tmp_path, lab_id=lab.id) == []

    def test_un_exercice_est_bien_inscrit(self, tmp_path: Path) -> None:
        """Le contre-exemple, sans lequel le test précédent ne prouve rien.

        Un test qui passe parce que la base est vide passerait aussi si rien
        n'était jamais enregistré.
        """
        lab = _lab(tmp_path, lab_type="lab", id_="vrai-exercice")
        resultat = CheckResult(ok=True, passed=5, total=5, output="")

        evaluation = evaluate_lab(tmp_path, lab, resultat)

        assert evaluation.enregistre is True
        assert len(get_results(tmp_path, lab_id=lab.id)) == 1


class TestLaProgressionLIgnore:
    def test_next_ne_le_propose_jamais(self, tmp_path: Path) -> None:
        """Sans ce filtre, il serait proposé indéfiniment.

        Un lab `validation` n'entre jamais dans les scores : `next` le verrait
        donc éternellement comme « pas encore fait », et le proposerait en
        premier à chaque appel.
        """
        garde = _lab(tmp_path, id_="garde-guide")
        exercice = _lab(tmp_path, lab_type="lab", id_="premier-pas")

        assert next_pending_lab([garde, exercice], {}) is exercice

    def test_sans_exercice_il_ne_reste_rien_a_faire(self, tmp_path: Path) -> None:
        assert next_pending_lab([_lab(tmp_path)], {}) is None


class TestLeBaremeNEstPlusExige:
    def test_aucun_bareme_n_est_reclame(self, tmp_path: Path) -> None:
        """Un lab qui ne note personne n'a pas de barème à faire coïncider.

        On lui donne la forme qui ferait échouer un exercice — des tâches
        notées dont le compte ne colle pas au nombre de tests — et le contrôle
        se tait.
        """
        ch = tmp_path / "challenge"
        (ch / "tests").mkdir(parents=True)
        (ch / "README.fr.md").write_text(
            "**Format** : 2 tâches, 100 points.\n\n"
            "### Tâche 1 — un fait du guide (50 pts)\n\n"
            "### Tâche 2 — un autre (50 pts)\n",
            encoding="utf-8",
        )
        (ch / "tests" / "test_functional.py").write_text(
            "def test_a(h): ...\ndef test_b(h): ...\ndef test_c(h): ...\n",
            encoding="utf-8",
        )

        assert content.validate_scoring(_lab(tmp_path)).ok
        # Et le même contenu, déclaré comme exercice, reste refusé.
        assert not content.validate_scoring(_lab(tmp_path, lab_type="lab")).ok
