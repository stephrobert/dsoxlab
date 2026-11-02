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
from dsoxlab.services.progress_service import (
    blocages_de_ligne,
    echecs_de_ligne,
    exam_verdict,
)
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


@pytest.mark.parametrize("valeur", [42, "test_critique", {"a": 1}, 3.5])
def test_une_valeur_malformee_leve_dans_le_contrat(
    tmp_path: Path, valeur: object
) -> None:
    """Un champ malformé doit lever DANS le contrat, jamais ailleurs.

    Le parseur a une promesse : `KeyError`, `ValueError` ou `YAMLError`. Un lab
    dont le `lab.yaml` lève ainsi est sauté avec un avertissement ; tout autre
    type d'exception remonte en trace Python et fait planter la CLI entière.

    Mesuré sur la première écriture de ce champ, qui faisait les deux fautes :
    un `42` levait un `TypeError`, hors contrat, et une chaîne était
    silencieusement éclatée en caractères, ce qui est pire qu'une erreur
    puisque l'exigence devenait une liste de lettres ne bloquant rien.
    """
    import yaml as _yaml

    (tmp_path / "lab.yaml").write_text(_yaml.safe_dump({
        "id": "epreuve", "title": "Épreuve", "level": "c1",
        "exam_blocking_checks": valeur,
    }), encoding="utf-8")
    with pytest.raises((KeyError, ValueError, _yaml.YAMLError)):
        LabDefinition.from_yaml(tmp_path / "lab.yaml")


# ── ce qu'il faut réviser ─────────────────────────────────────────────────

class TestCeQuIlFautReviser:
    """Un verdict exact qui ne nomme rien laisse l'apprenant devant « 3 sur 5 ».

    Le verdict corrigé règle la justesse et pas l'usage : le portail recevait
    un compte, donc il n'avait aucune révision à proposer. Les noms des
    contrôles ratés sont donc consignés, exportés, et transmis.
    """

    def test_les_echecs_sont_consignes_et_relus(self, tmp_path: Path) -> None:
        record_result(
            tmp_path, lab_id="epreuve", section="s", score=60, max_score=100,
            passed_tests=3, total_tests=5, hints_used=0,
            blocking_failed=("test_critique",),
            failed_checks=("test_critique", "test_ordinaire"),
        )
        [ligne] = get_results(tmp_path, lab_id="epreuve")
        assert echecs_de_ligne(ligne) == ("test_critique", "test_ordinaire")
        # LES DEUX LISTES SONT DISTINCTES, et c'est la hiérarchie utile :
        # tout ce qui a raté, puis ce qui refuse l'épreuve.
        assert blocages_de_ligne(ligne) == ("test_critique",)

    def test_l_export_nomme_les_deux_listes(self) -> None:
        rendu = score_dict({
            "lab_id": "epreuve", "section": "s", "score": 60, "max_score": 100,
            "passed_tests": 3, "total_tests": 5, "hints_used": 0,
            "validated_at": "2026-11-02T10:00:00",
            "failed_checks": "test_critique,test_ordinaire",
            "blocking_failed": "test_critique",
        }, 75)
        assert rendu["failed_checks"] == ["test_critique", "test_ordinaire"]
        assert rendu["blocking_failed"] == ["test_critique"]

    def test_une_ligne_sans_echec_ne_nomme_rien(self) -> None:
        rendu = score_dict({
            "lab_id": "epreuve", "section": "s", "score": 100, "max_score": 100,
            "passed_tests": 5, "total_tests": 5, "hints_used": 0,
            "validated_at": "2026-11-02T10:00:00",
        }, 75)
        assert rendu["failed_checks"] == []
        assert rendu["blocking_failed"] == []


# ── la progression ────────────────────────────────────────────────────────

class TestProgression:
    """`progress` ne peut pas dire « validée » ce que `submit` a refusé.

    LE DÉFAUT, mesuré le 2026-11-02 : `challenge_validated` valait « une note
    existe », sans regarder ni la note, ni le seuil, ni le blocage. Un
    apprenant qui soumettait une fois, même à zéro, voyait son épreuve
    déclarée validée pendant que `submit` la refusait.

    Il est antérieur au contrôle bloquant et plus large que lui, mais il le
    contredit frontalement : une fonctionnalité dont une autre commande dit le
    contraire n'est pas livrée.
    """

    @staticmethod
    def _epreuve(racine: Path) -> LabDefinition:
        return LabDefinition(
            id="epreuve", title="Épreuve", level="c1", path=racine,
            skills=["s"], distros=["d"], doc_url="https://exemple.invalid/",
            runtime=RuntimeConfig(type=RuntimeType.SHELL),
            validation=ValidationConfig(), lab_type="challenge",
            exam_passing_score=75, bloc=1,
            exam_blocking_checks=("test_critique",),
        )

    @pytest.mark.parametrize("tentatives,attendu", [
        # LE CAS DU DÉFAUT : une seule tentative, catastrophique.
        ([(0, ("test_critique",))], False),
        # Le cas que le contrôle bloquant existe pour refuser.
        ([(80, ("test_critique",))], False),
        ([(80, ())], True),
        ([(74, ())], False),
        # UNE tentative suffit, et ce n'est pas la meilleure au sens du score :
        # une tentative à 80 avec un blocage ne vaut pas une tentative à 76
        # sans. Et un apprenant qui réussit puis rejoue n'a pas désappris.
        ([(0, ("test_critique",)), (80, ())], True),
        ([(80, ()), (0, ("test_critique",))], True),
    ])
    def test_une_epreuve_n_est_validee_que_si_elle_est_remportee(
        self, tmp_path: Path,
        tentatives: list[tuple[int, tuple[str, ...]]], attendu: bool,
    ) -> None:
        from dsoxlab.services.progress_service import build_progress
        from dsoxlab.sessions.store import get_best_scores, get_exam_outcomes

        lab = self._epreuve(tmp_path)
        for score, bloques in tentatives:
            record_result(
                tmp_path, lab_id="epreuve", section="s", score=score,
                max_score=100, passed_tests=score // 20, total_tests=5,
                hints_used=0, blocking_failed=bloques, failed_checks=bloques,
            )
        issues = get_exam_outcomes(tmp_path, {"epreuve": 75})
        (bloc,) = build_progress(
            [lab], get_best_scores(tmp_path, ["epreuve"]), issues)
        assert bloc.challenge_validated is attendu

    def test_sans_releve_aucune_epreuve_n_est_declaree_remportee(
        self, tmp_path: Path
    ) -> None:
        """L'absence de relevé rend la réponse PRUDENTE, pas l'ancienne.

        Un appelant qui ne fournit rien ne doit pas retomber sur le
        comportement faux qu'on vient de corriger.
        """
        from dsoxlab.services.progress_service import build_progress
        from dsoxlab.sessions.store import get_best_scores

        lab = self._epreuve(tmp_path)
        record_result(
            tmp_path, lab_id="epreuve", section="s", score=100, max_score=100,
            passed_tests=5, total_tests=5, hints_used=0,
        )
        (bloc,) = build_progress([lab], get_best_scores(tmp_path, ["epreuve"]))
        assert bloc.challenge_validated is False

    def test_le_seuil_se_compare_en_entiers_comme_le_verdict(
        self, tmp_path: Path
    ) -> None:
        """Les deux chemins ne doivent pas diverger d'un arrondi.

        `exam_verdict` compare en entiers pour ne pas déclarer reçu à 69,5 %
        un candidat qui ne l'est pas. `get_exam_outcomes` fait la même
        comparaison, et ce test le tient : une divergence d'arrondi ferait
        dire deux choses à deux commandes sur la même tentative.
        """
        from dsoxlab.sessions.store import get_exam_outcomes

        record_result(
            tmp_path, lab_id="epreuve", section="s", score=69, max_score=100,
            passed_tests=3, total_tests=5, hints_used=0,
        )
        assert get_exam_outcomes(tmp_path, {"epreuve": 70}) == {"epreuve": False}
        assert exam_verdict(69, 100, 70) is False


# ── le motif du refus ─────────────────────────────────────────────────────

class TestLeMotifDuRefus:
    """Un refus doit dire POURQUOI, et le vrai pourquoi.

    MESURÉ SUR LA VM avec 0.7.0, `epreuve-reprendre-un-hote-docker` à 80 sur
    un seuil de 75, son seul contrôle bloquant en échec :

        ✘ Un contrôle bloquant a échoué, donc l'épreuve est refusée quel que
          soit le total : test_la_place_est_rendue_et_le_volume_utile_est_intact
        ✘ Examen échoué : 80 % du barème, SOUS LE SEUIL DE 75 %.

    80 n'est pas sous 75. La seconde ligne attribuait le refus au score alors
    que le score était suffisant, et un apprenant qui la lit cherche à gagner
    des points qu'aucun point ne lui rendra.

    C'est la faute que cette version corrige, retournée : le moteur disait
    « reçue » quand il fallait refuser, puis il a refusé en motivant faux.
    """

    @staticmethod
    def _cle(verdict: bool | None, bloques: tuple[str, ...]) -> str:
        """La règle du code, isolée pour être éprouvée sans terminal."""
        if verdict:
            return "exam_passed"
        if bloques:
            return "exam_failed_blocking"
        return "exam_failed"

    def test_un_refus_sur_blocage_ne_parle_pas_du_seuil(self) -> None:
        assert self._cle(False, ("test_critique",)) == "exam_failed_blocking"

    def test_un_refus_sur_le_score_garde_son_message(self) -> None:
        assert self._cle(False, ()) == "exam_failed"

    def test_une_reussite_reste_une_reussite(self) -> None:
        assert self._cle(True, ()) == "exam_passed"

    def test_les_deux_langues_ne_mentionnent_pas_le_seuil_franchi(self) -> None:
        """Le message du blocage ne doit pas invoquer un seuil qui est franchi."""
        from dsoxlab.i18n.strings import en, fr

        for nom, mod in (("en", en), ("fr", fr)):
            texte = mod.STRINGS["exam_failed_blocking"]
            assert "{pct}" in texte and "{threshold}" in texte, nom
            for mensonge in ("below the", "sous le seuil"):
                assert mensonge not in texte, f"{nom} dit « {mensonge} »"

    def test_le_message_du_score_parle_bien_du_seuil(self) -> None:
        """L'AUTRE SENS : la clé du score doit, elle, parler du seuil.

        Sans ce test, vider les deux messages de toute mention du seuil
        passerait le précédent.
        """
        from dsoxlab.i18n.strings import en, fr

        assert "below the" in en.STRINGS["exam_failed"]
        assert "sous le seuil" in fr.STRINGS["exam_failed"]
