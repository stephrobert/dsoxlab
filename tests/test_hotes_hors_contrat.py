"""Les machines du state que le ``meta.yml`` courant ignore (issue #357).

Deux checkouts d'un même dépôt partagent le state Terraform, nommé par
``repo.id``. Celui qui déclare le moins d'hôtes détruisait en silence, au
premier ``provision``, les machines que l'autre avait montées. Ces tests
défendent le refus, son contournement explicite (``--prune``) et le cas nominal.

Aucune commande d'infrastructure réelle : Terraform est simulé, et le state est
un fichier posé à la main dans un ``XDG_STATE_HOME`` jetable.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from dsoxlab.cli import app, destruction
from dsoxlab.exit_codes import ExitCode
from dsoxlab.infra import terraform
from dsoxlab.models.repo import RepoMetadata

runner = CliRunner()

META = """\
repo:
  id: hc
  category: demo
infra:
  provider: kvm
  network: lab-hc
  cidr: 10.10.61.0/24
  hosts:
    - name: cp.lab
    - name: w1.lab
  optional_hosts:
    - name: lb.lab
"""


class _Arret(RuntimeError):
    """Levée par le faux Terraform : on a vu l'appel, on n'a pas besoin de la suite."""


@pytest.fixture
def depot(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "state"))
    monkeypatch.setenv("DSOXLAB_NO_UPDATE_CHECK", "1")
    monkeypatch.setenv("DSOXLAB_LANG", "en")
    monkeypatch.delenv("DSOXLAB_PROVIDER", raising=False)
    repo = tmp_path / "repo"
    (repo / "ssh").mkdir(parents=True)
    (repo / "ssh" / "id_ed25519").write_text("clé factice", encoding="utf-8")
    (repo / "meta.yml").write_text(META, encoding="utf-8")
    return repo


@pytest.fixture
def faux_terraform(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    """Terraform simulé : chaque appel est noté, puis arrêté net."""
    appels: list[str] = []

    def _noter(nom: str):  # type: ignore[no-untyped-def]
        def _faux(*_a: object, **_k: object) -> None:
            appels.append(nom)
            raise _Arret(nom)
        return _faux

    monkeypatch.setattr(terraform, "is_available", lambda: True)
    monkeypatch.setattr(terraform, "init", lambda *a, **k: None)
    monkeypatch.setattr(terraform, "apply", _noter("apply"))
    monkeypatch.setattr(terraform, "destroy", _noter("destroy"))
    monkeypatch.setattr(terraform, "retirer_hotes_optionnels", _noter("retirer"))
    # Les contrôles préalables interrogent l'hyperviseur : hors sujet ici.
    monkeypatch.setattr(terraform, "other_active_providers", lambda meta: [])
    monkeypatch.setattr(
        terraform, "find_orphan_domains", lambda meta: terraform.OrphanScan()
    )
    monkeypatch.setattr(destruction, "_purge_snapshots_before_destroy", lambda *a, **k: None)
    return appels


def _poser_le_state(tmp_path: Path, hotes: list[str]) -> None:
    dossier = tmp_path / "state" / "dsoxlab" / "hc" / "terraform" / "kvm"
    dossier.mkdir(parents=True, exist_ok=True)
    (dossier / "terraform.tfstate").write_text(json.dumps({"resources": [
        {"mode": "managed", "type": "libvirt_domain", "name": "host",
         "instances": [{"index_key": h} for h in hotes]},
    ]}), encoding="utf-8")


def _provision(depot: Path, *options: str) -> object:
    return runner.invoke(app, ["provision", *options, "--lab-home", str(depot)])


# ── La lecture du state ────────────────────────────────────────────────────


def test_un_hote_du_state_absent_du_meta_est_nomme(depot: Path, tmp_path: Path) -> None:
    _poser_le_state(tmp_path, ["cp.lab", "w1.lab", "lb.lab", "kind.lab"])
    meta = RepoMetadata.from_yaml(depot / "meta.yml")
    assert terraform.hotes_hors_contrat(meta) == ["kind.lab"]


def test_sans_state_aucun_hote_hors_contrat(depot: Path) -> None:
    meta = RepoMetadata.from_yaml(depot / "meta.yml")
    assert terraform.hotes_hors_contrat(meta) == []


# ── provision ──────────────────────────────────────────────────────────────


def test_provision_refuse_de_detruire_un_hote_inconnu(
    depot: Path, tmp_path: Path, faux_terraform: list[str]
) -> None:
    _poser_le_state(tmp_path, ["cp.lab", "w1.lab", "kind.lab"])
    resultat = _provision(depot)
    assert resultat.exit_code == ExitCode.HOTES_HORS_CONTRAT, resultat.output
    assert "kind.lab" in resultat.output
    assert "--prune" in resultat.output
    assert faux_terraform == []


def test_provision_host_refuse_aussi(
    depot: Path, tmp_path: Path, faux_terraform: list[str]
) -> None:
    """Le --host ne détruirait rien, mais le provision suivant si : on le dit tôt."""
    _poser_le_state(tmp_path, ["cp.lab", "w1.lab", "kind.lab"])
    resultat = _provision(depot, "--host", "cp.lab")
    assert resultat.exit_code == ExitCode.HOTES_HORS_CONTRAT, resultat.output
    assert faux_terraform == []


def test_provision_prune_assume_la_destruction_et_la_nomme(
    depot: Path, tmp_path: Path, faux_terraform: list[str]
) -> None:
    _poser_le_state(tmp_path, ["cp.lab", "w1.lab", "kind.lab"])
    resultat = _provision(depot, "--prune")
    assert faux_terraform == ["apply"]
    assert "kind.lab" in resultat.output


def test_provision_nominal_inchange_avec_un_optionnel_monte(
    depot: Path, tmp_path: Path, faux_terraform: list[str]
) -> None:
    """Un optionnel au state est déclaré : rien d'étranger, l'apply part."""
    _poser_le_state(tmp_path, ["cp.lab", "w1.lab", "lb.lab"])
    resultat = _provision(depot)
    assert faux_terraform == ["apply"], resultat.output
    assert resultat.exit_code != ExitCode.HOTES_HORS_CONTRAT


# ── destroy ────────────────────────────────────────────────────────────────


def test_destroy_optional_hosts_refuse_un_hote_inconnu(
    depot: Path, tmp_path: Path, faux_terraform: list[str]
) -> None:
    _poser_le_state(tmp_path, ["cp.lab", "w1.lab", "lb.lab", "kind.lab"])
    resultat = runner.invoke(
        app, ["destroy", "--optional-hosts", "--yes", "--lab-home", str(depot)]
    )
    assert resultat.exit_code == ExitCode.HOTES_HORS_CONTRAT, resultat.output
    assert "kind.lab" in resultat.output
    assert faux_terraform == []


def test_destroy_nomme_les_hotes_inconnus_avant_de_tout_detruire(
    depot: Path, tmp_path: Path, faux_terraform: list[str]
) -> None:
    _poser_le_state(tmp_path, ["cp.lab", "w1.lab", "kind.lab"])
    resultat = runner.invoke(app, ["destroy", "--yes", "--lab-home", str(depot)])
    assert faux_terraform == ["destroy"]
    sortie = resultat.output
    assert "kind.lab" in sortie
    assert sortie.index("kind.lab") < sortie.index("failed")
