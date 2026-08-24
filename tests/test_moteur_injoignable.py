"""Un lab dont le moteur est tombé ne s'affiche plus « prêt » (#179).

`_services_degrades` rendait une liste vide quand `docker_available()` était
faux. L'intention était juste — une machine sans Docker n'est pas un lab cassé,
et c'était un choix documenté et testé — mais elle rendait « Docker **était** là
et son démon est tombé » indistinguable de « Docker n'a jamais été installé ».
Dans le premier cas, le lab est bel et bien injouable, et `dsoxlab status`
annonçait pourtant `ready` ou `validated`.

Les deux causes se distinguent maintenant, parce qu'elles appellent des gestes
opposés : installer un paquet, ou démarrer un démon et vérifier que le compte
peut lui parler.

Un lab qui ne déclare **aucun** service n'est pas concerné, et ce point compte
autant que les autres : c'est lui qui garantit qu'un catalogue entièrement
`shell` sans conteneur ne paie ni un appel, ni un faux rouge.
"""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from dsoxlab.models.lab import LabDefinition
from dsoxlab.services import lab_state

_ENTETE = """\
id: l1-demo
title: Demo lab
level: beginner
skills: [demo]
distros: [any]
doc_url: https://example.org/docs/demo/
runtime:
  type: shell
  workdir: challenge/work
"""

_SERVICE = """\
  services:
    - name: db
      image: postgres:16
"""


@pytest.fixture(autouse=True)
def xdg_jetable(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "state"))
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "data"))


def _depot(tmp_path: Path) -> Path:
    racine = tmp_path / "catalogue"
    (racine / "labs").mkdir(parents=True, exist_ok=True)
    (racine / "meta.yml").write_text("repo:\n  id: essai\n  category: essai\n",
                                     encoding="utf-8")
    return racine


def _lab(tmp_path: Path, *, avec_service: bool) -> LabDefinition:
    base = _depot(tmp_path) / "labs" / "l1-demo"
    base.mkdir(parents=True, exist_ok=True)
    (base / "lab.yaml").write_text(
        _ENTETE + (_SERVICE if avec_service else ""), encoding="utf-8")
    return LabDefinition.from_yaml(base / "lab.yaml")


def _moteur(monkeypatch: pytest.MonkeyPatch, *, installe: bool, repond: bool) -> None:
    """Simule l'état du moteur, sans dépendre de la machine qui joue les tests."""
    from dsoxlab.runtimes import services as svc

    monkeypatch.setattr(shutil, "which",
                        lambda nom: "/usr/bin/docker" if installe else None)
    monkeypatch.setattr(svc, "docker_available", lambda: repond)


# ── Le défaut : un moteur tombé passait pour « rien à signaler » ────────────

def test_un_demon_tombe_rend_le_lab_degrade(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Le cas de l'issue : docker est installé, le démon ne répond plus."""
    racine = _depot(tmp_path)
    lab = _lab(tmp_path, avec_service=True)
    _moteur(monkeypatch, installe=True, repond=False)

    etat = lab_state.calculer(racine, lab, "essai")

    assert etat.state == lab_state.DEGRADED


def test_un_docker_jamais_installe_se_dit_autrement(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Les deux causes appellent des gestes opposés, donc elles se distinguent.

    Confondre « installe Docker » et « démarre son démon » envoie l'utilisateur
    chercher un paquet déjà présent.
    """
    racine = _depot(tmp_path)
    lab = _lab(tmp_path, avec_service=True)

    _moteur(monkeypatch, installe=False, repond=False)
    absent = lab_state.calculer(racine, lab, "essai")

    _moteur(monkeypatch, installe=True, repond=False)
    muet = lab_state.calculer(racine, lab, "essai")

    assert absent.state == muet.state == lab_state.DEGRADED
    assert absent.detail != muet.detail, "les deux causes doivent se lire"


def test_les_deux_details_sont_traduits(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Une clé absente des dictionnaires s'afficherait telle quelle."""
    racine = _depot(tmp_path)
    lab = _lab(tmp_path, avec_service=True)

    for installe in (True, False):
        _moteur(monkeypatch, installe=installe, repond=False)
        detail = lab_state.calculer(racine, lab, "essai").detail
        assert detail is not None
        assert not detail.startswith("lab_state_"), f"clé non traduite : {detail}"


# ── Le lab n'est plus annoncé jouable ───────────────────────────────────────

def test_un_lab_deja_note_ne_passe_plus_pour_validated(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Une note obtenue hier ne rend pas le lab jouable aujourd'hui.

    C'est le cas qui trompait le plus : le score existait, donc `status`
    annonçait « validé » sur un environnement qui ne démarre plus.
    """
    from dsoxlab.services.lab_service import CheckResult, evaluate_lab

    racine = _depot(tmp_path)
    lab = _lab(tmp_path, avec_service=True)
    evaluate_lab(racine, lab,
                 CheckResult(ok=True, output="3 passed", passed=3, total=3))

    _moteur(monkeypatch, installe=True, repond=False)
    etat = lab_state.calculer(racine, lab, "essai")

    assert etat.state == lab_state.DEGRADED
    assert etat.best_score is not None, "la note reste lisible, elle n'est pas perdue"


# ── L'autre bout : ne rien casser pour qui n'utilise pas Docker ────────────

def test_un_lab_sans_service_ignore_le_moteur(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    """L'intention d'origine, préservée : pas de faux rouge, et pas d'appel.

    Un catalogue entièrement `shell` sans conteneur ne doit ni payer une sonde,
    ni virer au rouge pour un moteur qu'il n'utilise pas.
    """
    from dsoxlab.runtimes import services as svc

    racine = _depot(tmp_path)
    lab = _lab(tmp_path, avec_service=False)

    appele = {"oui": False}

    def _sonde() -> bool:
        appele["oui"] = True
        return False

    monkeypatch.setattr(shutil, "which", lambda nom: None)
    monkeypatch.setattr(svc, "docker_available", _sonde)

    etat = lab_state.calculer(racine, lab, "essai")

    assert etat.state != lab_state.DEGRADED
    assert appele["oui"] is False, "aucun appel pour un lab qui ne déclare rien"


def test_un_moteur_qui_repond_laisse_l_etat_normal(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Le garde-fou du garde-fou : Docker debout ne dégrade rien."""
    from dsoxlab.runtimes import services as svc

    racine = _depot(tmp_path)
    lab = _lab(tmp_path, avec_service=True)
    _moteur(monkeypatch, installe=True, repond=True)
    monkeypatch.setattr(
        svc, "status",
        lambda service, repo: type("E", (), {"detail": "absent"})())

    etat = lab_state.calculer(racine, lab, "essai")

    assert etat.state != lab_state.DEGRADED
