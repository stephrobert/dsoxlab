"""Un seuil de réussite n'a de sens que sur un lab qui évalue.

Le défaut qui a motivé ce fichier venait d'ailleurs : quatre labs de
`devsecops-dsoxlab-training` servaient d'épreuve à un niveau de parcours en
étant déclarés `lab_type: lab`. Ce cas-là ne se voit PAS depuis le catalogue,
parce que rien dans un `lab.yaml` ne dit qu'un lab clôt un niveau : la
déclaration vit dans le parcours, donc en aval, et le contrôle qui l'a trouvé
est à sa place là-bas.

Ce que l'audit a mis au jour en revanche, c'est une contradiction que le
catalogue porte seul et que personne ne contrôlait : `exam_passing_score` sur
une forme qui n'évalue pas. Les 424 labs des 22 catalogues la respectaient
déjà (21 barèmes, tous sur un `challenge` ou un `capstone`), ce qui est
exactement le bon moment pour la rendre opposable : aucune dette à solder, et
une porte fermée.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from dsoxlab.models.lab import LabDefinition, ValidationConfig
from dsoxlab.models.runtime import RuntimeConfig, RuntimeType
from dsoxlab.validators import metadata


def _lab(chemin: Path, lab_type: str, score: int | None = None) -> LabDefinition:
    return LabDefinition(
        id="epreuve-de-niveau",
        title="Durcir le pipeline de bout en bout",
        level="d4",
        path=chemin,
        doc_url="https://example.test/guide",
        runtime=RuntimeConfig(type=RuntimeType.SHELL, workdir="work"),
        skills=["pipeline"],
        distros=["almalinux10"],
        validation=ValidationConfig(),
        lab_type=lab_type,
        exam_passing_score=score,
    )


def _ecarts(rapport: metadata.MetadataReport) -> list[str]:
    return [i.key for i in rapport.issues]


class TestLeBaremeSupposeUneEpreuve:
    @pytest.mark.parametrize("forme", ["challenge", "capstone"])
    def test_les_deux_formes_qui_evaluent_portent_un_bareme(
        self, tmp_path: Path, forme: str
    ) -> None:
        assert metadata.validate_metadata(_lab(tmp_path, forme, score=70)).ok

    @pytest.mark.parametrize("forme", ["lab", "validation"])
    def test_une_forme_qui_n_evalue_pas_le_refuse(
        self, tmp_path: Path, forme: str
    ) -> None:
        """Le cas qui doit mordre : les deux lectures du fichier divergeaient."""
        rapport = metadata.validate_metadata(_lab(tmp_path, forme, score=70))

        assert not rapport.ok
        assert "metadata_exam_score_sans_epreuve" in _ecarts(rapport)
        assert any(i.field == "lab_type" for i in rapport.issues)

    @pytest.mark.parametrize("forme", ["lab", "challenge", "capstone", "validation"])
    def test_sans_bareme_aucune_forme_n_est_inquietee(
        self, tmp_path: Path, forme: str
    ) -> None:
        """Le champ est optionnel : son absence n'est pas une contradiction."""
        assert metadata.validate_metadata(_lab(tmp_path, forme)).ok

    def test_le_message_nomme_la_sortie_et_non_seulement_la_faute(
        self, tmp_path: Path
    ) -> None:
        """Un contrôle qui ne dit pas quoi faire se contourne en retirant le champ."""
        rapport = metadata.validate_metadata(_lab(tmp_path, "lab", score=70))
        faute = next(
            i for i in rapport.issues if i.key == "metadata_exam_score_sans_epreuve"
        )

        assert faute.params["score"] == 70
        assert faute.params["value"] == "lab"
        assert "challenge" in faute.params["expected"]
        assert "capstone" in faute.params["expected"]

    def test_un_bareme_hors_bornes_reste_signale_pour_lui_meme(
        self, tmp_path: Path
    ) -> None:
        """Les deux contrôles sont distincts : 0 n'est pas « pas un examen »."""
        rapport = metadata.validate_metadata(_lab(tmp_path, "capstone", score=150))

        assert "metadata_exam_score_invalid" in _ecarts(rapport)
        assert "metadata_exam_score_sans_epreuve" not in _ecarts(rapport)

    @pytest.mark.parametrize("valeur", [101, -5])
    def test_un_bareme_absurde_ne_vaut_pas_deux_messages(
        self, tmp_path: Path, valeur: int
    ) -> None:
        """Les deux contrôles sont exclusifs : la forme d'une valeur qui n'a pas
        de sens ne se discute pas, sinon une ligne fautive en rend deux."""
        rapport = metadata.validate_metadata(_lab(tmp_path, "lab", score=valeur))

        assert [i.field for i in rapport.issues] == ["exam_passing_score"]
