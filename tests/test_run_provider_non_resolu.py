"""Un lab ``vm`` sans provider résolu : un message, jamais une trace (issue #319).

``infra.provider`` en liste ne se résout pas de lui-même. ``provision`` le
disait déjà, par ``_require_provider`` ; ``run`` atteignait
``require_provider()`` au fond du runtime, et ``ProviderUnresolved`` (une
``ValueError``) s'échappait en trace Python complète.

Aucune infrastructure n'est touchée : sans provider, rien ne peut l'atteindre,
et ``HOME`` comme ``XDG_STATE_HOME`` pointent sur un dossier jetable.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from typer.testing import CliRunner

from dsoxlab.cli import app
from dsoxlab.models.repo import ProviderUnresolved

runner = CliRunner()

_META = """\
repo:
  id: deux-providers
  category: domaine
infra:
  provider: [kvm, incus]
  network: reseau
  cidr: 10.10.62.0/24
  hosts:
    - name: cible.lab
      distro: debian13
"""

_LAB = """\
id: lab-vm
title: Lab vm
level: l1
skills: [demo]
distros: [debian13]
doc_url: https://example.test/docs/vm/
runtime:
  type: vm
  targets:
    - name: cible
      host: cible.lab
  default: cible
"""


@pytest.fixture
def catalogue(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    (tmp_path / "meta.yml").write_text(_META, encoding="utf-8")
    dossier = tmp_path / "labs" / "domaine" / "lab-vm"
    (dossier / "challenge" / "tests").mkdir(parents=True)
    (dossier / "lab.yaml").write_text(_LAB, encoding="utf-8")
    (dossier / "setup.yaml").write_text("- hosts: lab_target\n  tasks: []\n", encoding="utf-8")
    (dossier / "cleanup.yaml").write_text("- hosts: lab_target\n  tasks: []\n", encoding="utf-8")
    monkeypatch.setenv("LAB_HOME", str(tmp_path))
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "etat"))
    monkeypatch.setenv("HOME", str(tmp_path / "maison"))
    monkeypatch.setenv("DSOXLAB_LANG", "en")
    monkeypatch.setenv("DSOXLAB_NO_UPDATE_CHECK", "1")
    monkeypatch.delenv("DSOXLAB_PROVIDER", raising=False)
    monkeypatch.delenv("DSOXLAB_TARGET", raising=False)
    return tmp_path


@pytest.mark.parametrize("commande", [
    ["run", "lab-vm"],
    ["reset", "lab-vm", "--yes"],
    ["clean", "lab-vm", "--yes"],
])
def test_un_lab_vm_sans_provider_nomme_le_geste(
    catalogue: Path, commande: list[str]
) -> None:
    resultat = runner.invoke(app, commande)
    assert not isinstance(resultat.exception, ProviderUnresolved), resultat.output
    assert resultat.exit_code == 1, resultat.output
    assert "dsoxlab use --provider kvm" in resultat.output


def test_un_lab_shell_n_exige_jamais_de_provider(catalogue: Path) -> None:
    """Le contre-témoin : un lab sans infrastructure ne demande pas de provider."""
    from dsoxlab.cli._commun import _lab_a_jouer

    dossier = catalogue / "labs" / "domaine" / "lab-shell"
    (dossier / "challenge" / "tests").mkdir(parents=True)
    (dossier / "lab.yaml").write_text(
        _LAB.replace("id: lab-vm", "id: lab-shell").split("runtime:")[0]
        + "runtime:\n  type: shell\n  workdir: challenge/work\n",
        encoding="utf-8",
    )
    assert _lab_a_jouer(catalogue, "lab-shell", "en").id == "lab-shell"
