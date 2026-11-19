"""Le poste de `dsoxlab vm` : un hyperviseur, aucun catalogue (0.10.1).

Deux défauts trouvés en répétant la vidéo de démo de `vm`, le 2026-11-19, sur
une Ubuntu 24.04 neuve :

- `doctor --fix --all` installait Incus, l'annonçait « fait, revérifié », et la
  première VM Incus refusait de démarrer : « Neither mkisofs nor genisoimage
  could be found ». Le paquet `incus` seul fait tourner des conteneurs, et les
  templates de dsoxlab ne créent que des VM ;
- sans catalogue, `doctor` ne classait ni Terraform ni la ligne `Include` de
  `~/.ssh/config` en requis : `vm create` avertissait après coup que
  `ssh <nom>.lab` ne marcherait pas.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from dsoxlab.services import doctor
from dsoxlab.templates import template_root


def _taches(liste: list[dict]) -> list[dict]:
    """Les tâches du playbook, blocs dépliés."""
    sortie: list[dict] = []
    for tache in liste:
        sortie.append(tache)
        sortie += _taches(tache.get("block", []))
    return sortie


def test_le_playbook_installe_avec_incus_ce_qu_il_faut_pour_ses_vm() -> None:
    jeu = yaml.safe_load((template_root() / "ansible" / "poste.yml").read_text(encoding="utf-8"))
    paquets: set[str] = set()
    for tache in _taches(jeu[0]["tasks"]):
        apt = tache.get("ansible.builtin.apt") or {}
        noms = apt.get("name")
        if isinstance(noms, list) and "incus" in noms:
            paquets |= set(noms)
    assert {"incus", "genisoimage", "qemu-system-x86", "ovmf"} <= paquets


def _poste(monkeypatch: pytest.MonkeyPatch, *, kvm: bool, incus: bool) -> None:
    monkeypatch.setattr(doctor, "_hypervisor_checks", lambda: {
        "kvm": doctor._check("kvm", kvm, "libvirt 10.0.0"),
        "incus": doctor._check("incus", incus, "6.0.0"),
    })
    monkeypatch.setattr(doctor, "_check_terraform",
                        lambda: doctor._check("terraform", True, "Terraform v1.17.2"))
    monkeypatch.setattr(doctor, "_check_ssh_include",
                        lambda: doctor._check("ssh_include", False, "absent"))
    monkeypatch.setattr(doctor, "_check_iso_tool",
                        lambda: doctor._check("iso_tool", False, "absent"))


@pytest.mark.parametrize(("kvm", "incus"), [(True, False), (False, True)])
def test_sans_catalogue_un_hyperviseur_rend_terraform_et_l_include_requis(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, kvm: bool, incus: bool,
) -> None:
    _poste(monkeypatch, kvm=kvm, incus=incus)
    requis = {c.key for c in doctor.collect_checks(tmp_path, None).required}
    assert {"terraform", "ssh_include"} <= requis


def test_sans_catalogue_ni_hyperviseur_rien_de_plus_n_est_exige(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path,
) -> None:
    """Un poste sans hyperviseur n'a pas l'usage de Terraform : pas de rouge pour lui."""
    _poste(monkeypatch, kvm=False, incus=False)
    requis = {c.key for c in doctor.collect_checks(tmp_path, None).required}
    assert not ({"terraform", "ssh_include"} & requis)


def test_sans_catalogue_incus_qui_repond_exige_l_outil_iso_de_ses_vm(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path,
) -> None:
    """Le démon répond sans genisoimage, mais aucune VM ne démarre."""
    _poste(monkeypatch, kvm=False, incus=True)
    requis = {c.key for c in doctor.collect_checks(tmp_path, None).required}
    assert "iso_tool" in requis


def test_sans_catalogue_kvm_seul_n_exige_pas_l_outil_iso(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path,
) -> None:
    _poste(monkeypatch, kvm=True, incus=False)
    requis = {c.key for c in doctor.collect_checks(tmp_path, None).required}
    assert "iso_tool" not in requis


def test_l_outil_iso_se_repare_par_le_composant_incus_du_playbook() -> None:
    """Un contrôle rouge sans composant faisait lever `doctor --fix` en entier."""
    from dsoxlab.services import remediation

    assert remediation._COMPOSANTS["iso_tool"] == "incus"
