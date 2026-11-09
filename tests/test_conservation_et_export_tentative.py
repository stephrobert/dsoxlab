"""Une tentative se conserve avec de quoi la relire, et s'exporte sans rien deviner.

Lots B (conservation) et C (export) de l'issue #336, 0.8.0. Chaque `check`
enregistré consigne un identifiant, l'empreinte du lab, la révision du
catalogue, un résultat par critère et les indices vus. L'export les rend dans
`dsoxlab-evidence-v1` par EXTENSION COMPATIBLE : le nom du schéma et le sens des
champs existants ne bougent pas, et une ligne d'avant 0.8.0 porte `null` partout.

Un vrai pytest tourne sur des catalogues factices en `tmp_path`, par
`check_lab` puis `evaluate_lab` : ce qui est consigné est ce que le moteur
produit, pas ce qu'un test y a posé à la main. Aucun lab réel n'est joué.
"""

from __future__ import annotations

import json
import re
import sqlite3
import subprocess
import textwrap
from pathlib import Path

import pytest

from dsoxlab.models.lab import (
    LabDefinition,
    RuntimeConfig,
    RuntimeType,
    ValidationConfig,
)
from dsoxlab.services.evidence import construire_document
from dsoxlab.services.lab_service import check_lab, evaluate_lab
from dsoxlab.sessions.store import (
    get_all_results,
    hint_requests_for,
    record_hint,
    record_result,
    reset_hints,
)

JETON = re.compile(r"^[\w.:\[\]-]+$")

TESTS = """\
    import pytest

    @pytest.fixture
    def socle():
        raise RuntimeError("SECRET-TECHNIQUE-A-NE-JAMAIS-EXPORTER")

    @pytest.mark.parametrize("n", [1, 2])
    def test_pair(n):
        assert n % 2 == 0, "Le nombre doit etre pair, cree le fichier."

    def test_depend_du_socle(socle):
        assert True

    def test_reussi():
        assert True
    """


def _lab(racine: Path, nom: str = "premier", tests: str = TESTS) -> LabDefinition:
    racine.mkdir(parents=True, exist_ok=True)
    (racine / "meta.yml").write_text(
        "repo:\n  id: tentative-test\n  category: demo\n", encoding="utf-8"
    )
    lab_dir = racine / "labs" / "demo" / nom
    (lab_dir / "challenge" / "tests").mkdir(parents=True, exist_ok=True)
    (lab_dir / "challenge" / "tests" / "test_functional.py").write_text(
        textwrap.dedent(tests), encoding="utf-8"
    )
    (lab_dir / "lab.yaml").write_text(f"id: {nom}\n", encoding="utf-8")
    return LabDefinition(
        id=nom,
        title=nom,
        level="l1",
        skills=["s"],
        runtime=RuntimeConfig(type=RuntimeType.SHELL, workdir="challenge/work"),
        distros=["alma10"],
        doc_url="https://example.test/doc",
        validation=ValidationConfig(),
        path=lab_dir,
        section="demo",
    )


@pytest.fixture(autouse=True)
def _env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("DSOXLAB_RAPPORT", raising=False)


def _tenter(racine: Path, lab: LabDefinition) -> None:
    evaluate_lab(racine, lab, check_lab(lab))


def _derniere(racine: Path) -> dict:
    return get_all_results(racine)[-1]


# ── B : une base 0.7.3 se relit ───────────────────────────────────────────


def _base_073(racine: Path) -> None:
    """La base telle que 0.7.3 la crée : sans aucune des colonnes de 0.8.0."""
    conn = sqlite3.connect(racine / ".dsoxlab.db")
    conn.executescript("""
        CREATE TABLE results (
            id INTEGER PRIMARY KEY AUTOINCREMENT, lab_id TEXT NOT NULL,
            section TEXT NOT NULL, validated_at TEXT NOT NULL,
            score INTEGER NOT NULL, max_score INTEGER NOT NULL,
            passed_tests INTEGER NOT NULL, total_tests INTEGER NOT NULL,
            hints_used INTEGER NOT NULL,
            blocking_failed TEXT NOT NULL DEFAULT '',
            failed_checks TEXT NOT NULL DEFAULT ''
        );
        CREATE TABLE hint_requests (
            id INTEGER PRIMARY KEY AUTOINCREMENT, lab_id TEXT NOT NULL,
            hint_index INTEGER NOT NULL, requested_at TEXT NOT NULL,
            cost INTEGER NOT NULL
        );
        INSERT INTO results (lab_id, section, validated_at, score, max_score,
            passed_tests, total_tests, hints_used, failed_checks)
        VALUES ('premier', 'demo', '2026-10-01T10:00:00+00:00', 60, 100, 3, 5, 0,
            'test_a,test_b');
    """)
    conn.commit()
    conn.close()


NOUVELLES = ("attempt_id", "lab_digest", "catalog_revision", "criteria", "hints_seen")


def test_une_base_073_se_relit_et_ses_lignes_donnent_null(tmp_path: Path) -> None:
    _base_073(tmp_path)

    (ancienne,) = get_all_results(tmp_path)

    assert ancienne["score"] == 60 and ancienne["failed_checks"] == "test_a,test_b"
    assert {c: ancienne[c] for c in NOUVELLES} == dict.fromkeys(NOUVELLES)


def test_une_base_073_migree_accepte_une_nouvelle_tentative(tmp_path: Path) -> None:
    _base_073(tmp_path)
    lab = _lab(tmp_path)

    _tenter(tmp_path, lab)
    ancienne, nouvelle = get_all_results(tmp_path)

    assert ancienne["attempt_id"] is None
    assert nouvelle["attempt_id"] is not None


def test_l_export_d_une_ancienne_ligne_porte_null_partout(tmp_path: Path) -> None:
    _base_073(tmp_path)
    lab = _lab(tmp_path)

    document = construire_document(tmp_path, {"premier": lab}, catalog_id="c")
    (ligne,) = document["results"]

    assert {c: ligne[c] for c in (*NOUVELLES, "not_evaluated")} == {
        "attempt_id": None, "lab_digest": None, "catalog_revision": None,
        "criteria": None, "hints_seen": None, "not_evaluated": None,
    }
    # Et ce qui existait ne change pas.
    assert ligne["failed_checks"] == ["test_a", "test_b"]
    assert document["schema"] == "dsoxlab-evidence-v1"


# ── B : ce que `check` consigne ───────────────────────────────────────────


def test_deux_checks_donnent_deux_identifiants_de_tentative(tmp_path: Path) -> None:
    lab = _lab(tmp_path)

    _tenter(tmp_path, lab)
    _tenter(tmp_path, lab)
    premier, second = get_all_results(tmp_path)

    uuid4 = r"[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}"
    assert re.fullmatch(uuid4, premier["attempt_id"])
    assert re.fullmatch(uuid4, second["attempt_id"])
    assert premier["attempt_id"] != second["attempt_id"]
    assert premier["lab_digest"] == second["lab_digest"]


def test_les_criteres_consignes_ne_portent_aucun_texte_technique(tmp_path: Path) -> None:
    lab = _lab(tmp_path)

    _tenter(tmp_path, lab)
    brut = _derniere(tmp_path)["criteria"]
    criteres = {c["id"]: c for c in json.loads(brut)}

    assert sorted(criteres) == [
        "test_depend_du_socle", "test_pair[1]", "test_pair[2]", "test_reussi",
    ]
    assert criteres["test_pair[1]"]["state"] == "unsatisfied"
    assert criteres["test_pair[1]"]["author_message"] == "Le nombre doit etre pair, cree le fichier."
    assert criteres["test_pair[2]"]["state"] == "satisfied"
    assert criteres["test_depend_du_socle"]["state"] == "not_evaluated"
    assert criteres["test_depend_du_socle"]["author_message"] is None
    assert "SECRET-TECHNIQUE" not in brut
    assert str(tmp_path) not in brut


def test_la_revision_du_catalogue_est_celle_du_check(tmp_path: Path) -> None:
    """Un vrai dépôt git : la révision est consignée AU MOMENT du check."""
    lab = _lab(tmp_path)
    git = ["git", "-C", str(tmp_path), "-c", "user.name=t", "-c", "user.email=t@t.test"]
    subprocess.run([*git, "init", "-q"], check=True)
    subprocess.run([*git, "add", "meta.yml"], check=True)
    subprocess.run([*git, "commit", "-q", "-m", "un"], check=True)
    un = subprocess.run(
        [*git, "rev-parse", "HEAD"], check=True, capture_output=True, text=True
    ).stdout.strip()

    _tenter(tmp_path, lab)
    subprocess.run([*git, "commit", "-q", "--allow-empty", "-m", "deux"], check=True)
    _tenter(tmp_path, lab)
    premier, second = get_all_results(tmp_path)

    assert premier["catalog_revision"] == un
    assert second["catalog_revision"] != un
    # L'export garde le sens de `catalog.version` : la révision d'AUJOURD'HUI.
    document = construire_document(tmp_path, {"premier": lab}, catalog_id="c")
    assert document["catalog"]["version"] == second["catalog_revision"]
    assert document["results"][0]["catalog_revision"] == un


def test_hors_d_un_depot_git_la_revision_reste_null(tmp_path: Path) -> None:
    lab = _lab(tmp_path / "sans-git")
    _tenter(tmp_path / "sans-git", lab)
    assert _derniere(tmp_path / "sans-git")["catalog_revision"] is None


def test_reset_ne_touche_pas_aux_indices_deja_consignes(tmp_path: Path) -> None:
    lab = _lab(tmp_path)
    (lab.path / "challenge" / "hints.yaml").write_text(
        "points: 100\nhints:\n"
        "  - {id: 'indice-un', cost: 5, text_en: a}\n"
        "  - {id: 2, cost: 5, text_en: b}\n",
        encoding="utf-8",
    )
    record_hint(tmp_path, lab.id, 0, 5)
    record_hint(tmp_path, lab.id, 1, 5)

    _tenter(tmp_path, lab)
    reset_hints(tmp_path, lab.id)

    assert hint_requests_for(tmp_path, lab.id) == []
    consignes = json.loads(_derniere(tmp_path)["hints_seen"])
    assert consignes == [
        {"index": 0, "id": "indice-un", "criterion": None},
        {"index": 1, "id": "2", "criterion": None},
    ]


def test_sans_indice_demande_la_liste_est_vide_et_non_inconnue(tmp_path: Path) -> None:
    lab = _lab(tmp_path)
    _tenter(tmp_path, lab)
    assert json.loads(_derniere(tmp_path)["hints_seen"]) == []


def test_un_lab_sans_hints_yaml_consigne_l_index_sans_id(tmp_path: Path) -> None:
    lab = _lab(tmp_path)
    record_hint(tmp_path, lab.id, 0, 10)
    _tenter(tmp_path, lab)
    assert json.loads(_derniere(tmp_path)["hints_seen"]) == [
        {"index": 0, "id": None, "criterion": None}
    ]


# ── B : l'empreinte du lab ────────────────────────────────────────────────


def test_l_empreinte_change_si_un_test_change(tmp_path: Path) -> None:
    from dsoxlab.services.tentative import empreinte_du_lab

    lab = _lab(tmp_path)
    avant = empreinte_du_lab(lab)
    assert re.fullmatch(r"[0-9a-f]{16}", avant)
    assert empreinte_du_lab(lab) == avant

    test = lab.path / "challenge" / "tests" / "test_functional.py"
    test.write_text(test.read_text(encoding="utf-8") + "\n# modifie\n", encoding="utf-8")
    assert empreinte_du_lab(lab) != avant


def test_l_empreinte_change_avec_lab_yaml_et_hints_et_un_nouveau_test(tmp_path: Path) -> None:
    from dsoxlab.services.tentative import empreinte_du_lab

    lab = _lab(tmp_path)
    base = empreinte_du_lab(lab)
    seen = {base}
    (lab.path / "lab.yaml").write_text("id: premier\ntitle: autre\n", encoding="utf-8")
    seen.add(empreinte_du_lab(lab))
    (lab.path / "challenge" / "hints.yaml").write_text("hints: []\n", encoding="utf-8")
    seen.add(empreinte_du_lab(lab))
    (lab.path / "challenge" / "tests" / "sous").mkdir()
    (lab.path / "challenge" / "tests" / "sous" / "test_b.py").write_text("x = 1\n")
    seen.add(empreinte_du_lab(lab))
    assert len(seen) == 4


def test_l_empreinte_ignore_un_autre_lab_et_les_caches(tmp_path: Path) -> None:
    from dsoxlab.services.tentative import empreinte_du_lab

    lab = _lab(tmp_path)
    avant = empreinte_du_lab(lab)

    autre = _lab(tmp_path, "second", tests="def test_autre():\n    assert False\n")
    (autre.path / "challenge" / "tests" / "test_functional.py").write_text("# change\n")
    cache = lab.path / "challenge" / "tests" / "__pycache__"
    cache.mkdir()
    (cache / "test_functional.cpython-314.pyc").write_bytes(b"\0\1\2")
    (lab.path / "challenge" / "tests" / ".pytest_cache").mkdir()

    assert empreinte_du_lab(lab) == avant


def test_l_empreinte_ne_change_pas_apres_un_check(tmp_path: Path) -> None:
    """pytest écrit des `__pycache__` dans le lab : ils ne doivent pas l'user."""
    from dsoxlab.services.tentative import empreinte_du_lab

    lab = _lab(tmp_path)
    avant = empreinte_du_lab(lab)
    _tenter(tmp_path, lab)
    assert _derniere(tmp_path)["lab_digest"] == avant
    assert empreinte_du_lab(lab) == avant


# ── C : l'export ──────────────────────────────────────────────────────────


def _ligne_exportee(racine: Path, lab: LabDefinition) -> dict:
    document = construire_document(racine, {lab.id: lab}, catalog_id="tentative-test")
    return document["results"][-1]


def test_exemple_reel_de_ligne_d_export(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    lab = _lab(tmp_path)
    record_hint(tmp_path, lab.id, 0, 5)
    _tenter(tmp_path, lab)

    ligne = _ligne_exportee(tmp_path, lab)
    with capsys.disabled():
        print("\nLIGNE D'EXPORT (0.8.0) :")
        print(json.dumps(ligne, indent=2, ensure_ascii=False))

    assert ligne["failed_checks"] == ["test_pair", "test_depend_du_socle"]
    assert ligne["not_evaluated"] == ["test_depend_du_socle"]
    assert ligne["hints_seen"] == [{"index": 0, "id": None, "criterion": None}]
    par_id = {c["id"]: c for c in ligne["criteria"]}
    assert par_id["test_pair[1]"] == {
        "id": "test_pair[1]", "state": "unsatisfied", "phase": "call",
        "mention": None, "observation": "Le nombre doit etre pair, cree le fichier.",
    }
    assert par_id["test_depend_du_socle"]["state"] == "not_evaluated"
    assert par_id["test_depend_du_socle"]["observation"] is None
    assert set(par_id["test_reussi"]) == {"id", "state", "phase", "mention", "observation"}


def test_l_export_respecte_le_contrat_du_site(tmp_path: Path) -> None:
    lab = _lab(tmp_path)
    _tenter(tmp_path, lab)

    ligne = _ligne_exportee(tmp_path, lab)
    brut = json.dumps(ligne, ensure_ascii=False)

    for critere in ligne["criteria"]:
        assert JETON.fullmatch(critere["id"]) and len(critere["id"]) <= 128
        assert critere["state"] in {"satisfied", "unsatisfied", "not_evaluated"}
    for nom in ligne["not_evaluated"]:
        assert len(nom) <= 128
    assert len(ligne["not_evaluated"]) <= 20
    # Rien d'absolu, rien de technique, jamais de nodeid avec chemin.
    assert str(tmp_path) not in brut
    assert "SECRET-TECHNIQUE" not in brut
    assert "nodeid" not in brut
    assert "::" not in " ".join(c["id"] for c in ligne["criteria"] if "/" in c["id"])
    assert "test_functional.py" not in brut


def test_une_observation_est_bornee_a_280(tmp_path: Path) -> None:
    lab = _lab(tmp_path, tests='def test_long():\n    assert False, "x" * 400\n')
    _tenter(tmp_path, lab)

    (critere,) = _ligne_exportee(tmp_path, lab)["criteria"]

    assert len(critere["observation"]) == 280


def test_un_export_n_est_jamais_tronque_en_silence_sur_les_listes_nommees(
    tmp_path: Path,
) -> None:
    corps = "".join(f"def test_n{i}(fix{i}):\n    pass\n" for i in range(30))
    fixtures = "import pytest\n" + "".join(
        f"@pytest.fixture\ndef fix{i}():\n    raise RuntimeError('x')\n" for i in range(30)
    )
    lab = _lab(tmp_path, tests=fixtures + corps)
    _tenter(tmp_path, lab)

    ligne = _ligne_exportee(tmp_path, lab)

    assert len(ligne["not_evaluated"]) == 20  # borne du site
    assert len(ligne["criteria"]) == 30  # les critères eux-mêmes ne sont pas coupés


def test_une_base_retouchee_ne_traverse_pas_la_frontiere(tmp_path: Path) -> None:
    lab = _lab(tmp_path)
    mauvais = json.dumps([
        {"id": "ok", "state": "satisfied", "phase": "call"},
        {"id": "/home/marie/secret.py::t", "state": "satisfied", "phase": "call"},
        {"id": "bon", "state": "invente", "phase": "call"},
        "pas un objet",
    ])
    record_result(
        tmp_path, lab_id="premier", section="demo", score=10, max_score=100,
        passed_tests=1, total_tests=2, hints_used=0,
        attempt_id="pas-un-uuid", lab_digest="../../etc/passwd",
        catalog_revision="rev\nsuspecte", criteria=mauvais, hints_seen="{pas du json",
    )

    ligne = _ligne_exportee(tmp_path, lab)

    assert ligne["attempt_id"] is None
    assert ligne["lab_digest"] is None
    assert ligne["catalog_revision"] is None
    assert ligne["hints_seen"] is None
    assert [c["id"] for c in ligne["criteria"]] == ["ok"]


def test_le_nom_du_schema_et_les_champs_historiques_sont_inchanges(tmp_path: Path) -> None:
    lab = _lab(tmp_path)
    _tenter(tmp_path, lab)

    document = construire_document(tmp_path, {"premier": lab}, catalog_id="c")
    (ligne,) = document["results"]

    assert document["schema"] == "dsoxlab-evidence-v1"
    historiques = {
        "catalog", "lab_id", "lab_type", "section", "validated", "score",
        "max_score", "passed_tests", "total_tests", "hints_used",
        "failed_checks", "blocking_failed", "attempted_at", "exam",
    }
    assert historiques <= set(ligne)
    assert ligne["validated"] is False
    assert ligne["passed_tests"] == 2 and ligne["total_tests"] == 4


def test_un_test_saute_est_skipped_et_n_est_pas_non_evalue(tmp_path: Path) -> None:
    """`skip` et `xfail` ne sont pas une vérification BLOQUÉE par l'environnement."""
    lab = _lab(tmp_path, tests="""\
        import pytest

        @pytest.mark.skip(reason="r")
        def test_saute():
            assert True

        @pytest.mark.xfail
        def test_attendu_rouge():
            assert False

        def test_saute_en_cours():
            pytest.skip("pas ici")

        @pytest.fixture
        def casse():
            raise RuntimeError("x")

        def test_bloque(casse):
            assert True

        def test_ok():
            assert True
        """)
    _tenter(tmp_path, lab)

    ligne = _ligne_exportee(tmp_path, lab)
    etats = {c["id"]: c["state"] for c in ligne["criteria"]}

    assert etats == {
        "test_saute": "skipped",
        "test_attendu_rouge": "skipped",
        "test_saute_en_cours": "skipped",
        "test_bloque": "not_evaluated",
        "test_ok": "satisfied",
    }
    # `not_evaluated` ne nomme que les vérifications bloquées, et il est un
    # sous-ensemble de `failed_checks` : le score les compte en échec.
    assert ligne["not_evaluated"] == ["test_bloque"]
    assert set(ligne["not_evaluated"]) <= set(ligne["failed_checks"])
