"""Les quatre défauts du lot 0.8.1 où un comportement contredisait un autre.

Ce que ces tests défendent, et pourquoi ils n'existaient pas avant : chacun des
quatre défauts est une INCOHÉRENCE entre deux chemins du même moteur, et aucun
des deux chemins n'était faux en lui-même. C'est exactement ce qu'une suite
organisée par fonction ne voit pas, puisque chaque fonction, mesurée seule,
donne le résultat qu'on attend d'elle.

- #349 : `submit` sortait en 0 sur une épreuve refusée, quand `check` sortait
  en 1 sur le même lab.
- #351 : `clean` arrêtait les services du lab, `reset` les laissait tourner,
  alors qu'il se décrit comme « clean + start ».
- #352 : un lab `vm` sans `setup.yaml` ou `cleanup.yaml` disait sa phrase, mais
  emballée dans un second message (« Fichier introuvable : « … » »).
- #354 : `clean` et `reset` nommaient `--yes` hors terminal, `destroy` répondait
  « Aborted. » en code 1.

Aucun de ces tests ne lit un rendu Rich : ils lisent un code de sortie, le type
d'une exception, ou la trace des appels faits au module des services.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import typer
from typer.testing import CliRunner

from dsoxlab.cli import app, destruction
from dsoxlab.models.lab import LabDefinition

_BASE = """\
id: lab-a
title: Demo lab
level: beginner
skills: [demo]
distros: [any]
doc_url: https://example.org/docs/demo/
"""

_META = """\
repo:
  id: depot-demo
  category: demo
infra:
  provider: kvm
  network: lab-demo
  hosts:
    - name: n1.lab
      distro: debian13
"""


def _catalogue(racine: Path, *, runtime: str, services: bool = False) -> Path:
    """Un catalogue d'un seul lab, dont le runtime et les services se choisissent."""
    (racine / "labs" / "demo" / "lab-a" / "challenge" / "tests").mkdir(parents=True)
    (racine / "meta.yml").write_text(_META, encoding="utf-8")
    bloc = _BASE
    if runtime == "shell":
        bloc += "runtime:\n  type: shell\n  workdir: challenge/work\n"
    else:
        bloc += (
            "runtime:\n  type: vm\n"
            "  targets:\n    - name: cible\n      host: n1.lab\n"
        )
    if services:
        bloc += "  services:\n    - name: db\n      image: postgres:16\n"
    lab = racine / "labs" / "demo" / "lab-a"
    (lab / "lab.yaml").write_text(bloc, encoding="utf-8")
    (lab / "README.md").write_text("# lab-a\n", encoding="utf-8")
    (lab / "scenario.md").write_text("scenario\n", encoding="utf-8")
    (lab / "challenge" / "tests" / "test_functional.py").write_text(
        "def test_ok():\n    assert True\n", encoding="utf-8"
    )
    return racine


@pytest.fixture(autouse=True)
def _poste_isole(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Aucun de ces tests ne touche l'état de la machine qui les exécute."""
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "state"))
    monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path / "cache"))
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "data"))
    monkeypatch.setenv("DSOXLAB_LANG", "en")
    monkeypatch.delenv("LAB_HOME", raising=False)


# ── #349 : submit et check disent la même chose ───────────────────────────────


class TestLeCodeDeSortieDeSubmit:
    """Le verdict à l'écran et le code de sortie ne peuvent pas diverger."""

    def _submit(self, racine: Path, monkeypatch: pytest.MonkeyPatch,
                resultat: tuple[object, int, int]) -> int:
        # Sur `progression` : `submit` a importé `_run_check` par son nom au
        # chargement du module, donc c'est ce binding-là qu'il appelle. Posé sur
        # `_validation`, le simulacre est inerte et le vrai pytest tourne.
        from dsoxlab.cli import progression

        monkeypatch.setattr(progression, "_run_check", lambda *a, **k: resultat)
        return CliRunner().invoke(
            app, ["submit", "lab-a", "--lab-home", str(racine)]
        ).exit_code

    def test_des_tests_en_echec_sortent_en_1(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from dsoxlab.services.lab_service import CheckResult

        racine = _catalogue(tmp_path / "d", runtime="shell")
        code = self._submit(
            racine, monkeypatch, (CheckResult(False, "", 2, 5), 40, 100)
        )
        assert code == 1, "une soumission non reçue sort en succès"

    def test_une_epreuve_refusee_sort_en_1(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Le cas de l'issue : un refus affiché, suivi d'un code 0."""
        from dsoxlab.services.lab_service import CheckResult

        racine = _catalogue(tmp_path / "d", runtime="shell")
        lab_yaml = racine / "labs" / "demo" / "lab-a" / "lab.yaml"
        lab_yaml.write_text(
            lab_yaml.read_text(encoding="utf-8")
            + "lab_type: challenge\nexam_passing_score: 70\n",
            encoding="utf-8",
        )
        code = self._submit(
            racine, monkeypatch, (CheckResult(False, "", 2, 5), 40, 100)
        )
        assert code == 1

    def test_une_soumission_recue_sort_toujours_en_0(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Le contre-exemple, sans lequel les deux précédents passeraient à vide."""
        from dsoxlab.services.lab_service import CheckResult

        racine = _catalogue(tmp_path / "d", runtime="shell")
        code = self._submit(
            racine, monkeypatch, (CheckResult(True, "", 5, 5), 100, 100)
        )
        assert code == 0


# ── #351 : reset repart d'un service neuf ─────────────────────────────────────


class TestResetEtLesServices:
    """`reset` se décrit comme « clean + start » : il doit emporter les services."""

    def _reset(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, *, services: bool
    ) -> list[str]:
        """Joue `reset --yes` et rend la trace des gestes faits sur les services."""
        from dsoxlab.cli import progression
        from dsoxlab.runtimes import services as svc

        racine = _catalogue(tmp_path / "d", runtime="shell", services=services)
        gestes: list[str] = []
        monkeypatch.setattr(svc, "docker_available", lambda: True)
        monkeypatch.setattr(
            svc, "stop", lambda service, repo: gestes.append("stop") is None
        )
        monkeypatch.setattr(
            svc, "start",
            lambda service, repo, **kw: gestes.append("start") or "conteneur",
        )
        # La préparation elle-même n'est pas le sujet : elle est remplacée pour
        # que le test mesure le cycle de vie des services, et lui seul.
        monkeypatch.setattr(progression, "reset_lab", lambda *a, **k: None)

        resultat = CliRunner().invoke(
            app, ["reset", "lab-a", "--yes", "--lab-home", str(racine)]
        )
        assert resultat.exit_code == 0, resultat.output
        return gestes

    def test_reset_arrete_puis_recree_les_services_declares(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """L'ordre compte : arrêter PUIS redémarrer, avant la préparation.

        S'arrêter à l'arrêt laisserait le `setup.yaml` du lab parler à un
        service absent, alors qu'il le trouvait debout jusqu'ici.
        """
        assert self._reset(tmp_path, monkeypatch, services=True) == ["stop", "start"]

    def test_un_lab_sans_service_ne_touche_a_aucun_conteneur(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Le contre-exemple : un lab qui n'en déclare pas ne doit rien voir."""
        assert self._reset(tmp_path, monkeypatch, services=False) == []


# ── #352 : la phrase du contrat, et rien autour ───────────────────────────────


class TestLeMessageDUnLabVmIncomplet:
    """Un message emballé dans un autre est un message qu'on lit deux fois."""

    def _lab_vm(self, tmp_path: Path) -> LabDefinition:
        racine = _catalogue(tmp_path / "d", runtime="vm")
        return LabDefinition.from_yaml(
            racine / "labs" / "demo" / "lab-a" / "lab.yaml"
        )

    def test_un_setup_absent_leve_une_runtime_error(self, tmp_path: Path) -> None:
        """`FileNotFoundError` partait dans le filet générique de `_socle`.

        Celui-ci n'a que le texte de l'exception à montrer, faute de
        `filename` : il le repliait donc dans « Fichier introuvable : « … » ».
        """
        from dsoxlab.runtimes.vm import VmRuntime

        with pytest.raises(RuntimeError) as leve:
            VmRuntime().start(self._lab_vm(tmp_path), "cible")
        assert "setup.yaml" in str(leve.value)
        assert not isinstance(leve.value, FileNotFoundError), (
            "une FileNotFoundError se fait emballer par le filet de _socle"
        )

    def test_un_cleanup_absent_leve_une_runtime_error(self, tmp_path: Path) -> None:
        from dsoxlab.runtimes.vm import VmRuntime

        with pytest.raises(RuntimeError) as leve:
            VmRuntime().clean(self._lab_vm(tmp_path), "cible")
        assert "cleanup.yaml" in str(leve.value)
        assert not isinstance(leve.value, FileNotFoundError)

    def test_la_commande_sort_en_2_sur_la_phrase_du_contrat(
        self, tmp_path: Path
    ) -> None:
        """Vu depuis la CLI : le code attendu, et un seul message."""
        racine = _catalogue(tmp_path / "d", runtime="vm")
        resultat = CliRunner().invoke(
            app, ["clean", "lab-a", "--yes", "--lab-home", str(racine)]
        )
        assert resultat.exit_code == 2, resultat.output


# ── #354 : destroy demande comme clean demande ────────────────────────────────


class TestLaConfirmationDeDestroy:
    """« Aborted. » ne dit ni la cause, ni le geste, ni le bon code."""

    def test_hors_terminal_destroy_nomme_la_cause_et_sort_en_2(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from dsoxlab.cli import _commun

        dits: list[str] = []
        monkeypatch.setattr(_commun.sys.stdin, "isatty", lambda: False)
        monkeypatch.setattr(_commun, "error", dits.append)
        monkeypatch.setattr(
            _commun.typer, "confirm",
            lambda *a, **k: pytest.fail("une question a été posée sans terminal"),
        )

        with pytest.raises(typer.Exit) as sortie:
            destruction._confirmer("confirm_destroy", provider="kvm")

        assert sortie.value.exit_code == 2
        assert dits and "--yes" in dits[0], (
            "le refus ne nomme pas l'option qui le débloque"
        )

    def test_hors_terminal_une_question_ouverte_rend_non_sans_se_taire(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Le retrait des machines restées : refusé, et dit, jamais supposé oui.

        Un « oui » deviné dé-définirait des domaines homonymes que rien ne
        garantit être ceux de ce dépôt.
        """
        from dsoxlab.cli import _commun

        dits: list[str] = []
        monkeypatch.setattr(_commun.sys.stdin, "isatty", lambda: False)
        monkeypatch.setattr(_commun, "error", dits.append)

        assert destruction._demander("confirm_destroy_orphans") is False
        assert dits, "le refus est sorti sans un mot"
