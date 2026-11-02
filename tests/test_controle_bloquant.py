"""Le contrôle bloquant : une exigence qu'aucun total ne compense.

CE QUE CES TESTS DÉFENDENT, et pourquoi ils existent.

Les épreuves des catalogues annoncent, dans leur scénario comme sur les pages
qui les présentent, une exigence « critique » que la moyenne ne rachète pas :
perdre la donnée, laisser fuiter le secret, couper l'accès. Mesuré le
2026-11-02, le moteur ne connaissait pas cette notion, et l'arithmétique
disait le contraire de la promesse :

    compute_score(passed=4, total=5, max_score=100, hints_cost=0) = 80
    exam_verdict(80, 100, 75)                                     = True

Une épreuve dont SEUL le contrôle critique échouait était donc **reçue**. Le
défaut ne se voyait jamais par hasard : il fallait faire échouer exactement ce
contrôle-là, et rien d'autre.

CHAQUE TEST EST JOUÉ DANS LES DEUX SENS. Un garde-fou qui ne rougit pas quand
il doit rougir ne mesure rien : pour chaque règle, on vérifie le refus ET
l'acceptation, sur des entrées qui ne diffèrent que par le fait contrôlé.
"""

from __future__ import annotations

import ast
import sqlite3
from pathlib import Path
from typing import ClassVar

import pytest

from dsoxlab.models.lab import (
    LabDefinition,
    RuntimeConfig,
    RuntimeType,
    ValidationConfig,
)
from dsoxlab.reporting.machine import score_dict
from dsoxlab.services.lab_service import CheckResult, blocages_rates
from dsoxlab.services.progress_service import blocages_de_ligne, exam_verdict
from dsoxlab.sessions.store import get_results, record_result
from dsoxlab.validators.metadata import validate_metadata

# ── le verdict ────────────────────────────────────────────────────────────

class TestVerdict:
    """``exam_verdict`` refuse une épreuve dont un contrôle bloquant a échoué."""

    def test_sans_blocage_le_seuil_decide_comme_avant(self) -> None:
        assert exam_verdict(80, 100, 75) is True
        assert exam_verdict(74, 100, 75) is False

    def test_un_blocage_refuse_une_note_au_dessus_du_seuil(self) -> None:
        """LE CAS EXACT DU DÉFAUT : quatre contrôles sur cinq, seuil à 75."""
        assert exam_verdict(80, 100, 75) is True
        assert exam_verdict(80, 100, 75, ("test_critique",)) is False

    def test_un_total_parfait_ne_rachete_pas_un_blocage(self) -> None:
        """Le refus vient AVANT le seuil, parce qu'il ne se discute pas."""
        assert exam_verdict(100, 100, 75, ("test_critique",)) is False

    def test_un_lab_sans_seuil_ne_se_prononce_toujours_pas(self) -> None:
        """``None`` n'est pas un échec, et un blocage ne doit pas le changer.

        Un lab ordinaire n'est pas un examen : lui faire dire « recalé » parce
        qu'un test porte un nom déclaré ailleurs serait pire que le défaut
        qu'on corrige.
        """
        assert exam_verdict(80, 100, 0, ("test_critique",)) is None

    def test_plusieurs_blocages_refusent_aussi(self) -> None:
        assert exam_verdict(90, 100, 75, ("a", "b")) is False


# ── la règle, écrite une seule fois ───────────────────────────────────────

def _lab(tmp_path: Path, bloquants: tuple[str, ...]) -> LabDefinition:
    """Un lab minimal qui déclare ``bloquants`` comme contrôles critiques."""
    return LabDefinition(
        id="epreuve",
        title="Épreuve",
        level="c1",
        path=tmp_path,
        skills=["s"], distros=["d"], doc_url="https://exemple.invalid/",
        runtime=RuntimeConfig(type=RuntimeType.SHELL),
        validation=ValidationConfig(),
        exam_passing_score=75,
        exam_blocking_checks=bloquants,
    )


def _sortie_pytest(*rates: str) -> str:
    """Une sortie pytest dont ``rates`` sont les tests en échec."""
    lignes = [f"challenge/tests/test_functional.py::{nom} FAILED" for nom in rates]
    return "\n".join(lignes) + "\n= short test summary info =\n" + "\n".join(
        f"FAILED challenge/tests/test_functional.py::{nom}" for nom in rates
    )


class TestRegleDuCroisement:
    """``blocages_rates`` croise les échecs de pytest et le contrat du lab."""

    def test_un_bloquant_rate_est_vu(self, tmp_path: Path) -> None:
        lab = _lab(tmp_path, ("test_critique",))
        result = CheckResult(
            ok=False, output=_sortie_pytest("test_critique"), passed=4, total=5)
        assert blocages_rates(lab, result) == ("test_critique",)

    def test_un_autre_test_rate_ne_bloque_pas(self, tmp_path: Path) -> None:
        """L'AUTRE SENS, et c'est lui qui compte : un échec ordinaire reste
        ordinaire. Sans ce test, une règle qui bloquerait sur n'importe quel
        échec passerait le test précédent sans qu'on s'en aperçoive."""
        lab = _lab(tmp_path, ("test_critique",))
        result = CheckResult(
            ok=False, output=_sortie_pytest("test_ordinaire"), passed=4, total=5)
        assert blocages_rates(lab, result) == ()

    def test_un_lab_qui_ne_declare_rien_ne_bloque_jamais(self, tmp_path: Path) -> None:
        lab = _lab(tmp_path, ())
        result = CheckResult(
            ok=False, output=_sortie_pytest("test_critique"), passed=4, total=5)
        assert blocages_rates(lab, result) == ()

    def test_l_ordre_suit_le_contrat_et_non_la_sortie(self, tmp_path: Path) -> None:
        """Le message doit être stable d'une exécution à l'autre."""
        lab = _lab(tmp_path, ("test_a", "test_b"))
        result = CheckResult(
            ok=False, output=_sortie_pytest("test_b", "test_a"), passed=3, total=5)
        assert blocages_rates(lab, result) == ("test_a", "test_b")


# ── la persistance ────────────────────────────────────────────────────────

class TestPersistance:
    """Sans colonne, ``submit`` dirait « recalé » et ``scores`` « reçu »."""

    def test_la_colonne_est_relue_telle_qu_elle_a_ete_ecrite(
        self, tmp_path: Path
    ) -> None:
        record_result(
            tmp_path, lab_id="epreuve", section="s", score=80, max_score=100,
            passed_tests=4, total_tests=5, hints_used=0,
            blocking_failed=("test_critique",),
        )
        [ligne] = get_results(tmp_path, lab_id="epreuve")
        assert blocages_de_ligne(ligne) == ("test_critique",)

    def test_une_tentative_sans_blocage_n_en_invente_pas(self, tmp_path: Path) -> None:
        record_result(
            tmp_path, lab_id="epreuve", section="s", score=80, max_score=100,
            passed_tests=4, total_tests=5, hints_used=0,
        )
        [ligne] = get_results(tmp_path, lab_id="epreuve")
        assert blocages_de_ligne(ligne) == ()

    def test_une_base_anterieure_recoit_la_colonne_sans_perdre_ses_lignes(
        self, tmp_path: Path
    ) -> None:
        """LA MIGRATION, et c'est le cas qui casse chez quelqu'un d'autre.

        ``CREATE TABLE IF NOT EXISTS`` ne touche pas une table présente : une
        base créée avant l'ajout de la colonne ne l'aurait jamais, et toute
        écriture lèverait `no such column` sur la machine de quelqu'un qui
        joue des labs depuis des mois.

        On fabrique donc une base à l'ANCIEN schéma, à la main, et on vérifie
        que l'ouverture la migre sans perdre la ligne qu'elle portait.
        """
        base = tmp_path / ".dsoxlab.db"
        conn = sqlite3.connect(base)
        conn.executescript("""
            CREATE TABLE results (
                id            INTEGER PRIMARY KEY AUTOINCREMENT,
                lab_id        TEXT    NOT NULL,
                section       TEXT    NOT NULL,
                validated_at  TEXT    NOT NULL,
                score         INTEGER NOT NULL,
                max_score     INTEGER NOT NULL,
                passed_tests  INTEGER NOT NULL,
                total_tests   INTEGER NOT NULL,
                hints_used    INTEGER NOT NULL
            );
            INSERT INTO results
              (lab_id, section, validated_at, score, max_score,
               passed_tests, total_tests, hints_used)
              VALUES ('ancien', 's', '2026-01-01T00:00:00', 60, 100, 3, 5, 0);
        """)
        conn.commit()
        conn.close()

        # L'ouverture migre, et la ligne d'avant survit.
        anciennes = get_results(tmp_path, lab_id="ancien")
        assert len(anciennes) == 1
        assert anciennes[0]["score"] == 60
        # Elle ne porte aucun blocage : on ne SAIT pas, et deviner ferait
        # passer pour recalée une tentative qui ne l'a jamais été.
        assert blocages_de_ligne(anciennes[0]) == ()

        # Et l'écriture neuve fonctionne sur cette même base.
        record_result(
            tmp_path, lab_id="neuve", section="s", score=80, max_score=100,
            passed_tests=4, total_tests=5, hints_used=0,
            blocking_failed=("test_critique",),
        )
        [neuve] = get_results(tmp_path, lab_id="neuve")
        assert blocages_de_ligne(neuve) == ("test_critique",)


class TestLecteurDeColonne:
    """``blocages_de_ligne`` ne doit jamais lever sur une ligne incomplète."""

    @pytest.mark.parametrize("ligne,attendu", [
        ({}, ()),
        ({"blocking_failed": None}, ()),
        ({"blocking_failed": ""}, ()),
        ({"blocking_failed": "a"}, ("a",)),
        ({"blocking_failed": "a,b"}, ("a", "b")),
        ({"blocking_failed": "a,,b"}, ("a", "b")),
    ])
    def test_formes_de_la_colonne(
        self, ligne: dict[str, object], attendu: tuple[str, ...]
    ) -> None:
        assert blocages_de_ligne(ligne) == attendu


# ── l'export ──────────────────────────────────────────────────────────────

class TestExport:
    """Le JSON doit dire la même chose que ``submit``, sinon à quoi bon."""

    LIGNE: ClassVar[dict[str, object]] = {
        "lab_id": "epreuve", "section": "s", "score": 80, "max_score": 100,
        "passed_tests": 4, "total_tests": 5, "hints_used": 0,
        "validated_at": "2026-11-02T10:00:00",
    }

    def test_sans_blocage_le_json_dit_recu(self) -> None:
        assert score_dict(dict(self.LIGNE), 75)["exam"]["passed"] is True

    def test_avec_blocage_le_json_dit_recale_a_score_egal(self) -> None:
        rendu = score_dict({**self.LIGNE, "blocking_failed": "test_critique"}, 75)
        assert rendu["exam"]["passed"] is False
        # LE SCORE NE BOUGE PAS. Le refus est un verdict, pas une pénalité :
        # mentir sur la note pour forcer le verdict rendrait les deux faux.
        assert rendu["score"] == 80


# ── le validateur ─────────────────────────────────────────────────────────

def _ecrire_lab(racine: Path, *, tests: str, bloquants: list[str],
                lab_type: str = "challenge") -> LabDefinition:
    (racine / "challenge/tests").mkdir(parents=True, exist_ok=True)
    (racine / "challenge/tests/test_functional.py").write_text(tests, encoding="utf-8")
    return LabDefinition(
        id="epreuve", title="Épreuve", level="c1", path=racine,
        runtime=RuntimeConfig(type=RuntimeType.SHELL),
        validation=ValidationConfig(),
        skills=["s"], distros=["d"], doc_url="https://exemple.invalid/",
        lab_type=lab_type, exam_passing_score=75,
        exam_blocking_checks=tuple(bloquants),
    )


class TestValidateur:
    """La forme déclarative a deux faiblesses, et le validateur les ferme."""

    def test_un_nom_qui_existe_passe(self, tmp_path: Path) -> None:
        lab = _ecrire_lab(
            tmp_path, tests="def test_critique():\n    pass\n",
            bloquants=["test_critique"])
        codes = [i.key for i in validate_metadata(lab).issues]
        assert "metadata_blocking_check_inconnu" not in codes

    def test_un_nom_qui_n_existe_pas_est_refuse(self, tmp_path: Path) -> None:
        """LE RENOMMAGE SILENCIEUX, qui ramènerait le défaut par la porte de
        derrière : le `lab.yaml` nomme un test, le test est renommé, et
        l'exigence cesse de bloquer sans que personne ne l'ait décidé."""
        lab = _ecrire_lab(
            tmp_path, tests="def test_renomme():\n    pass\n",
            bloquants=["test_critique"])
        codes = [i.key for i in validate_metadata(lab).issues]
        assert "metadata_blocking_check_inconnu" in codes

    def test_une_exigence_bloquante_sur_un_lab_qui_n_evalue_pas(
        self, tmp_path: Path
    ) -> None:
        lab = _ecrire_lab(
            tmp_path, tests="def test_critique():\n    pass\n",
            bloquants=["test_critique"], lab_type="lab")
        codes = [i.key for i in validate_metadata(lab).issues]
        assert "metadata_blocking_sans_epreuve" in codes

    def test_la_meme_exigence_sur_une_epreuve_ne_dit_rien(
        self, tmp_path: Path
    ) -> None:
        lab = _ecrire_lab(
            tmp_path, tests="def test_critique():\n    pass\n",
            bloquants=["test_critique"], lab_type="capstone")
        codes = [i.key for i in validate_metadata(lab).issues]
        assert "metadata_blocking_sans_epreuve" not in codes


# ── le contrat ────────────────────────────────────────────────────────────

def test_le_champ_est_lu_depuis_le_lab_yaml(tmp_path: Path) -> None:
    """Déclaré dans le fichier, il doit arriver jusqu'au modèle."""
    import yaml

    (tmp_path / "lab.yaml").write_text(yaml.safe_dump({
        "id": "epreuve", "title": "Épreuve", "level": "c1",
        "lab_type": "challenge", "exam_passing_score": 75,
        "exam_blocking_checks": ["test_critique", "test_autre"],
    }), encoding="utf-8")
    lab = LabDefinition.from_yaml(tmp_path / "lab.yaml")
    assert lab.exam_blocking_checks == ("test_critique", "test_autre")


def test_un_lab_yaml_sans_le_champ_rend_un_tuple_vide(tmp_path: Path) -> None:
    import yaml

    (tmp_path / "lab.yaml").write_text(yaml.safe_dump({
        "id": "lab", "title": "Lab", "level": "c1",
    }), encoding="utf-8")
    assert LabDefinition.from_yaml(tmp_path / "lab.yaml").exam_blocking_checks == ()


def test_la_regle_du_croisement_n_est_ecrite_qu_une_fois() -> None:
    """Deux copies de cette règle divergeraient, et c'est le défaut d'origine.

    ``evaluate_lab`` l'inscrit, ``submit`` l'affiche : les deux doivent appeler
    la MÊME fonction. Une seconde copie passerait tous les tests ci-dessus le
    jour où elle est écrite, et mentirait le jour où l'une des deux change.
    """
    racine = Path(__file__).resolve().parents[1] / "src/dsoxlab"
    coupables = []
    for fichier in racine.rglob("*.py"):
        if "i18n/strings" in str(fichier):
            continue
        source = fichier.read_text(encoding="utf-8")
        if "exam_blocking_checks" not in source:
            continue
        arbre = ast.parse(source)
        # La règle, c'est l'itération sur `lab.exam_blocking_checks`. Le modèle
        # qui le déclare et le validateur qui le contrôle ne comptent pas.
        for noeud in ast.walk(arbre):
            if not isinstance(noeud, ast.GeneratorExp | ast.ListComp):
                continue
            rendu = ast.dump(noeud)
            if "exam_blocking_checks" in rendu and "rates" in rendu:
                coupables.append(str(fichier.relative_to(racine)))
    assert coupables == ["services/lab_service.py"], (
        "la règle du croisement doit vivre dans un seul fichier, et elle est "
        f"dans : {coupables}"
    )
