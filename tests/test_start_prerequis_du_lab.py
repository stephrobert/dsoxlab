"""``start <lab>`` juge les prérequis de ce lab, pas du catalogue (0.11.1).

Le défaut : sur un clone neuf, le premier lab ``shell`` d'un catalogue qui a aussi
des labs ``vm`` était refusé faute de provider et de clé SSH.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from dsoxlab.discovery.repo import read_repo_metadata
from dsoxlab.discovery.scanner import discover_labs
from dsoxlab.models import LabDefinition, RepoMetadata
from dsoxlab.services.doctor import collect_checks

_META = """repo:
  id: mixte
  category: domaine
infra:
  provider: [kvm, incus]
  network: lab-mixte
  cidr: 10.98.0.0/24
  hosts:
    - name: un.lab
      distro: debian13
"""
_TETE = "id: {id}\ntitle: {id}\nlevel: l1\nskills: [a]\ndistros: [b]\ndoc_url: https://example.org/\nruntime:\n"
_LABS = {
    "lab-shell": "  type: shell\n  workdir: challenge/work\n",
    "lab-vm": "  type: vm\n  targets:\n    - name: cible\n      host: un.lab\n",
    "lab-service": "  type: shell\n  workdir: challenge/work\n  services:\n    - name: base\n      image: une/image:1\n",
}


@pytest.fixture
def depot(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    (tmp_path / "meta.yml").write_text(_META, encoding="utf-8")
    for nom, runtime in _LABS.items():
        d = tmp_path / "labs" / nom
        d.mkdir(parents=True)
        (d / "lab.yaml").write_text(_TETE.format(id=nom) + runtime, encoding="utf-8")
    monkeypatch.setenv("LAB_HOME", str(tmp_path))
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "etat"))
    monkeypatch.delenv("DSOXLAB_PROVIDER", raising=False)
    return tmp_path


def _meta(depot: Path) -> RepoMetadata:
    meta = read_repo_metadata(depot)
    assert meta is not None
    return meta


def _requis(depot: Path, nom: str | None) -> set[str]:
    labs: dict[str, LabDefinition] = {lab.id: lab for lab in discover_labs(depot)}
    rapport = collect_checks(depot, _meta(depot), hosts=[], lab=labs[nom] if nom else None)
    return {c.key for c in rapport.required}


def test_un_lab_shell_n_exige_rien_des_machines(depot: Path) -> None:
    requis = _requis(depot, "lab-shell")

    assert not requis & {"provider", "cle_ssh", "terraform", "ansible", "kvm", "incus"}


def test_un_lab_shell_sans_service_n_exige_pas_docker(depot: Path) -> None:
    assert "docker" not in _requis(depot, "lab-shell")


def test_un_lab_a_service_exige_docker(depot: Path) -> None:
    assert "docker" in _requis(depot, "lab-service")


def test_un_lab_vm_dont_les_hotes_tournent_exige_toujours_l_outillage(depot: Path) -> None:
    """``hosts=[]`` veut aussi dire « tout tourne déjà » : il ne suffit pas à conclure."""
    assert "terraform" in _requis(depot, "lab-vm")


def test_doctor_seul_porte_toujours_sur_tout_le_catalogue(depot: Path) -> None:
    requis = _requis(depot, None)

    assert {"terraform", "docker"} <= requis
