"""Provider recommendation must not impose an unusable local hypervisor."""
from types import SimpleNamespace

import pytest

from dsoxlab.services import doctor


@pytest.fixture
def local_host(monkeypatch):
    monkeypatch.setattr(doctor.platform, "system", lambda: "Linux")
    monkeypatch.setattr(doctor.platform, "machine", lambda: "x86_64")
    monkeypatch.setattr(doctor, "_kvm_present", lambda: True)
    monkeypatch.setattr(doctor.os, "access", lambda *args: True)
    monkeypatch.setattr(doctor, "_check_kvm", lambda: SimpleNamespace(ok=False))
    monkeypatch.setattr(doctor, "_check_incus", lambda: SimpleNamespace(ok=True))


def test_existing_incus_preferred(local_host):
    assert doctor.provider_recommande(["kvm", "incus"]) == "incus"


def test_remote_without_virtualization(local_host, monkeypatch):
    monkeypatch.setattr(doctor, "_kvm_present", lambda: False)
    assert doctor.provider_recommande(["kvm", "incus", "outscale"]) == "outscale"
    assert doctor.provider_recommande(["kvm", "incus"]) == ""


def test_no_implicit_provider():
    assert doctor.provider_recommande([]) == ""


def test_kvm_image_architecture(local_host, monkeypatch):
    monkeypatch.setattr(doctor.platform, "machine", lambda: "aarch64")
    assert doctor.provider_recommande(["kvm", "incus"]) == "incus"
    assert doctor.provider_recommande(["kvm"]) == ""
