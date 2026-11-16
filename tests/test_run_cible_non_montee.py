"""``run`` refuse une machine commune jamais montée, en nommant la commande (issue #380).

Reproduit le 2026-11-16 sur une Ubuntu vide préparée jusqu'à un doctor vert :
après ``provision --host alma-rhcsa-1.lab``, ``run lfcs-apparmor`` envoyait
Ansible vers 10.10.30.13, l'adresse d'ubuntu-lfcs-1.lab, jamais montée
(blog-roadmap#186). L'apprenant lisait une erreur SSH dans une tâche AppArmor.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
import typer

from dsoxlab.cli import parcours

META = """\
repo:
  id: partiel
  category: demo
infra:
  provider: kvm
  network: lab-partiel
  cidr: 10.10.62.0/24
  hosts:
    - name: alma.lab
    - name: ubuntu.lab
"""


@pytest.fixture
def depot(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "state"))
    monkeypatch.setenv("DSOXLAB_NO_UPDATE_CHECK", "1")
    monkeypatch.setenv("DSOXLAB_LANG", "en")
    monkeypatch.delenv("DSOXLAB_PROVIDER", raising=False)
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "meta.yml").write_text(META, encoding="utf-8")
    return repo


def _state(tmp_path: Path, hotes: list[str] | None, *, illisible: bool = False) -> None:
    dossier = tmp_path / "state" / "dsoxlab" / "partiel" / "terraform" / "kvm"
    dossier.mkdir(parents=True, exist_ok=True)
    if illisible:
        (dossier / "terraform.tfstate").write_text("{pas du json", encoding="utf-8")
        return
    if hotes is None:
        return
    (dossier / "terraform.tfstate").write_text(json.dumps({"resources": [
        {"mode": "managed", "type": "libvirt_domain", "name": "host",
         "instances": [{"index_key": h, "attributes": {"name": h}} for h in hotes]},
    ]}), encoding="utf-8")


class _Lab:
    class runtime:
        class type:
            value = "vm"


def _cible(monkeypatch: pytest.MonkeyPatch, hotes: list[str]) -> None:
    from dsoxlab.runtimes import vm

    class _Target:
        def hosts(self) -> list[str]:
            return hotes

    monkeypatch.setattr(vm, "resoudre_target", lambda lab, target: _Target())


@pytest.fixture
def erreurs(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    dites: list[str] = []
    monkeypatch.setattr(parcours, "error", dites.append)
    return dites


def test_une_cible_commune_absente_arrete_run_avec_la_commande(
    depot: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, erreurs: list[str]
) -> None:
    _state(tmp_path, ["alma.lab"])
    _cible(monkeypatch, ["ubuntu.lab"])
    with pytest.raises(typer.Exit) as sortie:
        parcours._refuser_les_cibles_non_montees(depot, _Lab(), None)  # type: ignore[arg-type]
    assert sortie.value.exit_code == 2
    assert len(erreurs) == 1
    assert "ubuntu.lab" in erreurs[0]
    assert "dsoxlab provision --host ubuntu.lab" in erreurs[0]
    assert "alma.lab" not in erreurs[0]


def test_toutes_les_absentes_sont_nommees_dans_une_seule_commande(
    depot: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, erreurs: list[str]
) -> None:
    _state(tmp_path, ["autre.lab"])
    _cible(monkeypatch, ["ubuntu.lab", "alma.lab"])
    with pytest.raises(typer.Exit):
        parcours._refuser_les_cibles_non_montees(depot, _Lab(), None)  # type: ignore[arg-type]
    assert "dsoxlab provision --host alma.lab --host ubuntu.lab" in erreurs[0]


def test_une_cible_montee_laisse_passer(
    depot: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, erreurs: list[str]
) -> None:
    _state(tmp_path, ["alma.lab", "ubuntu.lab"])
    _cible(monkeypatch, ["ubuntu.lab"])
    parcours._refuser_les_cibles_non_montees(depot, _Lab(), None)  # type: ignore[arg-type]
    assert erreurs == []


@pytest.mark.parametrize(("hotes", "illisible"), [(None, False), ([], False), (None, True)])
def test_sans_state_ou_state_illisible_le_controle_ne_refuse_rien(
    depot: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, erreurs: list[str],
    hotes: list[str] | None, illisible: bool,
) -> None:
    """Rien de monté : infra_not_provisioned le dit déjà. Illisible : on ne sait pas."""
    _state(tmp_path, hotes, illisible=illisible)
    _cible(monkeypatch, ["ubuntu.lab"])
    parcours._refuser_les_cibles_non_montees(depot, _Lab(), None)  # type: ignore[arg-type]
    assert erreurs == []


def test_un_lab_shell_n_est_pas_concerne(
    depot: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, erreurs: list[str]
) -> None:
    class _Shell:
        class runtime:
            class type:
                value = "shell"

    _state(tmp_path, ["alma.lab"])
    parcours._refuser_les_cibles_non_montees(depot, _Shell(), None)  # type: ignore[arg-type]
    assert erreurs == []


def test_run_appelle_le_controle_avant_le_playbook() -> None:
    """L'ordre dans ``run`` : le refus vient avant tout ``run_lab``."""
    import inspect

    source = inspect.getsource(parcours.run)
    assert source.index("_refuser_les_cibles_non_montees") < source.index("run_lab(")


def test_les_cles_existent_en_anglais_et_en_francais() -> None:
    from dsoxlab.i18n.strings import en, fr

    assert "{command}" in en.STRINGS["run_cible_non_montee"]
    assert "{command}" in fr.STRINGS["run_cible_non_montee"]
