"""Le rapport structuré de pytest : un résultat par critère, et rien d'autre ne bouge.

Lot A de l'issue #336 (0.8.0). Le moteur lit désormais, en plus de la sortie
texte, un rapport JSONL écrit par un plugin pytest embarqué. Ce lot est INTERNE :
le score, l'affichage et les codes de sortie restent ceux d'avant, et les tests
protecteurs (``test_sortie_de_check``, ``test_controle_bloquant``) le défendent.

Ces tests lancent un VRAI pytest sur des catalogues factices en ``tmp_path``
(comme ``test_interruption``) : un plugin qui se charge mal ne se voit pas dans
un test qui simule pytest. Aucun lab réel n'est joué.

Chaque comportement est joué dans les deux sens : ce qui doit être produit, et
ce qui doit rester inconnu (``criteres is None``) quand le rapport est douteux.
"""

from __future__ import annotations

import ast
import os
import stat
import sys
import tempfile
import textwrap
from pathlib import Path
from typing import Any

import pytest

from dsoxlab.models.lab import (
    LabDefinition,
    RuntimeConfig,
    RuntimeType,
    ValidationConfig,
)
from dsoxlab.services import lab_service
from dsoxlab.services.lab_service import CheckResult, check_lab, echecs_de_tests
from dsoxlab.services.rapport_de_criteres import (
    IDENTIFIANT_MAX,
    MESSAGE_MAX,
    PLUGIN,
    ResultatDeCritere,
    identifiants_de_criteres,
    lire_rapport,
    repertoire_du_plugin,
)

# ── un catalogue factice ──────────────────────────────────────────────────


def _lab(
    racine: Path,
    tests: dict[str, str],
    *,
    pytest_ini: str | None = None,
    conftest: str | None = None,
) -> LabDefinition:
    """Un lab de ``racine``, dont ``tests`` donne les fichiers sous challenge/tests/."""
    racine.mkdir(parents=True, exist_ok=True)
    (racine / "meta.yml").write_text(
        "repo:\n  id: rapport-test\n  category: demo\n", encoding="utf-8"
    )
    if pytest_ini is not None:
        (racine / "pytest.ini").write_text(pytest_ini, encoding="utf-8")
    if conftest is not None:
        (racine / "conftest.py").write_text(conftest, encoding="utf-8")
    lab_dir = racine / "labs" / "demo" / "premier"
    for nom, contenu in tests.items():
        cible = lab_dir / "challenge" / "tests" / nom
        cible.parent.mkdir(parents=True, exist_ok=True)
        cible.write_text(textwrap.dedent(contenu), encoding="utf-8")
    return LabDefinition(
        id="premier",
        title="Premier",
        level="l1",
        skills=["s"],
        runtime=RuntimeConfig(type=RuntimeType.SHELL, workdir="challenge/work"),
        distros=["alma10"],
        doc_url="https://example.test/doc",
        validation=ValidationConfig(),
        path=lab_dir,
    )


def _par_id(resultat: CheckResult) -> dict[str, ResultatDeCritere]:
    assert resultat.criteres is not None, resultat.output
    return {c.identifiant: c for c in resultat.criteres}


@pytest.fixture(autouse=True)
def _pas_de_rapport_herite(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("DSOXLAB_RAPPORT", raising=False)


# ── ce que le rapport dit ─────────────────────────────────────────────────


def test_deux_tests_parametres_en_echec_donnent_deux_criteres(tmp_path: Path) -> None:
    lab = _lab(tmp_path / "depot", {"test_functional.py": """\
        import pytest

        @pytest.mark.parametrize("n", [1, 2, 3])
        def test_pair(n):
            assert n % 2 == 0, f"Le nombre {n} doit etre pair."
        """})

    resultat = check_lab(lab)
    criteres = _par_id(resultat)

    assert sorted(criteres) == ["test_pair[1]", "test_pair[2]", "test_pair[3]"]
    assert criteres["test_pair[1]"].etat == "unsatisfied"
    assert criteres["test_pair[3]"].etat == "unsatisfied"
    assert criteres["test_pair[2]"].etat == "satisfied"
    # Le message est celui de l'AUTEUR, coupé avant l'explication de pytest.
    assert criteres["test_pair[1]"].origine_message == "author"
    assert criteres["test_pair[1]"].message_auteur == "Le nombre 1 doit etre pair."
    assert criteres["test_pair[1]"].nodeid.endswith("test_functional.py::test_pair[1]")
    assert criteres["test_pair[1]"].phase == "call"


def test_une_fixture_en_echec_n_evalue_pas_le_critere(tmp_path: Path) -> None:
    lab = _lab(tmp_path / "depot", {"test_functional.py": """\
        import pytest

        @pytest.fixture
        def socle():
            raise RuntimeError("le socle n'a pas demarre")

        def test_depend_du_socle(socle):
            assert True

        def test_independant():
            assert False, "Cree le fichier."
        """})

    criteres = _par_id(check_lab(lab))

    assert criteres["test_depend_du_socle"].etat == "not_evaluated"
    assert criteres["test_depend_du_socle"].phase == "setup"
    # Le texte d'une exception technique n'est JAMAIS conservé.
    assert criteres["test_depend_du_socle"].message_auteur is None
    assert criteres["test_independant"].etat == "unsatisfied"


def test_un_echec_au_teardown_d_un_test_reussi_reste_satisfait(tmp_path: Path) -> None:
    lab = _lab(tmp_path / "depot", {"test_functional.py": """\
        import pytest

        @pytest.fixture
        def nettoyage():
            yield
            raise RuntimeError("le nettoyage a echoue")

        def test_reussi(nettoyage):
            assert True

        def test_rate(nettoyage):
            assert False, "Rate."
        """})

    criteres = _par_id(check_lab(lab))

    assert criteres["test_reussi"].etat == "satisfied"
    assert criteres["test_reussi"].mention == "teardown_error"
    # Un test raté ne devient pas satisfait parce que son nettoyage a échoué aussi.
    assert criteres["test_rate"].etat == "unsatisfied"
    assert criteres["test_rate"].mention == "teardown_error"


def test_une_erreur_de_collecte_ne_s_evalue_pas(tmp_path: Path) -> None:
    lab = _lab(tmp_path / "depot", {
        "test_functional.py": "def test_ok():\n    assert True\n",
        "test_casse.py": "import module_qui_n_existe_pas\n",
    })

    resultat = check_lab(lab)
    collecte = [c for c in (resultat.criteres or ()) if c.phase == "collect"]

    assert len(collecte) == 1
    assert collecte[0].etat == "not_evaluated"
    assert collecte[0].message_auteur is None


def test_l_origine_du_message_distingue_l_auteur_du_technique(tmp_path: Path) -> None:
    lab = _lab(tmp_path / "depot", {"test_functional.py": """\
        import pytest

        def test_message_auteur():
            assert 1 == 2, "Ligne un.\\nLigne deux."

        def test_assertion_nue():
            assert 1 == 2

        def test_pytest_fail():
            pytest.fail("Echec voulu par l'auteur.")

        def test_exception_technique():
            raise KeyError("detail interne")
        """})

    criteres = _par_id(check_lab(lab))

    assert criteres["test_message_auteur"].message_auteur == "Ligne un.\nLigne deux."
    assert criteres["test_assertion_nue"].origine_message == "technical"
    assert criteres["test_assertion_nue"].message_auteur is None
    assert criteres["test_pytest_fail"].origine_message == "author"
    assert criteres["test_pytest_fail"].message_auteur == "Echec voulu par l'auteur."
    assert criteres["test_exception_technique"].origine_message == "technical"
    assert criteres["test_exception_technique"].message_auteur is None


def test_le_message_de_l_auteur_est_borne(tmp_path: Path) -> None:
    lab = _lab(tmp_path / "depot", {"test_functional.py": """\
        def test_long():
            assert False, "x" * 5000
        """})

    critere = _par_id(check_lab(lab))["test_long"]

    assert critere.message_auteur is not None
    assert len(critere.message_auteur) == MESSAGE_MAX


def test_le_mode_flux_remplit_aussi_les_criteres(tmp_path: Path) -> None:
    lab = _lab(tmp_path / "depot", {"test_functional.py": """\
        def test_un():
            assert True

        def test_deux():
            assert False, "Deux."
        """})
    evenements: list[dict[str, Any]] = []

    resultat = check_lab(lab, on_event=evenements.append)

    criteres = _par_id(resultat)
    assert criteres["test_un"].etat == "satisfied"
    assert criteres["test_deux"].etat == "unsatisfied"
    assert any(e["type"] == "verdict" for e in evenements)


# ── les identifiants ──────────────────────────────────────────────────────


def test_deux_fonctions_homonymes_dans_deux_fichiers_restent_distinctes(
    tmp_path: Path,
) -> None:
    """Le choix documenté : en cas de collision, on regagne le chemin, pour TOUS.

    Le chemin remplace ``/`` par ``_`` (jeu ``[\\p{L}\\p{N}_.:\\[\\]-]``). Les
    DEUX membres du groupe le regagnent, pour que l'identifiant ne dépende pas
    de l'ordre d'exécution.
    """
    lab = _lab(tmp_path / "depot", {
        "a/test_functional.py": "def test_meme_nom():\n    assert False, 'A'\n",
        "b/test_functional.py": "def test_meme_nom():\n    assert False, 'B'\n",
        "c/test_functional.py": "def test_seul():\n    assert True\n",
    }, pytest_ini="[pytest]\naddopts = --import-mode=importlib\n")

    resultat = check_lab(lab)
    criteres = _par_id(resultat)

    assert len(criteres) == 3
    homonymes = [i for i in criteres if i.endswith("::test_meme_nom")]
    assert len(homonymes) == 2 and len(set(homonymes)) == 2
    assert any("/" not in i and "a_test_functional.py" in i for i in homonymes)
    assert any("b_test_functional.py" in i for i in homonymes)
    # Sans collision, l'identifiant reste le nodeid sans chemin.
    assert "test_seul" in criteres
    assert {criteres[i].message_auteur for i in homonymes} == {"A", "B"}


def test_identifiants_sans_collision_privent_le_nodeid_de_son_chemin() -> None:
    identifiants = identifiants_de_criteres([
        "labs/x/challenge/tests/test_functional.py::test_a",
        "labs/x/challenge/tests/test_functional.py::TestC::test_b[p-1]",
    ])
    assert list(identifiants.values()) == ["test_a", "TestC::test_b[p-1]"]


def test_identifiants_assainis_et_bornes() -> None:
    sale = "t.py::test_x[é/ü ça\t'\"<>;]"
    long = "t.py::test_" + "z" * 300
    identifiants = identifiants_de_criteres([sale, long])

    assert identifiants[sale] == "test_x[é_ü_ça______]"
    assert len(identifiants[long]) == IDENTIFIANT_MAX
    import re

    for ident in identifiants.values():
        assert re.fullmatch(r"[\w.:\[\]-]+", ident), ident


def test_collision_residuelle_departagee_par_un_suffixe() -> None:
    """Deux nodeids qui ne diffèrent qu'après la coupe à 128 restent distincts."""
    base = "d/t.py::test_" + "a" * 200
    identifiants = identifiants_de_criteres([base + "1", base + "2"])
    assert len(set(identifiants.values())) == 2
    assert all(len(i) <= IDENTIFIANT_MAX for i in identifiants.values())


# ── un rapport douteux est INCONNU, jamais « zéro critère » ───────────────

_ENTETE = '{"t": "debut", "v": 1}\n'
_PHASE = (
    '{"t": "phase", "nodeid": "d/t.py::test_a", "phase": "call", '
    '"issue": "passed", "origine": null, "message": null}\n'
)
_FIN = '{"t": "fin"}\n'


@pytest.mark.parametrize(
    ("contenu", "attendu_inconnu"),
    [
        (None, True),  # fichier absent
        ("", True),  # vide : pytest n'a jamais démarré
        (_ENTETE + _PHASE, True),  # pas de ligne de fin : pytest interrompu
        (_ENTETE + _PHASE + "{pas du json\n" + _FIN, True),  # ligne corrompue
        (_ENTETE + "[1, 2]\n" + _FIN, True),  # ligne qui n'est pas un objet
        (_ENTETE + '{"t": "inconnu"}\n' + _FIN, True),  # genre inconnu
        (_ENTETE + '{"t": "phase", "phase": "call"}\n' + _FIN, True),  # champ manquant
        (_ENTETE + _PHASE + _FIN, False),
        (_ENTETE + _FIN, False),  # session sans test : zéro critère, c'est CONNU
    ],
)
def test_lecture_du_rapport(
    tmp_path: Path, contenu: str | None, attendu_inconnu: bool
) -> None:
    chemin = tmp_path / "rapport.jsonl"
    if contenu is not None:
        chemin.write_text(contenu, encoding="utf-8")

    lu = lire_rapport(chemin)

    assert (lu is None) is attendu_inconnu


def test_un_rapport_binaire_est_inconnu(tmp_path: Path) -> None:
    chemin = tmp_path / "rapport.jsonl"
    chemin.write_bytes(b"\xff\xfe\x00\x01")
    assert lire_rapport(chemin) is None


def test_rapport_corrompu_par_le_catalogue_garde_le_chemin_texte(tmp_path: Path) -> None:
    """Un conftest qui écrase le rapport après la session : ``criteres`` est None."""
    conftest = """\
        import os

        def pytest_unconfigure(config):
            chemin = os.environ.get("DSOXLAB_RAPPORT")
            if chemin:
                with open(chemin, "w") as f:
                    f.write("{ceci n'est pas du json")
        """
    tests = {"test_functional.py": """\
        def test_un():
            assert True

        def test_deux():
            assert False, "Cree le fichier."
        """}
    corrompu = check_lab(_lab(tmp_path / "a", tests, conftest=textwrap.dedent(conftest)))
    sain = check_lab(_lab(tmp_path / "b", tests))

    assert corrompu.criteres is None
    assert sain.criteres is not None
    # Le chemin texte est celui d'avant : mêmes comptes, mêmes échecs nommés.
    assert (corrompu.passed, corrompu.total, corrompu.ok) == (sain.passed, sain.total, sain.ok)
    assert [e.nom for e in echecs_de_tests(corrompu.output)] == ["test_deux"]
    assert [e.message for e in echecs_de_tests(corrompu.output)] == ["Cree le fichier."]


# ── rien ne change pour le reste ──────────────────────────────────────────


def test_le_texte_et_les_comptes_restent_ceux_de_pytest(tmp_path: Path) -> None:
    lab = _lab(tmp_path / "depot", {"test_functional.py": """\
        import pytest

        def test_un():
            assert True

        def test_deux():
            assert False, "Deux a refaire."

        @pytest.mark.skip(reason="r")
        def test_trois():
            assert True
        """})

    resultat = check_lab(lab)

    assert (resultat.passed, resultat.total, resultat.skipped, resultat.ok) == (1, 3, 1, False)
    assert [e.nom for e in echecs_de_tests(resultat.output)] == ["test_deux"]
    criteres = _par_id(resultat)
    assert criteres["test_trois"].etat == "skipped"
    # Le plugin n'ajoute rien à ce que l'apprenant lit.
    assert "dsoxlab_rapport" not in resultat.output


def test_check_result_a_la_main_n_a_pas_de_criteres() -> None:
    assert CheckResult(ok=True, output="", passed=1, total=1).criteres is None


# ── les façons de lancer pytest ───────────────────────────────────────────


def _lanceur(tmp_path: Path, nom: str, corps: str) -> Path:
    script = tmp_path / nom
    script.write_text(f"#!{sys.executable}\n{textwrap.dedent(corps)}", encoding="utf-8")
    script.chmod(script.stat().st_mode | stat.S_IXUSR)
    return script


_TESTS_SIMPLES = {"test_functional.py": """\
    def test_un():
        assert True

    def test_deux():
        assert False, "Deux."
    """}


def test_lancement_par_le_pytest_du_venv(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Forme 2 de ``resolve_pytest_cmd`` : un exécutable ``pytest`` seul."""
    lanceur = _lanceur(tmp_path, "pytest", """\
        import sys
        import pytest
        sys.exit(pytest.console_main())
        """)
    monkeypatch.setattr(lab_service, "resolve_pytest_cmd", lambda _racine: [str(lanceur)])

    resultat = check_lab(_lab(tmp_path / "depot", _TESTS_SIMPLES))

    assert _par_id(resultat)["test_deux"].etat == "unsatisfied"


def test_lancement_par_un_uv_run_qui_relaie_le_pythonpath(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Forme 3 : ``uv run --quiet pytest``, simulé par un lanceur qui relaie l'environnement.

    ``uv run`` hérite de l'environnement du parent, ``PYTHONPATH`` compris : le
    simulacre fait de même, sans réseau ni cache uv.
    """
    lanceur = _lanceur(tmp_path, "uv", f"""\
        import os
        import sys
        assert sys.argv[1:3] == ["run", "--quiet"], sys.argv
        os.execv({sys.executable!r}, [{sys.executable!r}, "-m", *sys.argv[3:]])
        """)
    monkeypatch.setattr(
        lab_service, "resolve_pytest_cmd",
        lambda _racine: [str(lanceur), "run", "--quiet", "pytest"],
    )

    resultat = check_lab(_lab(tmp_path / "depot", _TESTS_SIMPLES))

    assert _par_id(resultat)["test_deux"].etat == "unsatisfied"


def test_un_lanceur_qui_ecrase_le_pythonpath_ne_casse_pas_le_check(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Le plugin est introuvable : pytest échoue. Le check rejoue SANS lui."""
    lanceur = _lanceur(tmp_path, "pytest", f"""\
        import os
        import sys
        env = dict(os.environ)
        env.pop("PYTHONPATH", None)
        os.execve({sys.executable!r}, [{sys.executable!r}, "-m", "pytest", *sys.argv[1:]], env)
        """)
    monkeypatch.setattr(lab_service, "resolve_pytest_cmd", lambda _racine: [str(lanceur)])
    tests = _TESTS_SIMPLES

    en_bloc = check_lab(_lab(tmp_path / "a", tests))
    en_flux = check_lab(_lab(tmp_path / "b", tests), on_event=lambda _e: None)

    for resultat in (en_bloc, en_flux):
        assert resultat.criteres is None
        assert (resultat.passed, resultat.total, resultat.ok) == (1, 2, False)
        assert "dsoxlab_rapport" not in resultat.output


# ── l'étanchéité avec les catalogues ──────────────────────────────────────


def test_un_catalogue_qui_declare_un_marqueur_en_strict_n_est_pas_casse(
    tmp_path: Path,
) -> None:
    conftest = """\
        def pytest_configure(config):
            config.addinivalue_line("markers", "reseau: besoin du reseau")
        """
    lab = _lab(
        tmp_path / "depot",
        {"test_functional.py": """\
            import pytest

            @pytest.mark.reseau
            def test_marque():
                assert True
            """},
        pytest_ini="[pytest]\naddopts = --strict-markers\n",
        conftest=textwrap.dedent(conftest),
    )

    resultat = check_lab(lab)

    assert (resultat.ok, resultat.passed, resultat.total) == (True, 1, 1)
    assert _par_id(resultat)["test_marque"].etat == "satisfied"


def test_le_mode_d_import_importlib_du_catalogue_pilote_est_honore(tmp_path: Path) -> None:
    """``--import-mode=importlib`` : tous les labs ont un ``test_functional.py``."""
    lab = _lab(
        tmp_path / "depot",
        {"test_functional.py": "def test_un():\n    assert True\n"},
        pytest_ini="[pytest]\naddopts = --import-mode=importlib\n",
    )

    resultat = check_lab(lab)

    assert resultat.ok and _par_id(resultat)["test_un"].etat == "satisfied"


def test_le_plugin_est_inerte_sans_la_variable(tmp_path: Path) -> None:
    """Chargé sans ``DSOXLAB_RAPPORT``, il n'écrit rien et ne change aucun verdict."""
    import subprocess

    test = tmp_path / "test_x.py"
    test.write_text("def test_ok():\n    assert True\n", encoding="utf-8")
    env = {k: v for k, v in os.environ.items() if k != "DSOXLAB_RAPPORT"}
    env["PYTHONPATH"] = str(repertoire_du_plugin())

    termine = subprocess.run(
        [sys.executable, "-m", "pytest", "-p", PLUGIN, "-q", str(test)],
        cwd=tmp_path, env=env, capture_output=True, text=True, check=False,
    )

    assert termine.returncode == 0, termine.stdout + termine.stderr
    assert list(tmp_path.glob("*.jsonl")) == []


def test_le_rapport_vit_dans_un_repertoire_temporaire_retire(tmp_path: Path) -> None:
    lab = _lab(tmp_path / "depot", _TESTS_SIMPLES)
    avant = set(Path(tempfile.gettempdir()).glob("dsoxlab-rapport-*"))

    check_lab(lab)

    apres = set(Path(tempfile.gettempdir()).glob("dsoxlab-rapport-*"))
    assert apres <= avant, "le répertoire du rapport doit être retiré à la fin du check"


def test_le_plugin_n_importe_pas_dsoxlab() -> None:
    """Module autonome : il tourne dans le pytest d'un autre environnement."""
    source = (repertoire_du_plugin() / f"{PLUGIN}.py").read_text(encoding="utf-8")
    importes: set[str] = set()
    for noeud in ast.walk(ast.parse(source)):
        if isinstance(noeud, ast.Import):
            importes |= {a.name.split(".")[0] for a in noeud.names}
        elif isinstance(noeud, ast.ImportFrom) and noeud.module:
            importes.add(noeud.module.split(".")[0])
    assert "dsoxlab" not in importes
    assert importes <= {"__future__", "json", "os", "contextlib", "pathlib", "typing", "pytest"}
