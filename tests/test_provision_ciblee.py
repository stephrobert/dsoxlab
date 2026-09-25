"""`provision --host X` ne doit attendre que X (issue #246).

L'output `hosts` du template Terraform dérive de `var.hosts`, donc de **tous** les
hôtes déclarés au `meta.yml`, et non de ceux que l'apply a créés. La CLI y lisait
la liste des machines à attendre, si bien qu'un ciblage réclamait une réponse à
des machines qu'on avait explicitement demandé de ne pas monter.

`provision --host` sortait donc en **8** à tous les coups dès qu'un dépôt déclare
plus d'un hôte, c'est-à-dire presque toujours. L'option devenait inutilisable en
script, là où elle sert le plus : on ne cible que pour éviter de monter une
topologie entière, donc dans un contexte automatisé où l'on lit le code de sortie.

Constaté en validant #234, où ce 8 a d'abord été pris pour un échec du correctif
du firmware.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from typer.testing import CliRunner

from dsoxlab.cli import app

runner = CliRunner()

META = """\
repo:
  id: cible
  category: domaine

infra:
  provider: kvm
  network: reseau
  cidr: 10.10.10.0/24
  hosts:
    - name: un.lab
      distro: alma10
    - name: deux.lab
      distro: alma10
    - name: trois.lab
      distro: alma10
"""

#: Ce que Terraform rend : les TROIS hôtes déclarés, quoi qu'on ait ciblé.
TOUS = {"un.lab": "10.10.10.11", "deux.lab": "10.10.10.12", "trois.lab": "10.10.10.13"}


@pytest.fixture
def catalogue(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    (tmp_path / "meta.yml").write_text(META, encoding="utf-8")
    ssh = tmp_path / "ssh"
    ssh.mkdir()
    (ssh / "id_ed25519").write_text("clé privée de test\n", encoding="utf-8")
    (ssh / "id_ed25519.pub").write_text("ssh-ed25519 AAAA test\n", encoding="utf-8")
    monkeypatch.setenv("LAB_HOME", str(tmp_path))
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "etat"))
    monkeypatch.setenv("HOME", str(tmp_path / "maison"))
    return tmp_path


@pytest.fixture
def attendus(monkeypatch: pytest.MonkeyPatch) -> list[list[str]]:
    """Enregistre les hôtes que la CLI décide d'attendre, sans rien provisionner."""
    from dsoxlab.cli import infrastructure as infra_cli
    from dsoxlab.infra import inventory
    from dsoxlab.infra import terraform as tf

    vus: list[list[str]] = []

    def _faux_wait(_meta: Any, hosts: list[str], **_kw: Any) -> list[str]:
        vus.append(list(hosts))
        return []

    # À LA SOURCE : `provision` importe `wait_for_hosts_ready` localement, donc
    # remplacer l'attribut du module CLI ne changerait rien — l'import irait
    # rechercher l'original. Le défaut est silencieux : le test passerait en
    # croyant mesurer, alors que la vraie sonde tenterait de vrais SSH.
    monkeypatch.setattr(inventory, "wait_for_hosts_ready", _faux_wait)
    monkeypatch.setattr(tf, "is_available", lambda: True)
    monkeypatch.setattr(tf, "init", lambda *a, **k: None)
    monkeypatch.setattr(tf, "find_orphan_domains", lambda _m: tf.OrphanScan())
    monkeypatch.setattr(tf, "other_active_providers", lambda _m: [])
    # `_run_terraform_with_progress` enveloppe l'apply : c'est lui que la CLI
    # appelle, et son résultat qui alimente la liste des hôtes à attendre.
    monkeypatch.setattr(
        infra_cli, "_run_terraform_with_progress",
        lambda _nom, _appel: tf.ProvisionResult(outputs={}, hosts=dict(TOUS)),
    )
    monkeypatch.setattr(
        infra_cli, "_run_terraform_init_with_spinner", lambda _appel: None
    )
    return vus


def test_un_ciblage_n_attend_que_la_cible(
    catalogue: Path, attendus: list[list[str]]
) -> None:
    """Le cœur de #246 : deux des trois hôtes n'ont pas été montés."""
    resultat = runner.invoke(app, ["provision", "--host", "deux.lab"])

    assert resultat.exit_code == 0, resultat.stdout[-1500:]
    assert attendus == [["deux.lab"]], attendus


def test_plusieurs_cibles_sont_toutes_attendues(
    catalogue: Path, attendus: list[list[str]]
) -> None:
    resultat = runner.invoke(
        app, ["provision", "--host", "un.lab", "--host", "trois.lab"]
    )

    assert resultat.exit_code == 0, resultat.stdout[-1500:]
    assert attendus and sorted(attendus[0]) == ["trois.lab", "un.lab"]


def test_sans_ciblage_tous_les_hotes_sont_attendus(
    catalogue: Path, attendus: list[list[str]]
) -> None:
    """La régression à craindre : restreindre partout et ne plus rien vérifier."""
    resultat = runner.invoke(app, ["provision"])

    assert resultat.exit_code == 0, resultat.stdout[-1500:]
    assert attendus and sorted(attendus[0]) == ["deux.lab", "trois.lab", "un.lab"]


def test_le_message_dit_bien_ce_qui_a_ete_verifie(
    catalogue: Path, attendus: list[list[str]]
) -> None:
    """« 1 hôte prêt » sur un dépôt qui en déclare trois laisse croire que les
    deux autres ont été jugés, alors qu'ils n'ont pas même été montés."""
    resultat = runner.invoke(app, ["provision", "--host", "deux.lab"])

    sortie = " ".join(resultat.stdout.split())
    assert "1" in sortie and "3" in sortie, sortie[-400:]
