"""Tests du mécanisme de services conteneurisés (``runtime.services``).

Deux niveaux :

- **contrat + logique pure** : parsing de ``runtime.services`` et nommage des
  conteneurs, sans Docker ;
- **intégration** : démarrage/arrêt réel d'un conteneur, sauté si Docker est
  injoignable. L'image utilisée est ``hello-world`` (universelle, minuscule) ;
  le cas d'usage réel du dépôt (émulateur cloud) reste hors du code de dsoxlab,
  qui est agnostique.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from dsoxlab.models.lab import LabDefinition
from dsoxlab.models.runtime import Service
from dsoxlab.runtimes import services as svc

CONTRACT_EXCEPTIONS = (KeyError, ValueError, yaml.YAMLError)

_BASE = """\
id: l1-demo
title: Demo lab
level: beginner
skills: [demo]
distros: [any]
doc_url: https://example.org/docs/demo/
"""


def _lab(tmp_path: Path, runtime_block: str) -> LabDefinition:
    path = tmp_path / "lab.yaml"
    path.write_text(_BASE + runtime_block, encoding="utf-8")
    return LabDefinition.from_yaml(path)


# ── Parsing du contrat ──────────────────────────────────────────────────────

def test_services_absent_donne_liste_vide(tmp_path: Path) -> None:
    lab = _lab(tmp_path, "runtime:\n  type: shell\n  workdir: challenge/work\n")
    assert lab.runtime.services == []


def test_service_complet_est_parse(tmp_path: Path) -> None:
    lab = _lab(tmp_path, """\
runtime:
  type: shell
  workdir: challenge/work
  services:
    - name: cloud
      image: some/image:1.0
      ports: ["4566:4566"]
      run_args: ["-u", "root"]
      env:
        DEBUG: "1"
      ready_tcp: 4566
      ready_timeout: 30
""")
    assert len(lab.runtime.services) == 1
    s = lab.runtime.services[0]
    assert s.name == "cloud"
    assert s.image == "some/image:1.0"
    assert s.ports == ["4566:4566"]
    assert s.run_args == ["-u", "root"]
    assert s.env == {"DEBUG": "1"}
    assert s.ready_tcp == 4566
    assert s.ready_timeout == 30


def test_service_defauts(tmp_path: Path) -> None:
    lab = _lab(tmp_path, """\
runtime:
  type: shell
  services:
    - name: db
      image: postgres:16
""")
    s = lab.runtime.services[0]
    assert s.ports == [] and s.run_args == [] and s.env == {}
    assert s.ready_tcp == 0 and s.ready_timeout == 90


@pytest.mark.parametrize("bad", [
    "runtime:\n  type: shell\n  services:\n    - image: x\n",          # name manquant
    "runtime:\n  type: shell\n  services:\n    - name: x\n",           # image manquante
    "runtime:\n  type: shell\n  services: not-a-list\n",               # services scalaire
    "runtime:\n  type: shell\n  services:\n    - name: x\n      image: y\n      ports: nope\n",  # ports scalaire
])
def test_service_malforme_reste_dans_le_contrat(tmp_path: Path, bad: str) -> None:
    with pytest.raises(CONTRACT_EXCEPTIONS):
        _lab(tmp_path, bad)


# ── Nommage des conteneurs ──────────────────────────────────────────────────

def test_container_name_namespace_par_repo(tmp_path: Path) -> None:
    s = Service(name="cloud", image="x")
    assert svc.container_name("terraform-training", s) == "dsoxlab-terraform-training-cloud"


def test_container_name_sanitize(tmp_path: Path) -> None:
    s = Service(name="my cloud!", image="x")
    # espaces et caractères interdits Docker remplacés par des tirets.
    assert svc.container_name("repo/id", s) == "dsoxlab-repo-id-my-cloud-"


# ── Intégration Docker (sautée si Docker injoignable) ───────────────────────

@pytest.mark.skipif(not svc.docker_available(), reason="Docker injoignable")
def test_start_status_stop_cycle() -> None:
    """Cycle réel start → status → stop sur une image universelle.

    hello-world sort immédiatement : on ne teste pas ``ready_tcp`` ici (pas de
    port), seulement que start crée le conteneur et que stop le retire.
    """
    s = Service(name="pytest-svc", image="hello-world")
    repo = "dsoxlab-test"
    try:
        svc.start(s, repo)
        st = svc.status(s, repo)
        assert st.container == svc.container_name(repo, s)
        assert st.detail in ("running", "stopped")  # hello-world s'arrête vite
    finally:
        assert svc.stop(s, repo) in (True, False)
        assert svc.status(s, repo).running is False
