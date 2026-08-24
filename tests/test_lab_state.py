"""L'état d'un lab, et le chemin qui y mène (issue #80).

« Où en suis-je ? » n'avait pas de réponse : l'état existait, éparpillé entre un
JSON, une base SQLite, un répertoire de travail et Docker. Ce module éprouve la
fonction qui le calcule, **une transition par test**, et surtout ce qui les
sépare :

- *prêt* et *en cours* ne diffèrent que par le contenu du répertoire de travail,
  comparé au point de départ que `run` a retenu ;
- *validé* prime sur les deux, une note obtenue ne se perdant pas ;
- *dégradé* prime sur tout, parce que c'est le seul état qui appelle un geste
  immédiat.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from dsoxlab.models.lab import LabDefinition
from dsoxlab.services import lab_state
from dsoxlab.sessions import store

_BASE = """\
id: l1-demo
title: Demo lab
level: beginner
skills: [demo]
distros: [any]
doc_url: https://example.org/docs/demo/
"""


@pytest.fixture(autouse=True)
def xdg_jetable(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """Les empreintes vont sous XDG : aucun test n'écrit dans le vrai ~/.local."""
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "state"))
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "data"))


def _depot(tmp_path: Path) -> Path:
    racine = tmp_path / "catalogue"
    (racine / "labs").mkdir(parents=True, exist_ok=True)
    (racine / "meta.yml").write_text(
        "repo:\n  id: essai\n  category: essai\n", encoding="utf-8")
    return racine


def _lab_shell(tmp_path: Path, *, workdir: str = "challenge/work") -> LabDefinition:
    racine = _depot(tmp_path) / "labs" / "l1-demo"
    racine.mkdir(parents=True, exist_ok=True)
    (racine / "lab.yaml").write_text(
        _BASE + f"runtime:\n  type: shell\n  workdir: {workdir}\n", encoding="utf-8")
    return LabDefinition.from_yaml(racine / "lab.yaml")


def _lab_vm(tmp_path: Path) -> LabDefinition:
    racine = _depot(tmp_path) / "labs" / "l1-demo"
    racine.mkdir(parents=True, exist_ok=True)
    (racine / "lab.yaml").write_text(
        _BASE
        + "runtime:\n  type: vm\n  targets:\n    - name: t\n      host: h.lab\n",
        encoding="utf-8",
    )
    return LabDefinition.from_yaml(racine / "lab.yaml")


# ── Les transitions, une par test ───────────────────────────────────────────

def test_sans_rien_le_lab_n_est_pas_encore_commence(tmp_path: Path) -> None:
    lab = _lab_shell(tmp_path)
    etat = lab_state.calculer(_depot(tmp_path), lab, "essai")

    assert etat.state == lab_state.NOT_STARTED
    assert lab.id in etat.detail, "le message doit nommer le lab à lancer"


def test_apres_run_le_lab_est_pret(tmp_path: Path) -> None:
    racine = _depot(tmp_path)
    lab = _lab_shell(tmp_path)
    (lab.path / "challenge" / "work").mkdir(parents=True)
    lab_state.enregistrer_depart(racine, lab)

    assert lab_state.calculer(racine, lab, "essai").state == lab_state.READY


def test_un_travail_touche_fait_passer_en_cours(tmp_path: Path) -> None:
    """La distinction qui motive tout le mécanisme.

    Un répertoire de travail existe dès que `run` l'a créé : sans point de
    départ, « en cours » serait indistinguable de « prêt ».
    """
    racine = _depot(tmp_path)
    lab = _lab_shell(tmp_path)
    travail = lab.path / "challenge" / "work"
    travail.mkdir(parents=True)
    (travail / "main.tf").write_text("resource {}\n", encoding="utf-8")
    lab_state.enregistrer_depart(racine, lab)

    assert lab_state.calculer(racine, lab, "essai").state == lab_state.READY

    (travail / "main.tf").write_text("resource { modifie }\n", encoding="utf-8")

    assert lab_state.calculer(racine, lab, "essai").state == lab_state.IN_PROGRESS


def test_un_fichier_ajoute_compte_comme_du_travail(tmp_path: Path) -> None:
    racine = _depot(tmp_path)
    lab = _lab_shell(tmp_path)
    travail = lab.path / "challenge" / "work"
    travail.mkdir(parents=True)
    lab_state.enregistrer_depart(racine, lab)

    (travail / "reponse.txt").write_text("ma réponse\n", encoding="utf-8")

    assert lab_state.calculer(racine, lab, "essai").state == lab_state.IN_PROGRESS


def test_une_note_obtenue_vaut_valide(tmp_path: Path) -> None:
    racine = _depot(tmp_path)
    lab = _lab_shell(tmp_path)
    (lab.path / "challenge" / "work").mkdir(parents=True)
    lab_state.enregistrer_depart(racine, lab)
    store.record_result(racine, lab_id=lab.id, section="essai",
                        score=80, max_score=100,
                        passed_tests=4, total_tests=5,
                        hints_used=0)

    etat = lab_state.calculer(racine, lab, "essai")

    assert etat.state == lab_state.VALIDATED
    assert etat.best_score == 80 and etat.max_score == 100


def test_valide_prime_sur_le_travail_en_cours(tmp_path: Path) -> None:
    """Une note ne se perd pas parce qu'on retouche ensuite au travail."""
    racine = _depot(tmp_path)
    lab = _lab_shell(tmp_path)
    travail = lab.path / "challenge" / "work"
    travail.mkdir(parents=True)
    lab_state.enregistrer_depart(racine, lab)
    store.record_result(racine, lab_id=lab.id, section="essai",
                        score=80, max_score=100,
                        passed_tests=4, total_tests=5,
                        hints_used=0)
    (travail / "encore.txt").write_text("je continue\n", encoding="utf-8")

    assert lab_state.calculer(racine, lab, "essai").state == lab_state.VALIDATED


def test_un_service_tombe_rend_le_lab_degrade(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Le seul état qui appelle un geste immédiat prime sur tous les autres."""
    racine = _depot(tmp_path) / "labs" / "l1-demo"
    racine.mkdir(parents=True, exist_ok=True)
    (racine / "lab.yaml").write_text(
        _BASE
        + "runtime:\n  type: shell\n  workdir: challenge/work\n"
        + "  services:\n    - name: db\n      image: postgres:16\n",
        encoding="utf-8",
    )
    lab = LabDefinition.from_yaml(racine / "lab.yaml")
    depot = _depot(tmp_path)
    store.record_result(depot, lab_id=lab.id, section="essai",
                        score=100, max_score=100,
                        passed_tests=5, total_tests=5,
                        hints_used=0)

    from dsoxlab.runtimes import services as svc

    monkeypatch.setattr(svc, "docker_available", lambda: True)
    monkeypatch.setattr(svc, "status", lambda service, repo: svc.ServiceStatus(
        name=service.name, container="c", running=False, detail="stopped"))

    etat = lab_state.calculer(depot, lab, "essai")

    assert etat.state == lab_state.DEGRADED
    assert "db" in etat.detail, "le message doit nommer le service tombé"


def test_un_service_jamais_demarre_n_est_pas_une_degradation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    """`absent` veut dire « pas encore lancé », pas « tombé ».

    Les confondre ferait virer au rouge tout lab à service jamais démarré,
    c'est-à-dire le cas normal avant le premier `run`.
    """
    racine = _depot(tmp_path) / "labs" / "l1-demo"
    racine.mkdir(parents=True, exist_ok=True)
    (racine / "lab.yaml").write_text(
        _BASE
        + "runtime:\n  type: shell\n  workdir: challenge/work\n"
        + "  services:\n    - name: db\n      image: postgres:16\n",
        encoding="utf-8",
    )
    lab = LabDefinition.from_yaml(racine / "lab.yaml")

    from dsoxlab.runtimes import services as svc

    monkeypatch.setattr(svc, "docker_available", lambda: True)
    monkeypatch.setattr(svc, "status", lambda service, repo: svc.ServiceStatus(
        name=service.name, container="c", running=False, detail="absent"))

    assert lab_state.calculer(_depot(tmp_path), lab, "essai").state != lab_state.DEGRADED


def test_docker_absent_degrade_un_lab_qui_declare_des_services(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Le renversement de #179, gardé explicite plutôt que discrètement effacé.

    Ce test affirmait l'inverse : « une machine sans Docker n'est pas un lab
    cassé : on ne sait simplement rien. » L'intention était juste, mais elle
    couvrait un cas de trop. Un lab qui **déclare** des services et dont le
    moteur est injoignable est bel et bien injouable — `dsoxlab run` y échoue
    déjà explicitement en `services_docker_absent`, code 2. Annoncer `ready`
    contredisait donc la commande suivante.

    Ce que l'intention d'origine protégeait est gardé, et testé juste en
    dessous : un lab qui ne déclare **aucun** service ignore le moteur, sans
    même payer une sonde.
    """
    racine = _depot(tmp_path) / "labs" / "l1-demo"
    racine.mkdir(parents=True, exist_ok=True)
    (racine / "lab.yaml").write_text(
        _BASE
        + "runtime:\n  type: shell\n  workdir: challenge/work\n"
        + "  services:\n    - name: db\n      image: postgres:16\n",
        encoding="utf-8",
    )
    lab = LabDefinition.from_yaml(racine / "lab.yaml")

    from dsoxlab.runtimes import services as svc

    monkeypatch.setattr(svc, "docker_available", lambda: False)

    etat = lab_state.calculer(_depot(tmp_path), lab, "essai")
    assert etat.state == lab_state.DEGRADED
    assert etat.detail, "l'état doit dire pourquoi, sinon il ne sert à rien"


def test_docker_absent_ne_degrade_pas_un_lab_sans_service(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    """L'intention d'origine, à l'endroit exact où elle vaut.

    Un catalogue entièrement `shell` sans conteneur ne doit pas virer au rouge
    pour un moteur qu'il n'utilise pas.
    """
    racine = _depot(tmp_path) / "labs" / "l1-demo"
    racine.mkdir(parents=True, exist_ok=True)
    (racine / "lab.yaml").write_text(
        _BASE + "runtime:\n  type: shell\n  workdir: challenge/work\n",
        encoding="utf-8",
    )
    lab = LabDefinition.from_yaml(racine / "lab.yaml")

    from dsoxlab.runtimes import services as svc

    monkeypatch.setattr(svc, "docker_available", lambda: False)

    assert lab_state.calculer(_depot(tmp_path), lab, "essai").state != lab_state.DEGRADED


# ── Le runtime vm : le travail est hors de portée d'une empreinte locale ────

def test_un_lab_vm_non_prepare_n_est_pas_commence(tmp_path: Path) -> None:
    lab = _lab_vm(tmp_path)

    assert lab_state.calculer(_depot(tmp_path), lab, "essai").state == lab_state.NOT_STARTED


def test_un_lab_vm_prepare_est_en_cours(tmp_path: Path) -> None:
    """Faute de pouvoir observer le travail sur la machine, la préparation suffit.

    Le détail le dit plutôt que de laisser croire à une mesure qui n'a pas eu
    lieu.
    """
    racine = _depot(tmp_path)
    lab = _lab_vm(tmp_path)
    lab_state.enregistrer_depart(racine, lab)

    etat = lab_state.calculer(racine, lab, "essai")

    assert etat.state == lab_state.IN_PROGRESS


def test_oublier_le_depart_ramene_a_non_commence(tmp_path: Path) -> None:
    """Ce que `clean` et `reset` doivent pouvoir faire : défaire la préparation."""
    racine = _depot(tmp_path)
    lab = _lab_vm(tmp_path)
    lab_state.enregistrer_depart(racine, lab)

    lab_state.oublier_depart(racine, lab.id)

    assert lab_state.calculer(racine, lab, "essai").state == lab_state.NOT_STARTED


def test_les_empreintes_ne_sont_pas_ecrites_dans_le_catalogue(tmp_path: Path) -> None:
    """Un état recalculable n'a rien à faire dans un dépôt versionné.

    L'y écrire le ferait apparaître dans un `git status`, ou pire, dans un
    commit d'apprenant.
    """
    racine = _depot(tmp_path)
    lab = _lab_shell(tmp_path)
    (lab.path / "challenge" / "work").mkdir(parents=True)

    lab_state.enregistrer_depart(racine, lab)

    laisses = [p for p in racine.rglob("*.sha256")]
    assert not laisses, f"empreintes écrites dans le catalogue : {laisses}"
