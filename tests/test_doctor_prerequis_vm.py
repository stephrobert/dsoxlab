"""Tests des prérequis matériels d'un lab ``vm`` : ce que `doctor` ignorait.

Trois prérequis décident si un lab ``vm`` peut tourner, et aucun n'était
vérifié : la virtualisation matérielle (`/dev/kvm`), l'architecture du
processeur face aux images packagées, et les ressources disponibles face à ce
que le ``meta.yml`` déclare. Sur une VM sans virtualisation imbriquée,
`doctor` était entièrement vert pendant que `provision` échouait en langage
Terraform (« could not find capabilities for domaintype=kvm »).

Deux règles héritées du module s'appliquent aussi ici :

- un catalogue 100 % ``shell`` ne doit jamais voir ces contrôles en rouge ;
- une sonde impossible ne vaut jamais « ok » : elle sort en ``unknown``,
  un jeton qui n'est ni le vert qui rassure à tort, ni le rouge qui accuse
  sans preuve.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from dsoxlab.models.lab import LabDefinition, ValidationConfig
from dsoxlab.models.repo import HostDefinition, InfraDefinition, RepoMetadata
from dsoxlab.models.runtime import RuntimeConfig, RuntimeType, Target
from dsoxlab.reporting import machine
from dsoxlab.services import doctor


def _lab(lab_id: str, runtime_type: RuntimeType) -> LabDefinition:
    targets = (
        []
        if runtime_type is RuntimeType.SHELL
        else [Target(name="rhel", host="node1.lab")]
    )
    return LabDefinition(
        id=lab_id,
        title=lab_id,
        level="l1",
        skills=["s"],
        runtime=RuntimeConfig(type=runtime_type, targets=targets),
        distros=["alma10"],
        doc_url="https://example.test/doc",
        validation=ValidationConfig(),
    )


def _infra(provider: str = "kvm") -> InfraDefinition:
    """Deux hôtes déclarés : 3072 Mo de RAM, 25 Go de disque en tout."""
    return InfraDefinition(
        provider=provider,
        hosts=[
            HostDefinition(name="a.lab", ram_mb=2048, disk_gb=10, extra_disk_gb=5),
            HostDefinition(name="b.lab", ram_mb=1024, disk_gb=10),
        ],
    )


def _repo(provider: str, infra: InfraDefinition | None = None) -> RepoMetadata:
    return RepoMetadata(
        id="demo",
        category="demo",
        infra=infra or InfraDefinition(provider=provider),
    )


@pytest.fixture(autouse=True)
def _environnement_stable(monkeypatch: pytest.MonkeyPatch) -> None:
    """Neutralise tout ce qui mesure la machine, sauf le contrôle sous test.

    Chaque test réactive la sonde qu'il vérifie en la pilotant lui-même.
    """
    monkeypatch.setattr(
        doctor, "_hypervisor_checks",
        lambda: {
            "kvm": doctor._check("kvm", True, "libvirt 10.0.0"),
            "incus": doctor._check("incus", True, "daemon ok"),
        },
    )
    monkeypatch.setattr(
        doctor, "_check_terraform",
        lambda: doctor._check("terraform", True, "Terraform v1.0.0"),
    )
    monkeypatch.setattr(
        doctor, "_check_ansible",
        lambda: doctor._check("ansible", True, "ok"),
    )
    monkeypatch.setattr(
        doctor, "_check_libvirt_pool",
        lambda pool: doctor._check("libvirt_pool", True, pool),
    )


# ── /dev/kvm : la virtualisation matérielle ───────────────────────────────────

def test_dev_kvm_absent_est_un_echec_qui_le_dit(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Sans /dev/kvm, les labs vm ne peuvent pas tourner ici, et ça se dit.

    `virsh version` répond parfaitement sur une machine sans virtualisation :
    c'est le périphérique qu'il faut lire, pas le client.
    """
    monkeypatch.setattr(doctor, "_KVM_DEVICE", tmp_path / "kvm")
    check = doctor._check_hw_virt()

    assert check.key == "hw_virt"
    assert check.state == doctor.STATE_FAILED
    # Le geste (BIOS, virtualisation imbriquée) appartient à l'humain, machine
    # éteinte : aucun correctif exécutable ne doit être proposé.
    assert check.fix is None


def test_dev_kvm_inaccessible_est_reparable(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Présent mais interdit est un autre état : le groupe kvm le rend.

    L'appartenance à un groupe ne prend effet qu'à la session suivante, d'où
    la catégorie NEEDS_RELOGIN : sans elle, l'utilisateur relance `doctor`,
    revoit le rouge et croit le correctif en échec.
    """
    device = tmp_path / "kvm"
    device.touch()
    monkeypatch.setattr(doctor, "_KVM_DEVICE", device)
    monkeypatch.setattr(doctor.os, "access", lambda p, mode: False)

    check = doctor._check_hw_virt()

    assert check.state == doctor.STATE_FAILED
    assert check.fix is not None
    assert check.fix.kind is doctor.FixKind.NEEDS_RELOGIN
    assert "usermod" in check.fix.display


def test_dev_kvm_accessible_est_vert(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    device = tmp_path / "kvm"
    device.touch()
    monkeypatch.setattr(doctor, "_KVM_DEVICE", device)

    check = doctor._check_hw_virt()

    assert check.state == doctor.STATE_OK
    assert check.detail == str(device)


# ── l'architecture face aux images packagées ──────────────────────────────────

def test_une_archi_etrangere_aux_images_kvm_echoue(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Les images du template kvm sont x86_64 : sur aarch64, rien ne bootera.

    L'écart est nommé des deux côtés, la machine ET les images, pour que
    l'utilisateur comprenne qu'aucune installation ne le comblera.
    """
    monkeypatch.setattr(doctor.platform, "machine", lambda: "aarch64")
    check = doctor._check_cpu_arch("kvm")

    assert check.key == "cpu_arch"
    assert check.state == doctor.STATE_FAILED
    assert "aarch64" in check.detail
    assert "x86_64" in check.detail


def test_x86_64_convient_aux_images_kvm(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(doctor.platform, "machine", lambda: "x86_64")
    check = doctor._check_cpu_arch("kvm")

    assert check.state == doctor.STATE_OK
    assert check.detail == "x86_64"


def test_un_provider_multiarch_ne_contraint_pas(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Le registre images: d'incus résout l'alias dans l'archi de l'hôte."""
    monkeypatch.setattr(doctor.platform, "machine", lambda: "aarch64")
    check = doctor._check_cpu_arch("incus")

    assert check.state == doctor.STATE_OK


def test_une_archi_indeterminable_nest_pas_verte(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """platform.machine() vide : rien mesuré, donc ni vert ni rouge."""
    monkeypatch.setattr(doctor.platform, "machine", lambda: "")
    check = doctor._check_cpu_arch("kvm")

    assert check.state == doctor.STATE_UNKNOWN
    assert not check.ok


# ── les ressources face au contrat ────────────────────────────────────────────

def test_des_ressources_suffisantes_sont_vertes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(doctor, "_mem_available_mb", lambda: 8192)
    monkeypatch.setattr(doctor, "_pool_available_gb", lambda pool: 100)

    check = doctor._check_resources(_infra(), "kvm")

    assert check.key == "resources"
    assert check.state == doctor.STATE_OK
    # Le détail montre l'offre ET la demande : c'est la comparaison qui parle.
    assert "3072" in check.detail
    assert "25" in check.detail


def test_une_ram_insuffisante_echoue_en_le_chiffrant(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """4 Go de poste pour 3 Go de catalogue, mais 2 Go réellement libres :
    c'est le cas de terrain, celui du provisionnement expiré à 181 s."""
    monkeypatch.setattr(doctor, "_mem_available_mb", lambda: 2048)
    monkeypatch.setattr(doctor, "_pool_available_gb", lambda pool: 100)

    check = doctor._check_resources(_infra(), "kvm")

    assert check.state == doctor.STATE_FAILED
    assert "2048" in check.detail
    assert "3072" in check.detail


def test_un_disque_insuffisant_echoue_aussi(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(doctor, "_mem_available_mb", lambda: 8192)
    monkeypatch.setattr(doctor, "_pool_available_gb", lambda pool: 8)

    check = doctor._check_resources(_infra(), "kvm")

    assert check.state == doctor.STATE_FAILED


def test_une_sonde_impossible_ne_vaut_jamais_vert(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Pool muet : l'état est `unknown`, ni « ok » menteur ni rouge sans preuve.

    C'est le motif que ce dépôt combat : le contrôle du pool rendait « ok »
    quand virsh ne répondait pas. Un `unknown` n'entre pas dans failing()
    (rien n'est prouvé), mais son jeton dit qu'il n'est pas vert, et le
    document JSON l'expose tel quel.
    """
    monkeypatch.setattr(doctor, "_mem_available_mb", lambda: 8192)
    monkeypatch.setattr(doctor, "_pool_available_gb", lambda pool: None)

    check = doctor._check_resources(_infra(), "kvm")

    assert check.state == doctor.STATE_UNKNOWN
    assert not check.ok

    report = doctor.DoctorReport(required=[check])
    assert not report.failing()
    assert machine.check_dict(check)["state"] == "unknown"


def test_un_manque_mesure_l_emporte_sur_l_inconnu(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """RAM insuffisante ET disque non mesurable : le manque prouvé décide."""
    monkeypatch.setattr(doctor, "_mem_available_mb", lambda: 1024)
    monkeypatch.setattr(doctor, "_pool_available_gb", lambda pool: None)

    check = doctor._check_resources(_infra(), "kvm")

    assert check.state == doctor.STATE_FAILED


# ── le classement : requis là où ça bloque, absent ailleurs ───────────────────

_NOUVELLES_CLES = {"hw_virt", "cpu_arch", "resources"}


def _cles(checks: list[doctor.Check]) -> set[str]:
    return {c.key for c in checks}


def test_requis_sur_un_catalogue_vm_a_provider_local(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(doctor, "get_all_labs", lambda root: [_lab("a", RuntimeType.VM)])
    monkeypatch.setattr(doctor, "_mem_available_mb", lambda: 8192)
    monkeypatch.setattr(doctor, "_pool_available_gb", lambda pool: 100)
    monkeypatch.setattr(doctor.platform, "machine", lambda: "x86_64")
    monkeypatch.setattr(doctor, "_KVM_DEVICE", tmp_path / "absent")

    report = doctor.collect_checks(tmp_path, _repo("kvm", _infra()))

    assert _cles(report.required) >= _NOUVELLES_CLES
    # /dev/kvm absent : le diagnostic doit le porter en échec, pas en silence.
    assert "hw_virt" in {c.key for c in report.failing()}


def test_absents_dun_catalogue_entierement_shell(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`terraform-training` : aucun bloc infra, aucun lab vm — aucun rouge.

    Ces contrôles n'ont rien à y mesurer : ils n'apparaissent nulle part,
    plutôt que d'y peindre en rouge une machine qui va très bien.
    """
    monkeypatch.setattr(
        doctor, "get_all_labs", lambda root: [_lab("a", RuntimeType.SHELL)]
    )
    monkeypatch.setattr(doctor, "_KVM_DEVICE", tmp_path / "absent")

    report = doctor.collect_checks(tmp_path, _repo(""))

    assert not _NOUVELLES_CLES & _cles(report.required)
    assert not _NOUVELLES_CLES & _cles(report.optional)
    assert not report.failing()


def test_absents_quand_le_provider_est_distant(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Un provider cloud provisionne ailleurs : rien à mesurer sur ce poste."""
    monkeypatch.setattr(doctor, "get_all_labs", lambda root: [_lab("a", RuntimeType.VM)])
    monkeypatch.setattr(doctor, "_KVM_DEVICE", tmp_path / "absent")

    report = doctor.collect_checks(tmp_path, _repo("outscale"))

    assert not _NOUVELLES_CLES & _cles(report.required)


def test_sans_hote_declare_les_ressources_se_taisent(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Zéro hôte dans le meta.yml : aucune demande, donc rien à comparer."""
    monkeypatch.setattr(doctor, "get_all_labs", lambda root: [_lab("a", RuntimeType.VM)])
    monkeypatch.setattr(doctor.platform, "machine", lambda: "x86_64")
    device = tmp_path / "kvm"
    device.touch()
    monkeypatch.setattr(doctor, "_KVM_DEVICE", device)

    report = doctor.collect_checks(tmp_path, _repo("kvm"))

    assert "resources" not in _cles(report.required)
    assert _cles(report.required) >= {"hw_virt", "cpu_arch"}
