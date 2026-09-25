"""Les versions que dsoxlab prend en charge, et celles qui tournent vraiment.

Rien ne disait qu'une version de libvirt pouvait être trop ancienne. Sur
libvirt 8.0, `provision` échoue parce que l'autoselect EFI
(`os.firmware = "efi"`) ne survit pas à la relecture du XML par le provider
Terraform, et l'erreur arrive en langage Terraform : « Provider produced
inconsistent result after apply » (issue #234). Rien ne nommait la version, ni la
cause, ni le geste.

L'enquête a demandé de comparer à la main deux rapports `dsoxlab support` dont
aucun ne portait la version du provider Terraform. C'est pourtant elle qui décide
du comportement : la contrainte du template, `~> 0.9`, laisse passer plusieurs
versions, et deux postes qui l'honorent tous les deux ne se comportent pas
pareil.

Le plancher est **mesuré**, pas supposé : 10.0.0 provisionne (vérifié en
provisionnant une VM AlmaLinux 10), 8.0.0 échoue (rapporté). 9.x n'a été éprouvé
par personne et passe au bénéfice du doute, plutôt que d'exclure Debian 12 et
AlmaLinux 9 qu'aucune mesure ne condamne.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from dsoxlab.models.repo import HostDefinition, InfraDefinition, RepoMetadata
from dsoxlab.services import doctor

VIRSH_10 = (
    "Compiled against library: libvirt 10.0.0\n"
    "Using library: libvirt 10.0.0\n"
    "Using API: QEMU 10.0.0\n"
    "Running hypervisor: QEMU 8.2.2\n"
)
VIRSH_8 = (
    "Compiled against library: libvirt 8.0.0\n"
    "Using library: libvirt 8.0.0\n"
    "Using API: QEMU 8.0.0\n"
    "Running hypervisor: QEMU 6.2.0\n"
)


# ── lire la version, sans se tromper de ligne ─────────────────────────────────

def test_la_version_lue_est_bien_celle_qui_tourne() -> None:
    """« Using library » l'emporte sur « Compiled against ».

    Les deux diffèrent après une mise à jour de la bibliothèque sans redémarrage
    du client, et c'est celle qui tourne qui décide du comportement.
    """
    melange = (
        "Compiled against library: libvirt 8.0.0\n"
        "Using library: libvirt 10.0.0\n"
    )

    assert doctor._version_libvirt(melange) == (10, 0)


def test_une_sortie_abregee_reste_lisible() -> None:
    """Refuser une sortie qui ne porte que « Compiled against » rendrait
    `unknown` un virsh parfaitement sain."""
    assert doctor._version_libvirt("Compiled against 10.0\n") == (10, 0)


@pytest.mark.parametrize("sortie", ["", "bonjour", "libvirt", "Using library: libvirt"])
def test_une_sortie_sans_version_ne_se_devine_pas(sortie: str) -> None:
    assert doctor._version_libvirt(sortie) is None


# ── le plancher, et ses trois issues ──────────────────────────────────────────

def _virsh(monkeypatch: pytest.MonkeyPatch, sortie: str | None) -> None:
    """Simule `virsh version`. ``None`` = la sonde n'a pas abouti."""
    monkeypatch.setattr(doctor.shutil, "which", lambda _nom: "/usr/bin/virsh")

    class _Res:
        ok = True
        stdout = sortie or ""
        stderr = ""

    monkeypatch.setattr(doctor, "_sonde_virsh", lambda _args: _Res())


def test_libvirt_recent_passe(monkeypatch: pytest.MonkeyPatch) -> None:
    _virsh(monkeypatch, VIRSH_10)

    check = doctor._check_kvm()

    assert check.ok
    assert check.state == doctor.STATE_OK


def test_libvirt_8_est_desormais_pris_en_charge(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Le plancher est redescendu de 9.0 à 8.0, et c'est volontaire.

    Il écartait libvirt 8 parce que l'autoselect EFI y échouait. La cause est
    corrigée — le template désigne son loader, découvert dans
    `virsh domcapabilities` — donc refuser cette version punirait des postes pour
    un défaut qui n'existe plus. Un seuil qui survit à sa raison exclut sans rien
    protéger.
    """
    _virsh(monkeypatch, VIRSH_8)

    check = doctor._check_kvm()

    assert check.ok
    assert check.state == doctor.STATE_OK


def test_libvirt_trop_ancien_echoue_et_nomme_la_cause(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Sous le plancher, l'échec se dit ici plutôt qu'en langage Terraform."""
    _virsh(monkeypatch, VIRSH_8.replace("8.0.0", "7.6.0"))

    check = doctor._check_kvm()

    assert not check.ok
    assert check.state == doctor.STATE_FAILED
    assert "7.6" in check.detail
    assert "8.0" in check.detail


def test_une_version_illisible_ne_conclut_pas(monkeypatch: pytest.MonkeyPatch) -> None:
    """Ni vert ni rouge : `--strict` a son propre code pour ce cas (10).

    On ne refuse pas un poste sur une sortie qu'on n'a pas su lire, et on ne le
    déclare pas bon pour autant.
    """
    _virsh(monkeypatch, "virsh 42 (une sortie qu'on ne sait pas lire)\n")

    check = doctor._check_kvm()

    assert check.state == doctor.STATE_UNKNOWN
    assert not check.ok


def test_le_plancher_est_celui_qui_a_ete_mesure() -> None:
    """Le figer ici rend le choix visible, et son changement délibéré.

    Redescendu de 9.0 à 8.0 : 8.0.0 provisionne désormais, mesuré dans une VM
    Ubuntu 22.04 où le défaut avait d'abord été reproduit à l'identique, une fois
    le loader désigné au lieu d'être choisi par libvirt. Rien en dessous de 8.0
    n'a été éprouvé, et c'est la seule raison pour laquelle un plancher subsiste.
    """
    assert doctor._LIBVIRT_MINIMUM == (8, 0)


# ── annoncer le provider Terraform réellement en place ────────────────────────

def _meta(tmp_path: Path) -> RepoMetadata:
    return RepoMetadata(
        id="demo",
        category="demo",
        infra=InfraDefinition(provider="kvm", hosts=[HostDefinition(name="n1.lab")]),
        path=tmp_path,
    )


def _poser_lock(racine: Path, contenu: str) -> None:
    racine.mkdir(parents=True, exist_ok=True)
    (racine / ".terraform.lock.hcl").write_text(contenu, encoding="utf-8")


def test_la_version_du_provider_est_lue_dans_le_verrou(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """C'est la version épinglée qui décide, pas la contrainte du template.

    « ~> 0.9 » laisse passer 0.9.7 comme 0.9.9, et aucune surface ne disait
    laquelle tournait.
    """
    from dsoxlab.infra import terraform

    etat = tmp_path / "etat"
    _poser_lock(etat, """
provider "registry.terraform.io/dmacvicar/libvirt" {
  version     = "0.9.9"
  constraints = "~> 0.9"
}
""")
    monkeypatch.setattr(terraform, "workdir", lambda _meta: etat)

    assert terraform.providers_epingles(_meta(tmp_path)) == {"libvirt": "0.9.9"}


def test_plusieurs_providers_sont_tous_annonces(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from dsoxlab.infra import terraform

    etat = tmp_path / "etat"
    _poser_lock(etat, """
provider "registry.terraform.io/dmacvicar/libvirt" {
  version = "0.9.9"
}

provider "registry.terraform.io/hashicorp/template" {
  version = "2.2.0"
}
""")
    monkeypatch.setattr(terraform, "workdir", lambda _meta: etat)

    assert terraform.providers_epingles(_meta(tmp_path)) == {
        "libvirt": "0.9.9", "template": "2.2.0",
    }


def test_sans_provision_jouee_le_verrou_n_existe_pas(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Ce n'est pas une anomalie : `terraform init` n'a simplement pas tourné."""
    from dsoxlab.infra import terraform

    monkeypatch.setattr(terraform, "workdir", lambda _meta: tmp_path / "jamais")

    assert terraform.providers_epingles(_meta(tmp_path)) == {}


def test_le_controle_des_providers_ne_peint_jamais_en_rouge(tmp_path: Path) -> None:
    """C'est une information, pas un prérequis.

    Aucun plancher n'est connu pour ces providers — le rapporteur de #234 et la
    machine de référence avaient la **même** version 0.9.9 — donc en inventer un
    refuserait des postes sur une supposition.
    """
    check = doctor._check_tf_providers(_meta(tmp_path))

    assert check.ok
    assert check.state == doctor.STATE_OK


# ── écrire des variables ne doit pas exiger un hyperviseur ────────────────────

def _meta_kvm(racine: Path) -> RepoMetadata:
    from dsoxlab.discovery.repo import read_repo_metadata

    (racine / "meta.yml").write_text(
        "repo:\n  id: sentinelle\n  category: domaine\n"
        "infra:\n  provider: kvm\n  network: reseau\n  cidr: 10.10.10.0/24\n"
        "  hosts:\n    - name: hote.lab\n      distro: alma10\n",
        encoding="utf-8",
    )
    meta = read_repo_metadata(racine)
    assert meta is not None
    return meta


def test_write_tfvars_n_exige_pas_libvirt(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Le défaut que la CI a trouvé avant ce test, et qu'il ferme.

    `write_tfvars` ÉCRIT UN FICHIER. L'avoir fait dépendre de
    `libvirt.efi_loader()` la rendait inappelable sans hyperviseur : les
    contrôles de documentation, qui l'invoquent pour chaque provider afin de
    relever les chemins, échouaient tous en intégration continue. Ici, la sonde
    ne rend rien, et l'écriture doit quand même aboutir.
    """
    from dsoxlab.infra import terraform

    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "etat"))
    monkeypatch.setattr(terraform.libvirt, "efi_loader", lambda: None)

    chemin = terraform.write_tfvars(_meta_kvm(tmp_path))

    import json

    assert json.loads(chemin.read_text(encoding="utf-8"))["efi_loader"] == ""


def test_write_tfvars_porte_le_loader_quand_il_existe(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from dsoxlab.infra import terraform

    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "etat"))
    monkeypatch.setattr(
        terraform.libvirt, "efi_loader", lambda: "/usr/share/edk2/ovmf/OVMF_CODE.fd"
    )

    chemin = terraform.write_tfvars(_meta_kvm(tmp_path))

    import json

    assert (
        json.loads(chemin.read_text(encoding="utf-8"))["efi_loader"]
        == "/usr/share/edk2/ovmf/OVMF_CODE.fd"
    )


def test_apply_refuse_de_partir_sans_firmware(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """La vérification a quitté l'écriture pour rejoindre le provisionnement.

    C'est là qu'elle compte : sans chemin, le plan n'a rien à poser, et un
    message qui nomme le paquet OVMF vaut mieux qu'une erreur Terraform sur une
    variable vide.
    """
    from dsoxlab.infra import terraform

    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "etat"))
    monkeypatch.setattr(terraform.libvirt, "efi_loader", lambda: None)

    with pytest.raises(terraform.EfiLoaderUnavailable):
        terraform.apply(_meta_kvm(tmp_path))
