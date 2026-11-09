"""Le contrat auteur `criteria:` / `feedback:` et la politique d'affichage de `check`.

Lot D de l'issue #336 (0.8.0), décision du propriétaire : un lab montre tout, un
défi montre la première ligne du message de l'auteur, une épreuve ne dit que le
verdict. Un critère qui n'a pas pu être évalué se dit comme tel.

TROIS GARANTIES, jouées dans les deux sens :

1. **Rien ne change pour un `lab`.** La sortie de `check` d'un catalogue factice
   sans `criteria:` ni `feedback:` est identique, octet pour octet, à celle de
   0.7.3. Les deux références de `tests/references/` ont été capturées en
   exécutant le code de 0.7.3 lui-même (`git archive 36df86c`), pas celui-ci. Le
   catalogue est tout `shell`, sans bloc `infra:`, à la façon de terraform : le
   contre-exemple qui attrape les régressions d'agnosticisme.
2. **`first-line` et `verdict` ne donnent pas la solution.** Le jumeau du test
   `test_le_geste_de_reparation_survit` : sur un `challenge`, `mkdir -p
   reponses` est ABSENT de l'écran.
3. **Le contrat est opposable** : `validate-structure` refuse ce qui viderait un
   critère en silence.

Un vrai pytest tourne sur des catalogues factices en `tmp_path`.
"""

from __future__ import annotations

import json
import re
import textwrap
from pathlib import Path

import pytest
from typer.testing import CliRunner

from dsoxlab.cli import app
from dsoxlab.i18n.strings import en as EN
from dsoxlab.models.lab import LabDefinition
from dsoxlab.reporting.machine import export_result_dict
from dsoxlab.services.lab_service import check_lab, evaluate_lab
from dsoxlab.services.rapport_de_criteres import (
    ResultatDeCritere,
    regrouper_par_declaration,
)
from dsoxlab.sessions.store import get_all_results
from dsoxlab.validators.contract import validate_unknown_keys
from dsoxlab.validators.metadata import validate_metadata

REFERENCES = Path(__file__).resolve().parent / "references"

MESSAGE_LONG = (
    "reponses/cours.txt manquant. Le mot se lit dans : dsoxlab course premiers-pas\n"
    "Cree le fichier, par exemple : mkdir -p reponses && echo mot > reponses/cours.txt"
)

TESTS_ECHEC = f'''\
import pytest

def test_le_mot_du_cours():
    assert False, {MESSAGE_LONG!r}

def test_la_mission():
    assert False, "reponses/mission.txt manquant."

def test_ok():
    assert True

@pytest.fixture
def socle():
    raise RuntimeError("detail technique SECRET")

def test_bloque(socle):
    assert True

@pytest.mark.skip(reason="r")
def test_saute():
    assert True
'''

TESTS_REUSSITE = "def test_un():\n    assert True\n\ndef test_deux():\n    assert True\n"

LAB_YAML = (
    "id: premier\ntitle: Premier\nlevel: l1\nskills: [s]\ndistros: [alma10]\n"
    "doc_url: https://example.test/doc\nruntime:\n  type: shell\n"
    "  workdir: challenge/work\n"
)


def _catalogue(
    racine: Path, *, extra: str = "", tests: str = TESTS_ECHEC, lab_fr: str | None = None
) -> Path:
    racine.mkdir(parents=True, exist_ok=True)
    (racine / "meta.yml").write_text(
        "repo:\n  id: politique-test\n  category: demo\n", encoding="utf-8"
    )
    lab = racine / "labs" / "demo" / "premier"
    (lab / "challenge" / "tests").mkdir(parents=True, exist_ok=True)
    (lab / "challenge" / "work").mkdir(parents=True, exist_ok=True)
    (lab / "lab.yaml").write_text(LAB_YAML + extra, encoding="utf-8")
    if lab_fr is not None:
        (lab / "lab.fr.yaml").write_text(lab_fr, encoding="utf-8")
    (lab / "challenge" / "tests" / "test_functional.py").write_text(tests, encoding="utf-8")
    return racine


@pytest.fixture(autouse=True)
def _env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "state"))
    monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path / "cache"))
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "data"))
    monkeypatch.setenv("DSOXLAB_LANG", "en")
    monkeypatch.setenv("COLUMNS", "80")
    monkeypatch.delenv("LAB_HOME", raising=False)
    monkeypatch.delenv("DSOXLAB_RAPPORT", raising=False)


def _ecran(racine: Path) -> tuple[int, str]:
    resultat = CliRunner().invoke(app, ["check", "premier", "--lab-home", str(racine)])
    return resultat.exit_code, re.sub(r"\d+:\d\d:\d\d", "H:MM:SS", resultat.output)


def _lab(racine: Path, lang: str = "en") -> LabDefinition:
    return LabDefinition.from_yaml(
        racine / "labs" / "demo" / "premier" / "lab.yaml", lang=lang
    )


# ── 1. l'écran d'un lab guidé, capturé en entier ──────────────────────────
#
# Ces captures ont figé la sortie de la 0.7.3, pour prouver que la politique
# d'affichage ne changeait rien au lab le plus courant. Elles ont changé UNE
# fois depuis, en 0.8.1 : un critère non évalué y passait pour un échec de
# l'apprenant (issue #350). C'est la seule ligne qui diffère, et le reste de
# l'écran reste la référence qu'il était.


def test_l_ecran_d_un_lab_guide_en_echec_ne_bouge_pas(tmp_path: Path) -> None:
    code, ecran = _ecran(_catalogue(tmp_path / "d"))

    assert code == 1
    assert ecran == (REFERENCES / "check_lab_full_echec.txt").read_text(encoding="utf-8")


def test_l_ecran_d_un_lab_guide_en_reussite_ne_bouge_pas(
    tmp_path: Path,
) -> None:
    code, ecran = _ecran(_catalogue(tmp_path / "d", tests=TESTS_REUSSITE))

    assert code == 0
    assert ecran == (REFERENCES / "check_lab_full_reussite.txt").read_text(encoding="utf-8")


def test_feedback_full_explicite_ne_change_pas_l_ecran_d_un_lab(tmp_path: Path) -> None:
    _, ecran = _ecran(_catalogue(tmp_path / "d", extra="feedback: full\n"))
    assert ecran == (REFERENCES / "check_lab_full_echec.txt").read_text(encoding="utf-8")


def test_un_critere_non_evalue_porte_sa_mention_sur_un_lab_guide(tmp_path: Path) -> None:
    """Issue #350 : la distinction vaut pour TOUTES les politiques, pas deux sur trois.

    Le catalogue de ce module porte un `test_bloque` dont la fixture lève : la
    machine n'a donc rien pu conclure. Sur `first-line` et `verdict`, il
    s'affichait avec un `?` et sa mention ; sur `full`, il était rangé parmi les
    tests ratés avec une croix rouge, et l'apprenant cherchait dans son travail
    une faute qui n'y était pas.

    Le `?` n'est pas la mise en forme, c'est le VERDICT : ce test lit donc les
    deux, le signe et la mention traduite.
    """
    _, ecran = _ecran(_catalogue(tmp_path / "d"))

    mention = EN.STRINGS["check_critere_non_evalue"]
    assert f"? bloque ({mention})" in ecran
    assert "✘ bloque" not in ecran, (
        "un critère que rien n'a pu évaluer reste affiché comme un échec"
    )
    assert ecran.count(EN.STRINGS["check_echecs_de_tests"]) == 1, (
        "le titre « ce qu'il reste à faire » est écrit deux fois"
    )


def test_un_challenge_en_full_garde_le_geste_de_reparation(tmp_path: Path) -> None:
    _, ecran = _ecran(_catalogue(tmp_path / "d", extra="lab_type: challenge\nfeedback: full\n"))
    assert "mkdir -p reponses" in ecran


# ── 2. first-line et verdict ne donnent pas la solution ───────────────────


def test_un_challenge_ne_montre_que_la_premiere_ligne(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    code, ecran = _ecran(_catalogue(tmp_path / "d", extra="lab_type: challenge\n"))
    with capsys.disabled():
        print("\n----- check, feedback first-line (challenge par défaut) -----")
        print(ecran)

    assert code == 1
    # Le libellé, le verdict, et la première ligne du message de l'auteur.
    assert "le mot du cours (not met)" in ecran
    assert "reponses/cours.txt manquant. Le mot se lit dans" in ecran
    # Le jumeau de `test_le_geste_de_reparation_survit` : le geste est ABSENT.
    assert "mkdir -p" not in ecran
    assert "Cree le fichier" not in ecran
    # La mission n'a qu'une ligne : elle se voit.
    assert "la mission (not met)" in ecran
    # Pas d'invite vers `-v`, qui montrerait tout.
    assert "dsoxlab -v check" not in ecran


def test_un_critere_bloque_se_dit_non_evalue_et_jamais_non_satisfait(
    tmp_path: Path,
) -> None:
    _, ecran = _ecran(_catalogue(tmp_path / "d", extra="lab_type: challenge\n"))

    assert "bloque (not evaluated: check impossible)" in ecran
    assert "bloque (not met)" not in ecran
    assert "SECRET" not in ecran, "le texte d'une exception technique ne s'affiche jamais"
    assert "saute" not in ecran.split("What is left")[1], "un test sauté n'est pas à revoir"


def test_un_capstone_ne_dit_que_le_verdict(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    code, ecran = _ecran(_catalogue(tmp_path / "d", extra="lab_type: capstone\n"))
    with capsys.disabled():
        print("\n----- check, feedback verdict (capstone par défaut) -----")
        print(ecran)

    assert code == 1
    assert "le mot du cours (not met)" in ecran
    assert "reponses/" not in ecran
    assert "manquant" not in ecran
    assert "mkdir" not in ecran
    assert "bloque (not evaluated: check impossible)" in ecran


def test_un_lab_peut_demander_verdict_ou_first_line(tmp_path: Path) -> None:
    _, verdict = _ecran(_catalogue(tmp_path / "a", extra="feedback: verdict\n"))
    _, premiere = _ecran(_catalogue(tmp_path / "b", extra="feedback: first-line\n"))

    assert "manquant" not in verdict
    assert "manquant" in premiere and "mkdir" not in premiere


def test_la_politique_s_affiche_en_francais(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("DSOXLAB_LANG", "fr")
    _, ecran = _ecran(_catalogue(tmp_path / "d", extra="lab_type: challenge\n"))

    assert "(non satisfait)" in ecran
    assert "(non évalué : vérification impossible)" in ecran
    assert "mkdir" not in ecran


@pytest.mark.parametrize(
    ("extra", "attendu"),
    [
        ("", "full"),
        ("lab_type: lab\n", "full"),
        ("lab_type: validation\n", "full"),
        ("lab_type: challenge\n", "first-line"),
        ("lab_type: capstone\n", "verdict"),
        ("lab_type: challenge\nexam_passing_score: 70\n", "verdict"),
        ("exam_passing_score: 70\n", "verdict"),
        ("lab_type: capstone\nfeedback: full\n", "full"),
        ("lab_type: challenge\nfeedback: verdict\n", "verdict"),
        ("feedback: n-importe-quoi\n", "full"),
        ("lab_type: challenge\nfeedback: n-importe-quoi\n", "first-line"),
    ],
)
def test_la_politique_par_defaut_suit_le_type_du_lab(
    tmp_path: Path, extra: str, attendu: str
) -> None:
    assert _lab(_catalogue(tmp_path / "d", extra=extra)).feedback_policy == attendu


# ── critères déclarés ─────────────────────────────────────────────────────

CRITERES = """\
criteria:
  - id: acces-documente
    label: Documented access
    tests: [test_le_mot_du_cours, test_la_mission]
  - id: socle.pret
    tests: [test_bloque]
"""
CRITERES_FR = """\
criteria:
  - id: acces-documente
    label: Accès documenté
"""


def test_un_critere_declare_regroupe_ses_tests_sous_son_id(tmp_path: Path) -> None:
    racine = _catalogue(tmp_path / "d", extra=CRITERES)
    lab = _lab(racine)

    resultat = check_lab(lab)
    par_id = {c.identifiant: c for c in resultat.criteres or ()}

    assert sorted(par_id) == ["acces-documente", "socle.pret", "test_ok", "test_saute"]
    assert par_id["acces-documente"].etat == "unsatisfied"
    # Le message du premier membre non satisfait, celui de l'auteur.
    assert par_id["acces-documente"].message_auteur == MESSAGE_LONG
    assert par_id["socle.pret"].etat == "not_evaluated"
    # Sans déclaration : un critère par test, comme avant.
    assert par_id["test_ok"].etat == "satisfied"
    assert par_id["test_saute"].etat == "skipped"


def test_le_libelle_declare_remplace_le_nom_du_test_a_l_ecran(tmp_path: Path) -> None:
    racine = _catalogue(
        tmp_path / "d", extra="lab_type: challenge\n" + CRITERES, lab_fr=CRITERES_FR
    )

    _, ecran = _ecran(racine)

    assert "Documented access (not met)" in ecran
    assert "le mot du cours" not in ecran
    # Sans libellé déclaré, le nom du critère : ici son id.
    assert "socle.pret (not evaluated: check impossible)" in ecran


def test_les_libelles_se_surchargent_par_id_dans_lab_fr(tmp_path: Path) -> None:
    racine = _catalogue(tmp_path / "d", extra=CRITERES, lab_fr=CRITERES_FR)

    assert _lab(racine, "en").libelle_de_critere("acces-documente") == "Documented access"
    assert _lab(racine, "fr").libelle_de_critere("acces-documente") == "Accès documenté"
    assert _lab(racine, "fr").libelle_de_critere("socle.pret") is None
    assert _lab(racine, "fr").criteria[0].tests == (
        "test_le_mot_du_cours", "test_la_mission",
    )


def test_un_lab_sans_criteres_ne_declare_rien(tmp_path: Path) -> None:
    lab = _lab(_catalogue(tmp_path / "d"))
    assert lab.criteria == () and lab.feedback is None


def _r(identifiant: str, etat: str, message: str | None = None) -> ResultatDeCritere:
    return ResultatDeCritere(
        identifiant, f"d/t.py::{identifiant}", "call", etat,  # type: ignore[arg-type]
        "author" if message else None, message,
    )


@pytest.mark.parametrize(
    ("etats", "attendu"),
    [
        (["satisfied", "satisfied"], "satisfied"),
        (["satisfied", "unsatisfied"], "unsatisfied"),
        (["unsatisfied", "not_evaluated"], "unsatisfied"),
        (["satisfied", "not_evaluated"], "not_evaluated"),
        (["skipped", "skipped"], "skipped"),
        (["satisfied", "skipped"], "skipped"),
        (["not_evaluated", "skipped"], "not_evaluated"),
    ],
)
def test_l_etat_d_un_critere_declare_qui_regroupe_plusieurs_tests(
    etats: list[str], attendu: str
) -> None:
    criteres = tuple(_r(f"test_t{i}", e) for i, e in enumerate(etats))
    declarations = [("groupe", tuple(f"test_t{i}" for i in range(len(etats))))]

    regroupes = regrouper_par_declaration(criteres, declarations)

    assert regroupes is not None and len(regroupes) == 1
    assert regroupes[0].identifiant == "groupe" and regroupes[0].etat == attendu


def test_le_regroupement_laisse_intact_ce_qui_n_est_pas_declare() -> None:
    criteres = (_r("test_a", "satisfied"), _r("test_b", "unsatisfied", "Msg"))
    assert regrouper_par_declaration(criteres, []) == criteres
    assert regrouper_par_declaration(None, [("g", ("test_a",))]) is None
    regroupes = regrouper_par_declaration(criteres, [("g", ("test_inconnu",))])
    assert regroupes == criteres, "un critère déclaré sans test exécuté n'apparaît pas"


def test_un_cas_parametre_rejoint_le_critere_de_sa_fonction() -> None:
    criteres = (_r("test_p[1]", "satisfied"), _r("test_p[2]", "unsatisfied", "M"))
    (groupe,) = regrouper_par_declaration(criteres, [("param", ("test_p",))]) or ()
    assert (groupe.identifiant, groupe.etat, groupe.message_auteur) == (
        "param", "unsatisfied", "M",
    )


def test_un_id_declare_ne_partage_jamais_l_identifiant_d_un_autre_critere() -> None:
    criteres = (_r("test_a", "satisfied"), _r("test_b", "satisfied"))
    regroupes = regrouper_par_declaration(criteres, [("test_a", ("test_b",))]) or ()
    assert len({c.identifiant for c in regroupes}) == 2


# ── l'export suit la politique ────────────────────────────────────────────


def _ligne(racine: Path, politique_extra: str = "") -> dict:
    lab = _lab(racine)
    evaluate_lab(racine, lab, check_lab(lab))
    (row,) = get_all_results(racine)
    return export_result_dict(row, lab, "politique-test")


def _observations(ligne: dict) -> dict:
    return {c["id"]: c["observation"] for c in ligne["criteria"]}


def test_l_observation_exportee_est_la_premiere_ligne_en_full(tmp_path: Path) -> None:
    obs = _observations(_ligne(_catalogue(tmp_path / "d")))
    assert obs["test_le_mot_du_cours"] == MESSAGE_LONG.splitlines()[0]
    assert "mkdir" not in json.dumps(obs)


def test_l_observation_exportee_est_la_premiere_ligne_en_first_line(tmp_path: Path) -> None:
    obs = _observations(_ligne(_catalogue(tmp_path / "d", extra="lab_type: challenge\n")))
    assert obs["test_le_mot_du_cours"] == MESSAGE_LONG.splitlines()[0]


def test_l_observation_exportee_est_nulle_en_verdict(tmp_path: Path) -> None:
    ligne = _ligne(_catalogue(tmp_path / "d", extra="lab_type: capstone\n"))
    assert set(_observations(ligne).values()) == {None}
    assert ligne["criteria"][0]["state"] == "unsatisfied", "le verdict, lui, est exporté"


def test_l_export_d_un_lab_disparu_du_catalogue_applique_verdict(tmp_path: Path) -> None:
    racine = _catalogue(tmp_path / "d")
    lab = _lab(racine)
    evaluate_lab(racine, lab, check_lab(lab))
    (row,) = get_all_results(racine)

    ligne = export_result_dict(row, None, "politique-test")

    assert set(_observations(ligne).values()) == {None}


def test_l_export_porte_l_id_declare(tmp_path: Path) -> None:
    ligne = _ligne(_catalogue(tmp_path / "d", extra=CRITERES))
    ids = [c["id"] for c in ligne["criteria"]]
    assert ids == ["acces-documente", "test_ok", "socle.pret", "test_saute"]
    assert re.fullmatch(r"[\w.:\[\]-]{1,128}", ids[2])


# ── 3. le contrat est opposable ───────────────────────────────────────────


def _issues(racine: Path) -> list[tuple[str, str]]:
    rapport = validate_metadata(_lab(racine))
    return [(i.key, str(i.params.get("value", i.params.get("criterion", "")))) for i in rapport.issues]


BONS_TESTS = "def test_a():\n    assert True\n\nclass TestC:\n    def test_b(self):\n        assert True\n"


def test_un_contrat_conforme_n_a_aucune_anomalie(tmp_path: Path) -> None:
    racine = _catalogue(
        tmp_path / "d", tests=BONS_TESTS,
        extra="feedback: first-line\ncriteria:\n  - id: un\n    tests: [test_a, test_b]\n",
    )
    assert _issues(racine) == []


@pytest.mark.parametrize(
    ("extra", "cle"),
    [
        ("feedback: bavard\n", "metadata_feedback_inconnu"),
        ("criteria:\n  - id: 'a b'\n    tests: [test_a]\n", "metadata_critere_id_invalide"),
        ("criteria:\n  - id: " + "x" * 129 + "\n    tests: [test_a]\n", "metadata_critere_id_invalide"),
        (
            "criteria:\n  - {id: un, tests: [test_a]}\n  - {id: un, tests: [test_b]}\n",
            "metadata_critere_id_double",
        ),
        ("criteria:\n  - id: vide\n", "metadata_critere_sans_test"),
        ("criteria:\n  - id: un\n    tests: [test_renomme]\n", "metadata_critere_test_inconnu"),
        (
            "criteria:\n  - {id: un, tests: [test_a]}\n  - {id: deux, tests: [test_a]}\n",
            "metadata_critere_test_partage",
        ),
    ],
)
def test_validate_structure_refuse_ce_qui_viderait_un_critere(
    tmp_path: Path, extra: str, cle: str
) -> None:
    racine = _catalogue(tmp_path / "d", tests=BONS_TESTS, extra=extra)
    assert cle in [k for k, _ in _issues(racine)]


def test_les_cles_criteria_et_feedback_sont_connues_du_contrat(tmp_path: Path) -> None:
    racine = _catalogue(
        tmp_path / "d", tests=BONS_TESTS,
        extra="feedback: full\ncriteria:\n  - {id: un, tests: [test_a], label: Un}\n",
        lab_fr=CRITERES_FR,
    )
    assert validate_unknown_keys(racine).issues == []


def test_une_cle_de_critere_inconnue_est_signalee(tmp_path: Path) -> None:
    racine = _catalogue(
        tmp_path / "d", tests=BONS_TESTS,
        extra="criteria:\n  - {id: un, tests: [test_a], libele: Un}\n",
        lab_fr="criteria:\n  - {id: un, tests: [test_a]}\n",
    )
    chemins = " ".join(str(i.params) for i in validate_unknown_keys(racine).issues)
    assert "criteria[].libele" in chemins
    assert "criteria[].tests" in chemins, "une traduction ne porte que `id` et `label`"


def test_le_squelette_d_un_lab_reste_conforme(tmp_path: Path) -> None:
    from dsoxlab.services.scaffold import _LAB_COMMUN

    assert "feedback" in textwrap.dedent(_LAB_COMMUN)


# ── une épreuve ne donne rien, pas même avec -v ni avec --json ────────────

MOTS_INTERDITS = ("mkdir", "manquant", "Cree le fichier", "AssertionError", "assert ")


def _invoquer(racine: Path, *args: str) -> tuple[int, str, str]:
    resultat = CliRunner().invoke(
        app, [*[a for a in args if a == "-v"], "check", "premier",
              *[a for a in args if a != "-v"], "--lab-home", str(racine)]
    )
    return resultat.exit_code, resultat.stdout, re.sub(r"\d+:\d\d:\d\d", "H:MM:SS", resultat.output)


def _journal(tmp_path: Path) -> str:
    chemin = tmp_path / "state" / "dsoxlab" / "dsoxlab.log"
    return chemin.read_text(encoding="utf-8") if chemin.is_file() else ""


def test_v_check_d_une_epreuve_n_affiche_aucun_message_d_assertion(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    racine = _catalogue(tmp_path / "d", extra="lab_type: capstone\n")

    code, _, ecran = _invoquer(racine, "-v")
    with capsys.disabled():
        print("\n----- dsoxlab -v check, epreuve (verdict) -----")
        print(ecran)

    assert code == 1
    for interdit in MOTS_INTERDITS:
        assert interdit not in ecran, interdit
    assert "le mot du cours (not met)" in ecran
    assert "bloque (not evaluated: check impossible)" in ecran
    assert "the test detail is not available" in ecran
    assert "SECRET" not in ecran


def test_v_check_d_un_lab_avec_seuil_est_ferme_comme_une_epreuve(tmp_path: Path) -> None:
    racine = _catalogue(tmp_path / "d", extra="lab_type: challenge\nexam_passing_score: 70\n")
    _, _, ecran = _invoquer(racine, "-v")
    assert "mkdir" not in ecran and "the test detail is not available" in ecran


def test_json_d_une_epreuve_ne_porte_aucun_message_d_assertion(tmp_path: Path) -> None:
    racine = _catalogue(tmp_path / "d", extra="lab_type: capstone\n")

    code, sortie, _ = _invoquer(racine, "--json")
    document = json.loads(sortie)
    check = document["check"]

    assert code == 1
    assert check["output"] == "" and check["output_withheld"] is True
    for interdit in (*MOTS_INTERDITS, "SECRET"):
        assert interdit not in sortie, interdit
    # Ce qui reste : les compteurs, les noms, les critères sans observation.
    assert (check["passed"], check["total"], check["ok"]) == (1, 5, False)
    assert check["failed_checks"] == ["test_le_mot_du_cours", "test_la_mission", "test_bloque"]
    etats = {c["id"]: (c["state"], c["observation"]) for c in check["criteria"]}
    assert etats["test_le_mot_du_cours"] == ("unsatisfied", None)
    assert etats["test_bloque"] == ("not_evaluated", None)
    assert etats["test_ok"] == ("satisfied", None)


def test_un_lab_full_garde_v_et_output_complets(tmp_path: Path) -> None:
    """Non-régression : la fermeture ne vaut que pour `verdict`."""
    racine = _catalogue(tmp_path / "d")

    _, _, ecran = _invoquer(racine, "-v")
    _, sortie, _ = _invoquer(racine, "--json")
    check = json.loads(sortie)["check"]

    assert "mkdir -p reponses" in ecran and "AssertionError" in ecran
    assert "mkdir -p reponses" in check["output"] and check["output_withheld"] is False
    # `criteria` porte la première ligne seulement, comme l'export.
    obs = {c["id"]: c["observation"] for c in check["criteria"]}
    assert obs["test_le_mot_du_cours"] == MESSAGE_LONG.splitlines()[0]


def test_un_challenge_en_first_line_garde_v_et_output(tmp_path: Path) -> None:
    racine = _catalogue(tmp_path / "d", extra="lab_type: challenge\n")
    _, _, ecran = _invoquer(racine, "-v")
    _, sortie, _ = _invoquer(racine, "--json")
    assert "mkdir -p reponses" in ecran
    assert "mkdir -p reponses" in json.loads(sortie)["check"]["output"]


def test_seul_un_feedback_explicite_ouvre_une_epreuve(tmp_path: Path) -> None:
    for extra in ("lab_type: capstone\nfeedback: full\n", "lab_type: capstone\nfeedback: first-line\n"):
        racine = _catalogue(tmp_path / extra.split("feedback: ")[1].strip(), extra=extra)
        _, _, ecran_v = _invoquer(racine, "-v")
        _, sortie, _ = _invoquer(racine, "--json")
        assert "mkdir -p reponses" in ecran_v
        check = json.loads(sortie)["check"]
        assert check["output_withheld"] is False and "mkdir -p reponses" in check["output"]


def test_le_journal_ne_recrache_pas_les_messages_d_une_epreuve(tmp_path: Path) -> None:
    """Le journal garde les commandes lancées et leur code de retour, pas la sortie de pytest."""
    racine = _catalogue(tmp_path / "d", extra="lab_type: capstone\n")

    _invoquer(racine, "-v")
    _invoquer(racine, "--json")
    journal = _journal(tmp_path)

    assert "pytest" in journal, "le journal existe et porte bien la commande lancée"
    for interdit in (*MOTS_INTERDITS, "SECRET"):
        assert interdit not in journal, interdit


def test_scores_et_status_ne_nomment_que_des_controles(tmp_path: Path) -> None:
    racine = _catalogue(tmp_path / "d", extra="lab_type: capstone\n")
    _invoquer(racine)
    for commande in (["scores"], ["scores", "--json"], ["status", "premier"], ["progress"]):
        sortie = CliRunner().invoke(app, [*commande, "--lab-home", str(racine)]).output
        for interdit in ("mkdir", "manquant", "Cree le fichier", "SECRET"):
            assert interdit not in sortie, (commande, interdit)


# ── criteria[].lessons : déclarées, jamais montrées, jamais exportées ─────

LECONS = (
    "criteria:\n  - id: acces\n    tests: [test_le_mot_du_cours, test_la_mission]\n"
    "    lessons:\n      - https://www.stephane-robert.info/docs/x/y/#ancre\n"
    "      - http://exemple.test/lecon\n"
)


def test_un_check_d_epreuve_n_affiche_aucune_url_de_lecon(tmp_path: Path) -> None:
    racine = _catalogue(tmp_path / "d", extra="lab_type: capstone\n" + LECONS)

    for options in ((), ("-v",)):
        _, _, ecran = _invoquer(racine, *options)
        assert "http" not in ecran and "stephane-robert" not in ecran
    _, sortie, _ = _invoquer(racine, "--json")
    assert "stephane-robert" not in sortie and "lessons" not in sortie


def test_les_lecons_ne_sortent_jamais_dans_l_export(tmp_path: Path) -> None:
    racine = _catalogue(tmp_path / "d", extra=LECONS)
    lab = _lab(racine)
    evaluate_lab(racine, lab, check_lab(lab))
    (row,) = get_all_results(racine)

    ligne = json.dumps(export_result_dict(row, lab, "politique-test"))

    assert "stephane-robert" not in ligne and "lessons" not in ligne
    assert lab.criteria[0].lessons == (
        "https://www.stephane-robert.info/docs/x/y/#ancre", "http://exemple.test/lecon",
    )


def _issues_lecons(racine: Path) -> list[str]:
    return [i.key for i in validate_metadata(_lab(racine)).issues if "lecon" in i.key]


@pytest.mark.parametrize(
    "lecons",
    [
        "[https://www.stephane-robert.info/docs/a/]",
        "[https://www.stephane-robert.info/docs/a/#section-2]",
        "[http://exemple.test/a, https://exemple.test/b]",
        "[https://a.test/1, https://a.test/2, https://a.test/3, https://a.test/4, https://a.test/5]",
    ],
)
def test_des_lecons_bien_formees_passent(tmp_path: Path, lecons: str) -> None:
    extra = f"criteria:\n  - id: un\n    tests: [test_ok]\n    lessons: {lecons}\n"
    racine = _catalogue(tmp_path / "d", tests="def test_ok():\n    assert True\n", extra=extra)
    assert _issues_lecons(racine) == []


@pytest.mark.parametrize(
    ("lecons", "cle"),
    [
        ("[]", "metadata_lecons_vide"),
        ("[/docs/relatif/]", "metadata_lecon_url_invalide"),
        ("[ftp://exemple.test/a]", "metadata_lecon_url_invalide"),
        ("[www.stephane-robert.info/docs/a/]", "metadata_lecon_url_invalide"),
        ("['https://']", "metadata_lecon_url_invalide"),
        ("['https://a.test/une lecon']", "metadata_lecon_url_invalide"),
        ("[https://a.test/1, https://a.test/1]", "metadata_lecon_doublon"),
        (
            ("[https://a.test/1, https://a.test/2, https://a.test/3, https://a.test/4, "
             "https://a.test/5, https://a.test/6]"),
            "metadata_lecons_trop",
        ),
    ],
)
def test_des_lecons_mal_formees_sont_refusees(tmp_path: Path, lecons: str, cle: str) -> None:
    extra = f"criteria:\n  - id: un\n    tests: [test_ok]\n    lessons: {lecons}\n"
    racine = _catalogue(tmp_path / "d", tests="def test_ok():\n    assert True\n", extra=extra)
    assert cle in _issues_lecons(racine)


def test_les_lecons_ne_se_traduisent_pas(tmp_path: Path) -> None:
    racine = _catalogue(
        tmp_path / "d", tests="def test_ok():\n    assert True\n",
        extra="criteria:\n  - {id: un, tests: [test_ok], lessons: [https://a.test/1]}\n",
        lab_fr="criteria:\n  - {id: un, lessons: [https://a.test/1]}\n",
    )
    chemins = " ".join(str(i.params) for i in validate_unknown_keys(racine).issues)
    assert "criteria[].lessons" in chemins
