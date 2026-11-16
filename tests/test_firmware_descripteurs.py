"""Le firmware EFI sans Secure Boot, retrouvé par les descripteurs QEMU (issue #381).

Mesuré le 2026-11-16 sur AlmaLinux 10.2 : edk2-ovmf installe
/usr/share/edk2/ovmf/OVMF_CODE.fd, sans Secure Boot, mais `virsh
domcapabilities` ne cite que OVMF_CODE.secboot.fd. dsoxlab ne lisait que cette
liste : aucun lab vm ne pouvait se provisionner sur la famille RHEL 10. Les
descripteurs ci-dessous reprennent ceux de cette machine, aux chemins près.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from dsoxlab.infra import libvirt


def _descripteur(executable: Path, *, features: list[str] | None = None, mode: str = "split",
                 machines: list[str] | None = None, architecture: str = "x86_64",
                 nvram: bool = True) -> dict[str, Any]:
    mapping: dict[str, Any] = {"device": "flash", "mode": mode,
                               "executable": {"filename": str(executable), "format": "raw"}}
    if nvram:
        mapping["nvram-template"] = {"filename": str(executable.with_name("VARS.fd")), "format": "raw"}
    return {
        "interface-types": ["uefi"],
        "mapping": mapping,
        "targets": [{"architecture": architecture, "machines": machines or ["pc-q35-*"]}],
        "features": features if features is not None else ["acpi-s3", "verbose-dynamic"],
    }


def _poser(dossier: Path, nom: str, contenu: dict[str, Any]) -> None:
    dossier.mkdir(parents=True, exist_ok=True)
    (dossier / nom).write_text(json.dumps(contenu), encoding="utf-8")


@pytest.fixture
def firmwares(tmp_path: Path) -> dict[str, Path]:
    chemins = {}
    for nom in ("CODE.fd", "CODE.secboot.fd", "CODE.amdsev.fd", "CODE.aarch64.fd"):
        chemin = tmp_path / "edk2" / nom
        chemin.parent.mkdir(parents=True, exist_ok=True)
        chemin.write_bytes(b"\0")
        chemins[nom] = chemin
    return chemins


def test_le_firmware_sans_secure_boot_d_alma_10_est_retenu(
    tmp_path: Path, firmwares: dict[str, Path]
) -> None:
    usr = tmp_path / "usr"
    _poser(usr, "30-edk2-ovmf-x64-sb-enrolled.json", _descripteur(
        firmwares["CODE.secboot.fd"], features=["secure-boot", "enrolled-keys", "requires-smm"]))
    _poser(usr, "40-edk2-ovmf-x64-sb.json", _descripteur(
        firmwares["CODE.secboot.fd"], features=["requires-smm", "secure-boot"]))
    _poser(usr, "50-edk2-ovmf-x64-nosb.json", _descripteur(
        firmwares["CODE.fd"], features=["acpi-s3", "amd-sev", "amd-sev-es", "verbose-dynamic"]))
    assert libvirt.firmware_des_descripteurs((usr,)) == str(firmwares["CODE.fd"])


def test_rien_quand_tout_est_secure_boot(tmp_path: Path, firmwares: dict[str, Path]) -> None:
    usr = tmp_path / "usr"
    _poser(usr, "40-sb.json", _descripteur(firmwares["CODE.secboot.fd"], features=["secure-boot"]))
    assert libvirt.firmware_des_descripteurs((usr,)) is None


def test_un_firmware_stateless_ou_sans_nvram_est_ecarte(
    tmp_path: Path, firmwares: dict[str, Path]
) -> None:
    usr = tmp_path / "usr"
    _poser(usr, "60-amdsev.json", _descripteur(firmwares["CODE.amdsev.fd"], mode="stateless"))
    _poser(usr, "61-sans-nvram.json", _descripteur(firmwares["CODE.fd"], nvram=False))
    assert libvirt.firmware_des_descripteurs((usr,)) is None


def test_une_autre_architecture_ou_un_executable_absent_est_ecarte(
    tmp_path: Path, firmwares: dict[str, Path]
) -> None:
    usr = tmp_path / "usr"
    _poser(usr, "40-aarch64.json", _descripteur(firmwares["CODE.aarch64.fd"], architecture="aarch64",
                                                machines=["virt-*"]))
    _poser(usr, "50-absent.json", _descripteur(tmp_path / "nulle-part" / "CODE.fd"))
    assert libvirt.firmware_des_descripteurs((usr,)) is None


def test_etc_masque_le_fichier_de_meme_nom_sous_usr_share(
    tmp_path: Path, firmwares: dict[str, Path]
) -> None:
    etc, usr = tmp_path / "etc", tmp_path / "usr"
    _poser(usr, "50-nosb.json", _descripteur(firmwares["CODE.fd"]))
    _poser(etc, "50-nosb.json", _descripteur(firmwares["CODE.secboot.fd"], features=["secure-boot"]))
    assert libvirt.firmware_des_descripteurs((etc, usr)) is None


def test_un_descripteur_illisible_n_arrete_pas_la_recherche(
    tmp_path: Path, firmwares: dict[str, Path]
) -> None:
    usr = tmp_path / "usr"
    usr.mkdir()
    (usr / "10-casse.json").write_text("{pas du json", encoding="utf-8")
    _poser(usr, "50-nosb.json", _descripteur(firmwares["CODE.fd"]))
    assert libvirt.firmware_des_descripteurs((usr,)) == str(firmwares["CODE.fd"])


_DOMCAPS_SECBOOT_SEUL = """<domainCapabilities><os supported='yes'><loader supported='yes'>
<value>/usr/share/OVMF/OVMF_CODE.secboot.fd</value>
<enum name='type'><value>rom</value><value>pflash</value></enum>
</loader></os></domainCapabilities>"""


def test_efi_loader_se_replie_sur_les_descripteurs_comme_sur_alma_10(
    tmp_path: Path, firmwares: dict[str, Path], monkeypatch: pytest.MonkeyPatch
) -> None:
    from dsoxlab.utils.shell import CommandResult

    usr = tmp_path / "usr"
    _poser(usr, "50-nosb.json", _descripteur(firmwares["CODE.fd"]))
    monkeypatch.setattr(libvirt, "run_virsh",
                        lambda args, check=True: CommandResult(0, _DOMCAPS_SECBOOT_SEUL, ""))
    monkeypatch.setattr(libvirt, "DOSSIERS_FIRMWARE", (usr,))
    assert libvirt.efi_loader() == str(firmwares["CODE.fd"])


def test_efi_loader_garde_domcapabilities_quand_il_suffit(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from dsoxlab.utils.shell import CommandResult

    domcaps = _DOMCAPS_SECBOOT_SEUL.replace(
        "<value>/usr/share/OVMF/OVMF_CODE.secboot.fd</value>",
        "<value>/usr/share/OVMF/OVMF_CODE_4M.fd</value><value>/usr/share/OVMF/OVMF_CODE.secboot.fd</value>",
    )
    monkeypatch.setattr(libvirt, "run_virsh", lambda args, check=True: CommandResult(0, domcaps, ""))

    def interdit(*_a: object, **_k: object) -> None:
        raise AssertionError("les descripteurs ne sont lus qu'en repli")

    monkeypatch.setattr(libvirt, "firmware_des_descripteurs", interdit)
    assert libvirt.efi_loader() == "/usr/share/OVMF/OVMF_CODE_4M.fd"
