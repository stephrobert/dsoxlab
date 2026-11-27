"""La recommandation de provider n'impose plus un hyperviseur inutilisable (#411).

Deux postes réels l'ont motivée : un poste où Incus marche déjà, à qui `doctor`
proposait d'installer KVM, et un poste sans virtualisation matérielle (WSL, VM
sans virtualisation imbriquée), à qui il proposait KVM quand même, pour un
`--fix` qui l'installait en vain.

Les sondes virsh et incus ne sont jamais jouées ici : elles sont passées.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from dsoxlab.models import InfraDefinition, RepoMetadata
from dsoxlab.models.lab import (
    LabDefinition,
    RuntimeConfig,
    RuntimeType,
    Target,
    ValidationConfig,
)
from dsoxlab.services import doctor


def _sondes(kvm: bool, incus: bool) -> dict[str, doctor.Check]:
    return {
        "kvm": doctor._check("kvm", kvm, "sonde"),
        "incus": doctor._check("incus", incus, "sonde"),
    }


@pytest.fixture
def poste_linux(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Un Linux x86_64 dont /dev/kvm existe et s'ouvre."""
    device = tmp_path / "kvm"
    device.touch()
    monkeypatch.setattr(doctor, "_KVM_DEVICE", device)
    monkeypatch.setattr(doctor.platform, "system", lambda: "Linux")
    monkeypatch.setattr(doctor.platform, "machine", lambda: "x86_64")
    monkeypatch.setattr(doctor.os, "access", lambda *args: True)
    return device


def test_un_incus_qui_marche_passe_avant_un_kvm_a_installer(poste_linux: Path) -> None:
    assert doctor.provider_recommande(["kvm", "incus"], _sondes(False, True)) == "incus"


def test_un_kvm_qui_marche_reste_recommande(poste_linux: Path) -> None:
    assert doctor.provider_recommande(["incus", "kvm"], _sondes(True, True)) == "incus"
    assert doctor.provider_recommande(["kvm", "incus"], _sondes(True, True)) == "kvm"


def test_rien_d_installe_kvm_reste_le_premier_choix(poste_linux: Path) -> None:
    assert doctor.provider_recommande(["incus", "kvm"], _sondes(False, False)) == "kvm"


def test_un_kvm_sans_droit_sur_le_peripherique_ne_marche_pas_encore(
    poste_linux: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Le droit compte pour KVM (qemu sous le compte de l'utilisateur), pas pour
    Incus, dont le démon ouvre /dev/kvm en root."""
    monkeypatch.setattr(doctor.os, "access", lambda *args: False)
    assert doctor.provider_recommande(["kvm", "incus"], _sondes(True, True)) == "incus"


def test_sans_virtualisation_seul_un_provider_distant_est_propose(
    poste_linux: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    poste_linux.unlink()
    assert doctor.provider_recommande(["kvm", "incus", "outscale"], _sondes(True, True)) == "outscale"
    assert doctor.provider_recommande(["kvm", "incus"], _sondes(True, True)) == ""


def test_aucun_candidat_aucune_recommandation() -> None:
    assert doctor.provider_recommande([], _sondes(False, False)) == ""


def test_kvm_ecarte_sur_une_architecture_que_ses_images_ne_servent_pas(
    poste_linux: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(doctor.platform, "machine", lambda: "riscv64")
    assert doctor.provider_recommande(["kvm", "incus"], _sondes(False, False)) == "incus"
    assert doctor.provider_recommande(["kvm"], _sondes(False, False)) == ""


# ── le diagnostic complet sur un poste sans virtualisation ────────────────


def _catalogue_vm(candidats: list[str]) -> RepoMetadata:
    return RepoMetadata(
        id="demo", category="demo",
        infra=InfraDefinition(provider="", providers_available=candidats),
    )


def _lab_vm() -> LabDefinition:
    return LabDefinition(
        id="a", title="a", level="l1", skills=["s"],
        runtime=RuntimeConfig(type=RuntimeType.VM, targets=[Target(name="t", host="n.lab")]),
        distros=["alma10"], doc_url="https://example.test/doc",
        validation=ValidationConfig(),
    )


@pytest.fixture
def poste_sans_virtualisation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(doctor, "_KVM_DEVICE", tmp_path / "absent")
    monkeypatch.setattr(doctor.platform, "system", lambda: "Linux")
    monkeypatch.setattr(doctor, "_hypervisor_checks", lambda: _sondes(False, False))
    monkeypatch.setattr(doctor, "get_all_labs", lambda root: [_lab_vm()])


def test_le_diagnostic_dit_pourquoi_aucun_provider_ne_convient(
    tmp_path: Path, poste_sans_virtualisation: None
) -> None:
    report = doctor.collect_checks(tmp_path, _catalogue_vm(["kvm", "incus"]))
    requis = {c.key: c for c in report.required}

    # La cause reste en requis, et c'est elle qui donne la consigne.
    assert "hw_virt" in requis and not requis["hw_virt"].ok
    # Aucune invite à choisir un provider qui ne marcherait pas.
    assert requis["provider"].hint is None
    # L'écran sans `-v` ne montre pas les notes : l'étape le dit elle-même.
    assert "kvm, incus" in requis["provider"].detail
    assert requis["provider"].detail != doctor._(
        "detail_provider_unresolved", candidates="kvm, incus"
    )
    assert "kvm" not in requis and "incus" not in requis
    assert report.provider == ""
    assert doctor._("doctor_note_aucun_provider_compatible") in report.notes
    assert doctor._("doctor_note_provider_unresolved") not in report.notes


def test_fix_ne_lance_rien_quand_aucun_provider_ne_convient(
    tmp_path: Path, poste_sans_virtualisation: None
) -> None:
    """L'étape provider a une action dsoxlab (`use --provider`). Lancée ici,
    elle écrirait un provider vide dans le contexte : elle reste à faire à la
    main, avec la virtualisation qui en donne la cause."""
    from dsoxlab.services.remediation import planifier

    report = doctor.collect_checks(tmp_path, _catalogue_vm(["kvm", "incus"]))
    plan = planifier(report, actions={"provider": lambda: None})

    # Seules ces deux étapes sont en jeu : le reste du plan dépend du poste
    # (un runner sans Terraform y ajoute son installation).
    lancees = {e.cle for e in [*plan.sans_sudo, *plan.root]}
    assert not lancees & {"provider", "hw_virt"}
    assert {e.cle for e in plan.manuelles} >= {"provider", "hw_virt"}


def test_un_provider_distant_declare_reste_la_voie_proposee(
    tmp_path: Path, poste_sans_virtualisation: None
) -> None:
    report = doctor.collect_checks(tmp_path, _catalogue_vm(["kvm", "incus", "outscale"]))
    provider = next(c for c in report.required if c.key == "provider")

    assert provider.hint == "dsoxlab use --provider outscale"
    assert report.provider == "outscale"
    assert doctor._("doctor_note_aucun_provider_compatible") not in report.notes
