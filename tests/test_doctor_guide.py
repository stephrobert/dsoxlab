"""Le diagnostic qui guide jusqu'au bout (refonte du 2026-11-16).

Ce que ce module prouve, sans toucher la machine :

- la table des remèdes donne une commande à coller pour chaque étape, par
  famille de distribution, et jamais un lien ;
- la ligne Include se pose en tête de ``~/.ssh/config``, que le fichier soit
  absent, vide ou rempli (``sed -i '1i …'`` n'écrit rien dans un fichier vide) ;
- les nouveaux contrôles (groupes, firmware EFI, clé du catalogue, Include)
  disent la bonne chose dans chacun de leurs cas ;
- aucun contrôle ne se cache : sans libvirt, le pool, le groupe et le firmware
  attendent l'étape qui l'installe ;
- les étapes se numérotent dans l'ordre des dépendances, et deux contrôles
  réparés par la même commande sont une seule étape ;
- la mémoire qui ne suffit pas pour tout le catalogue informe sans bloquer,
  sauf pour ``start <lab>``.
"""

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

import pytest

from dsoxlab.infra import inventory
from dsoxlab.models.lab import LabDefinition, ValidationConfig
from dsoxlab.models.repo import HostDefinition, InfraDefinition, RepoMetadata
from dsoxlab.models.runtime import RuntimeConfig, RuntimeType, Target
from dsoxlab.services import doctor
from dsoxlab.services.doctor_controles import kvm as kvm_controles
from dsoxlab.services.doctor_controles import remedes
from dsoxlab.services.doctor_controles.catalogue import creer_cle_ssh
from dsoxlab.services.doctor_controles.outillage import _terraform_depasse
from dsoxlab.services.doctor_etapes import construire

UBUNTU = 'ID=ubuntu\nID_LIKE=debian\nPRETTY_NAME="Ubuntu 24.04.5 LTS"\n'
ALMA = 'ID="almalinux"\nID_LIKE="rhel centos fedora"\nPRETTY_NAME="AlmaLinux 10.2"\n'


def _os_release(monkeypatch: pytest.MonkeyPatch, tmp_path: Path, contenu: str) -> None:
    fichier = tmp_path / "os-release"
    fichier.write_text(contenu, encoding="utf-8")
    monkeypatch.setattr(remedes, "OS_RELEASE", fichier)


# ── la famille de distribution ────────────────────────────────────────────────

@pytest.mark.parametrize(("contenu", "famille", "identifiant"), [
    (UBUNTU, remedes.Famille.DEBIAN, "ubuntu"),
    ("ID=debian\n", remedes.Famille.DEBIAN, "debian"),
    (ALMA, remedes.Famille.RHEL, "almalinux"),
    ('ID=fedora\nPRETTY_NAME="Fedora Linux 43"\n', remedes.Famille.RHEL, "fedora"),
    ('ID="rocky"\nID_LIKE="rhel centos fedora"\n', remedes.Famille.RHEL, "rocky"),
])
def test_la_famille_se_lit_dans_os_release(
    tmp_path: Path, contenu: str, famille: remedes.Famille, identifiant: str,
) -> None:
    fichier = tmp_path / "os-release"
    fichier.write_text(contenu, encoding="utf-8")
    systeme = remedes.systeme(fichier)
    assert (systeme.famille, systeme.identifiant) == (famille, identifiant)


def test_un_os_release_absent_retombe_sur_le_gestionnaire_present(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(remedes.shutil, "which", lambda n: "/usr/bin/dnf" if n == "dnf" else None)
    assert remedes.systeme(tmp_path / "absent").famille is remedes.Famille.RHEL
    monkeypatch.setattr(remedes.shutil, "which", lambda n: None)
    assert remedes.systeme(tmp_path / "absent").famille is remedes.Famille.DEBIAN


# ── la table des remèdes ──────────────────────────────────────────────────────

@pytest.mark.parametrize("contenu", [UBUNTU, ALMA, 'ID=fedora\n', "ID=debian\n"])
def test_chaque_etape_a_une_commande_et_jamais_un_lien(tmp_path: Path, contenu: str) -> None:
    fichier = tmp_path / "os-release"
    fichier.write_text(contenu, encoding="utf-8")
    systeme = remedes.systeme(fichier)
    for cle in remedes.TABLE:
        remede = remedes.remede(cle, systeme)
        if cle == "incus" and systeme.famille is remedes.Famille.RHEL:
            assert remede is None, "incus n'est dans aucun dépôt de base de la famille RHEL"
            continue
        assert remede is not None, cle
        assert remede.lignes, cle
        assert not any(ligne.startswith(("http://", "https://")) for ligne in remede.lignes), cle
        # `root` se lit dans les lignes : il décide du playbook, il ne peut
        # pas contredire la commande qu'il décrit.
        assert remede.root == any("sudo " in ligne for ligne in remede.lignes), cle


def test_terraform_vient_du_depot_hashicorp_de_chaque_famille(tmp_path: Path) -> None:
    for contenu, attendu in (
        (UBUNTU, "https://apt.releases.hashicorp.com"),
        (ALMA, "https://rpm.releases.hashicorp.com/RHEL/hashicorp.repo"),
        ("ID=fedora\n", "https://rpm.releases.hashicorp.com/fedora/hashicorp.repo"),
    ):
        fichier = tmp_path / "os-release"
        fichier.write_text(contenu, encoding="utf-8")
        remede = remedes.remede("terraform", remedes.systeme(fichier))
        assert remede is not None
        assert any(attendu in ligne for ligne in remede.lignes), contenu


def test_docker_vise_le_depot_de_sa_distribution(tmp_path: Path) -> None:
    for contenu, attendu in ((UBUNTU, "linux/ubuntu"), ("ID=debian\n", "linux/debian"),
                             (ALMA, "linux/rhel")):
        fichier = tmp_path / "os-release"
        fichier.write_text(contenu, encoding="utf-8")
        remede = remedes.remede("docker", remedes.systeme(fichier))
        assert remede is not None
        assert any(f"https://download.docker.com/{attendu}" in ligne for ligne in remede.lignes)


def test_l_ordre_de_la_table_est_celui_des_dependances() -> None:
    rang = remedes.rang
    assert rang("git") < rang("kvm") < rang("groupes") < rang("libvirt_pool") < rang("efi")
    assert rang("ansible") < rang("collections")
    assert rang("inconnue") == len(remedes.TABLE)


# ── la ligne Include de ~/.ssh/config ─────────────────────────────────────────

_CONTENUS = {"absent": None, "vide": "", "rempli": "Host forge\n  User git\n"}


@pytest.mark.skipif(shutil.which("bash") is None, reason="bash absent")
@pytest.mark.parametrize("cas", list(_CONTENUS))
def test_la_commande_affichee_marche_sur_un_fichier_vide_absent_ou_rempli(
    tmp_path: Path, cas: str,
) -> None:
    """La commande telle qu'affichée, jouée par bash dans un HOME jetable."""
    contenu = _CONTENUS[cas]
    if contenu is not None:
        (tmp_path / ".ssh").mkdir()
        (tmp_path / ".ssh" / "config").write_text(contenu, encoding="utf-8")
    ligne = remedes.remede("ssh_include", remedes.systeme())
    assert ligne is not None
    subprocess.run(["bash", "-c", ligne.lignes[0]], env={**os.environ, "HOME": str(tmp_path)},
                   check=True)

    config = tmp_path / ".ssh" / "config"
    assert config.read_text(encoding="utf-8") == f"{inventory.LIGNE_INCLUDE}\n{contenu or ''}"
    assert config.stat().st_mode & 0o777 == 0o600


@pytest.mark.parametrize("cas", list(_CONTENUS))
def test_fix_pose_l_include_en_tete_quel_que_soit_le_fichier(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, cas: str,
) -> None:
    monkeypatch.setenv("HOME", str(tmp_path))
    contenu = _CONTENUS[cas]
    if contenu is not None:
        (tmp_path / ".ssh").mkdir()
        (tmp_path / ".ssh" / "config").write_text(contenu, encoding="utf-8")
    assert not inventory.ssh_config_include_present()

    inventory.ajouter_include_ssh()

    config = tmp_path / ".ssh" / "config"
    assert config.read_text(encoding="utf-8").splitlines()[0] == inventory.LIGNE_INCLUDE
    assert config.read_text(encoding="utf-8").endswith(contenu or "\n")
    assert config.stat().st_mode & 0o777 == 0o600
    assert inventory.ssh_config_include_present()
    assert doctor._check_ssh_include().ok


# ── Terraform : la version plus récente, sous -v seulement ────────────────────

def test_une_version_depassee_devient_une_mise_en_garde() -> None:
    sortie = (
        "Terraform v1.16.1\non linux_amd64\n\nYour version of Terraform is out of date! "
        "The latest version\nis 1.17.2. You can update by downloading from "
        "https://developer.hashicorp.com/terraform/install\n"
    )
    garde = _terraform_depasse(sortie)
    assert garde is not None and "1.17.2" in garde
    assert _terraform_depasse("Terraform v1.17.2\non linux_amd64\n") is None


# ── les groupes kvm et libvirt ────────────────────────────────────────────────

@pytest.fixture
def groupes(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> dict[str, object]:
    """Pilote les sondes du contrôle des groupes : /dev/kvm, /etc/group, la session."""
    etat: dict[str, object] = {"gids": {"libvirt": 106}, "session": set(), "inscrits": set()}
    device = tmp_path / "kvm"
    device.touch()
    monkeypatch.setattr(doctor, "_KVM_DEVICE", device)
    monkeypatch.setattr(kvm_controles.os, "access", lambda p, m: True)
    monkeypatch.setattr(kvm_controles, "_gid", lambda n: etat["gids"].get(n))  # type: ignore[attr-defined]  # noqa: PLW0108 — relu à chaque appel
    monkeypatch.setattr(kvm_controles, "_dans_la_session", lambda g: g in etat["session"])  # type: ignore[operator]
    monkeypatch.setattr(kvm_controles, "_inscrit", lambda n, g: n in etat["inscrits"])  # type: ignore[operator]
    return etat


def test_un_compte_dans_le_groupe_est_vert(groupes: dict[str, object]) -> None:
    groupes["session"] = {106}
    assert doctor._check_groupes(kvm_ok=True).ok


def test_sans_libvirt_le_groupe_attend_l_etape_kvm(groupes: dict[str, object]) -> None:
    groupes["gids"] = {}
    check = doctor._check_groupes(kvm_ok=False)
    assert check.state == doctor.STATE_UNKNOWN
    assert check.apres == "kvm"
    assert check.remede is not None
    assert check.remede.lignes == ("sudo usermod -aG libvirt $USER",)


def test_un_compte_absent_du_groupe_recoit_usermod(groupes: dict[str, object]) -> None:
    check = doctor._check_groupes(kvm_ok=True)
    assert check.state == doctor.STATE_FAILED
    assert check.remede is not None and check.remede.reconnexion
    assert "usermod -aG libvirt" in check.remede.lignes[0]


def test_un_compte_inscrit_mais_pas_reconnecte_n_a_qu_a_se_reconnecter(
    groupes: dict[str, object],
) -> None:
    """Rejouer usermod ne changerait rien : seule la reconnexion compte."""
    groupes["inscrits"] = {"libvirt"}
    check = doctor._check_groupes(kvm_ok=True)
    assert check.state == doctor.STATE_FAILED
    assert check.remede is not None
    assert check.remede.lignes == ()
    assert check.remede.reconnexion


def test_un_dev_kvm_ferme_ajoute_le_groupe_kvm(
    groupes: dict[str, object], monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(kvm_controles.os, "access", lambda p, m: False)
    check = doctor._check_groupes(kvm_ok=True)
    assert check.remede is not None
    assert check.remede.lignes == ("sudo usermod -aG kvm,libvirt $USER",)


# ── le firmware EFI ───────────────────────────────────────────────────────────

def test_le_firmware_attend_libvirt() -> None:
    check = doctor._check_efi(kvm_ok=False)
    assert check.state == doctor.STATE_UNKNOWN
    assert check.apres == "kvm"


def test_le_firmware_trouve_est_nomme(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(kvm_controles.libvirt_infra, "efi_loader",
                        lambda: "/usr/share/OVMF/OVMF_CODE_4M.fd")
    check = doctor._check_efi(kvm_ok=True)
    assert check.ok and check.detail == "OVMF_CODE_4M.fd"


def test_sans_firmware_le_paquet_efi_est_propose(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    _os_release(monkeypatch, tmp_path, ALMA)
    monkeypatch.setattr(kvm_controles.libvirt_infra, "efi_loader", lambda: None)
    check = doctor._check_efi(kvm_ok=True)
    assert check.state == doctor.STATE_FAILED
    assert check.remede is not None and check.remede.lignes == ("sudo dnf install edk2-ovmf",)


# ── la clé SSH du catalogue ───────────────────────────────────────────────────

def test_une_cle_absente_fait_proposer_bootstrap(tmp_path: Path) -> None:
    check = doctor._check_cle_ssh(tmp_path)
    assert check.state == doctor.STATE_FAILED
    assert check.remede is not None
    assert check.remede.lignes == ("dsoxlab instructor bootstrap",)


@pytest.mark.skipif(shutil.which("ssh-keygen") is None, reason="ssh-keygen absent")
def test_fix_cree_la_cle_que_le_controle_attend(tmp_path: Path) -> None:
    assert creer_cle_ssh(tmp_path) is None
    assert doctor._check_cle_ssh(tmp_path).ok
    assert (tmp_path / "ssh").stat().st_mode & 0o777 == 0o700
    # Une seconde fois ne réécrit rien.
    empreinte = (tmp_path / "ssh" / "id_ed25519.pub").read_text(encoding="utf-8")
    assert creer_cle_ssh(tmp_path) is None
    assert (tmp_path / "ssh" / "id_ed25519.pub").read_text(encoding="utf-8") == empreinte


# ── kvm : un démon qui ne répond pas s'active pour de bon ─────────────────────

def test_libvirtd_s_active_au_demarrage_et_pas_seulement_maintenant(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """`systemctl start` ne survit pas au redémarrage : le rouge revenait."""
    monkeypatch.setattr(doctor.shutil, "which", lambda n: f"/usr/bin/{n}")
    monkeypatch.setattr(doctor, "_sonde_virsh", lambda args, delai=5: None)
    check = doctor._check_kvm()
    assert check.fix is not None
    assert check.fix.commands == (("sudo", "systemctl", "enable", "--now", "libvirtd"),)


# ── le classement : rien ne se cache, la mémoire informe ──────────────────────

def _lab() -> LabDefinition:
    return LabDefinition(
        id="a", title="a", level="l1", skills=["s"],
        runtime=RuntimeConfig(type=RuntimeType.VM, targets=[Target(name="t", host="a.lab")]),
        distros=["alma10"], doc_url="https://example.test/doc", validation=ValidationConfig(),
    )


@pytest.fixture
def machine_vide(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> RepoMetadata:
    """Un catalogue à deux machines (3 Go) sur un poste sans rien, 2 Go libres."""
    _os_release(monkeypatch, tmp_path, UBUNTU)
    monkeypatch.setenv("HOME", str(tmp_path))
    device = tmp_path / "kvm"
    device.touch()
    monkeypatch.setattr(doctor, "_KVM_DEVICE", device)
    monkeypatch.setattr(doctor, "get_all_labs", lambda root: [_lab()])
    monkeypatch.setattr(doctor.shutil, "which", lambda n: None)
    monkeypatch.setattr(doctor.ansible_infra, "has_ansible_playbook", lambda: False)
    monkeypatch.setattr(doctor, "_mem_available_mb", lambda: 2048)
    monkeypatch.setattr(doctor, "_check_egress", lambda: doctor._check("egress", True, "ok"))
    monkeypatch.setattr(kvm_controles, "_gid", lambda n: None)
    return RepoMetadata(id="demo", category="demo", infra=InfraDefinition(
        provider="kvm",
        hosts=[HostDefinition(name="a.lab", ram_mb=2048), HostDefinition(name="b.lab", ram_mb=1024)],
    ))


def test_une_machine_vide_voit_tous_ses_manques_en_une_passe(
    tmp_path: Path, machine_vide: RepoMetadata,
) -> None:
    plan = construire(doctor.collect_checks(tmp_path, machine_vide))
    cles = [e.cle for e in plan.etapes]

    assert cles == ["git", "kvm", "groupes", "libvirt_pool", "efi", "terraform", "ansible",
                    "cle_ssh", "ssh_include"]
    numero = {e.cle: e.numero for e in plan.etapes}
    attente = {e.cle: e.apres for e in plan.etapes}
    for cle in ("groupes", "libvirt_pool", "efi"):
        assert attente[cle] == numero["kvm"], cle
    assert attente["git"] is None and attente["terraform"] is None


def test_la_memoire_de_tout_le_catalogue_informe_sans_bloquer(
    tmp_path: Path, machine_vide: RepoMetadata,
) -> None:
    report = doctor.collect_checks(tmp_path, machine_vide)

    assert "resources" not in {c.key for c in report.required}
    assert [c.key for c in report.a_savoir] == ["resources"]
    assert report.a_savoir[0].hint == "dsoxlab provision --host a.lab"


def test_start_garde_la_memoire_bloquante_pour_son_lab(
    tmp_path: Path, machine_vide: RepoMetadata,
) -> None:
    """`start <lab>` passe ses hôtes : là, la mémoire manque pour CE lab."""
    report = doctor.collect_checks(tmp_path, machine_vide, hosts=["a.lab", "b.lab"])

    assert "resources" in {c.key for c in report.failing()}
    assert not report.a_savoir


def test_deux_controles_repares_par_la_meme_commande_font_une_etape(
    tmp_path: Path, machine_vide: RepoMetadata, monkeypatch: pytest.MonkeyPatch,
) -> None:
    """/dev/kvm fermé et groupe libvirt absent : une étape, la commande du groupe."""
    monkeypatch.setattr(doctor.os, "access", lambda p, m: False)
    monkeypatch.setattr(kvm_controles.os, "access", lambda p, m: False)
    plan = construire(doctor.collect_checks(tmp_path, machine_vide))

    groupes = [e for e in plan.etapes if e.cle == "groupes"]
    assert len(groupes) == 1
    assert {c.key for c in groupes[0].controles} == {"hw_virt", "groupes"}
    assert groupes[0].remede is not None
    assert groupes[0].remede.lignes == ("sudo usermod -aG kvm,libvirt $USER",)


def test_un_provider_a_choisir_n_arrete_plus_le_diagnostic(
    tmp_path: Path, machine_vide: RepoMetadata,
) -> None:
    machine_vide.infra.provider = ""
    machine_vide.infra.providers_available = ["kvm", "incus"]
    report = doctor.collect_checks(tmp_path, machine_vide)
    plan = construire(report)

    assert report.provider == "kvm" and report.provider_a_confirmer
    assert plan.etapes[0].cle in ("git", "provider")
    assert {"provider", "kvm", "libvirt_pool"} <= {e.cle for e in plan.etapes}
    assert "incus" not in {e.cle for e in plan.etapes}


@pytest.mark.parametrize(("candidats", "kvm_present", "attendu"), [
    (["kvm", "incus"], True, "kvm"),
    (["incus", "kvm"], True, "kvm"),
    (["kvm", "incus"], False, "kvm"),
    (["outscale", "incus"], True, "incus"),
    (["outscale"], True, "outscale"),
])
def test_le_provider_recommande(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
    candidats: list[str], kvm_present: bool, attendu: str,
) -> None:
    device = tmp_path / "kvm"
    if kvm_present:
        device.touch()
    monkeypatch.setattr(doctor, "_KVM_DEVICE", device)
    assert doctor.provider_recommande(candidats) == attendu


def test_les_collections_attendent_ansible_avec_leur_commande(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Le « ? ansible-galaxy n'a pas répondu » cachait la vraie cause."""
    (tmp_path / "requirements.yml").write_text(
        "collections:\n  - name: community.general\n", encoding="utf-8",
    )
    monkeypatch.setattr(doctor.ansible_infra, "has_ansible_playbook", lambda: False)
    monkeypatch.setattr("dsoxlab.services.collections_ansible.collections_installees", lambda: None)
    check = doctor._check_collections(tmp_path)

    assert check.state == doctor.STATE_UNKNOWN
    assert check.apres == "ansible"
    assert check.fix is not None
    assert check.fix.commands == (
        ("ansible-galaxy", "collection", "install", "-r", str(tmp_path / "requirements.yml")),
    )


# ── le document JSON : des ajouts, rien de retiré ─────────────────────────────

def test_le_json_porte_les_commandes_l_attente_et_la_mise_en_garde(
    tmp_path: Path, machine_vide: RepoMetadata,
) -> None:
    from dsoxlab.reporting import machine

    document = machine.doctor_dict(doctor.collect_checks(tmp_path, machine_vide))
    par_cle = {c["key"]: c for c in [*document["required"], *document["informational"]]}

    for champ in ("key", "state", "ok", "label", "detail", "fix", "fix_kind", "hint"):
        assert champ in par_cle["kvm"], champ
    assert par_cle["kvm"]["commands"] == [
        "sudo apt install libvirt-clients libvirt-daemon-system qemu-kvm",
    ]
    assert par_cle["libvirt_pool"]["after"] == "kvm"
    assert par_cle["libvirt_pool"]["state"] == "unknown"
    assert par_cle["git"]["warning"] is None
    # La mémoire de tout le catalogue informe : elle n'est plus dans `required`.
    assert "resources" not in {c["key"] for c in document["required"]}
    assert "resources" in {c["key"] for c in document["informational"]}
