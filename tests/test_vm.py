"""``dsoxlab vm`` : une VM en une commande, sans meta.yml (issue #401).

Le service écrit le ``meta.yml`` qu'on écrirait à la main ; ces tests vérifient
qu'il est lu par le MÊME chemin que les autres (``read_repo_metadata``), que le
pont qu'il ferait créer tient dans la limite du noyau, que le sous-réseau choisi
ne croise rien, et que la CLI refuse ce qu'elle doit refuser sans rien créer.
L'essai réel (création, ssh, destruction sur kvm) est dans la PR : un test
unitaire ne monte pas de VM.
"""

from __future__ import annotations

import ipaddress
import re
from pathlib import Path

import pytest
from typer.testing import CliRunner

from dsoxlab.cli import app
from dsoxlab.discovery.repo import read_repo_metadata
from dsoxlab.infra.pont import IFNAMSIZ_UTILES, nom_du_pont
from dsoxlab.services import vm as vms
from dsoxlab.templates import template_root

runner = CliRunner()


@pytest.fixture(autouse=True)
def donnees_isolees(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "data"))
    monkeypatch.setenv("DSOXLAB_LANG", "en")
    return tmp_path


# ── le nom ────────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("nom", ["a", "essai", "essai-vm", "k8s-1", "x" * 32])
def test_un_nom_d_hote_est_accepte(nom: str) -> None:
    assert vms.verifier_nom(nom) == nom


@pytest.mark.parametrize("nom", ["", "Essai", "essai_vm", "1essai", "essai-", "-a",
                                 "a.b", "x" * 33, "../evasion"])
def test_un_nom_qui_ne_ferait_pas_un_nom_d_hote_est_refuse(nom: str) -> None:
    with pytest.raises(vms.NomRefuse):
        vms.verifier_nom(nom)


# ── le sous-réseau ────────────────────────────────────────────────────────────

def test_le_premier_sous_reseau_libre_de_la_plage_est_choisi() -> None:
    occupes = [ipaddress.IPv4Network("10.10.100.0/24"), ipaddress.IPv4Network("10.10.101.0/24")]
    assert vms.choisir_cidr(occupes) == ipaddress.IPv4Network("10.10.102.0/24")


def test_un_reseau_large_qui_englobe_la_plage_la_rend_entierement_occupee() -> None:
    with pytest.raises(vms.AucunSousReseauLibre):
        vms.choisir_cidr([ipaddress.IPv4Network("10.10.0.0/16")])


def test_un_reseau_qui_ne_croise_pas_la_plage_ne_gene_rien() -> None:
    occupes = [ipaddress.IPv4Network("10.10.50.0/24"), ipaddress.IPv4Network("192.168.1.0/24")]
    assert vms.choisir_cidr(occupes) == ipaddress.IPv4Network("10.10.100.0/24")


# ── le meta.yml écrit ─────────────────────────────────────────────────────────

def test_le_meta_yml_ecrit_se_lit_par_le_chemin_commun() -> None:
    demande = vms.DemandeVM(nom="essai", distro="debian13", ram_mb=4096, vcpu=3,
                            disk_gb=30, extra_disk_gb=5, provider="kvm")
    racine = vms.ecrire(demande, ipaddress.IPv4Network("10.10.137.0/24"))
    repo = read_repo_metadata(racine)
    assert repo.id == "vm-essai"
    assert repo.infra.provider == "kvm"
    assert repo.infra.cidr == "10.10.137.0/24"
    (hote,) = repo.infra.hosts
    assert (hote.name, hote.distro, hote.ram_mb, hote.vcpu, hote.disk_gb, hote.extra_disk_gb) \
        == ("essai.lab", "debian13", 4096, 3, 30, 5)


@pytest.mark.parametrize("provider", vms.PROVIDERS)
@pytest.mark.parametrize("troisieme", [100, 199])
def test_le_pont_tient_dans_la_limite_du_noyau_quel_que_soit_le_nom(
    provider: str, troisieme: int
) -> None:
    """Le réseau porte le numéro du sous-réseau : un nom de VM long ne l'allonge pas."""
    demande = vms.DemandeVM(nom="x" * 32, provider=provider)
    racine = vms.ecrire(demande, ipaddress.IPv4Network(f"10.10.{troisieme}.0/24"))
    pont = nom_du_pont(read_repo_metadata(racine), provider)
    assert pont is not None and len(pont) <= IFNAMSIZ_UTILES


def test_ecrire_refuse_d_ecraser_une_vm_existante() -> None:
    demande = vms.DemandeVM(nom="essai")
    vms.ecrire(demande, ipaddress.IPv4Network("10.10.100.0/24"))
    with pytest.raises(FileExistsError):
        vms.ecrire(demande, ipaddress.IPv4Network("10.10.101.0/24"))


def test_lister_rend_les_vm_ecrites_et_saute_un_dossier_abime() -> None:
    vms.ecrire(vms.DemandeVM(nom="une", ram_mb=1024), ipaddress.IPv4Network("10.10.100.0/24"))
    vms.ecrire(vms.DemandeVM(nom="deux"), ipaddress.IPv4Network("10.10.101.0/24"))
    abime = vms.dossier_des_vm() / "abimee"
    abime.mkdir()
    (abime / "meta.yml").write_text("infra: [pas, un, dict\n", encoding="utf-8")
    connues = vms.lister()
    assert [v.nom for v in connues] == ["deux", "une"]
    assert connues[1].ram_mb == 1024
    assert vms.adresse(connues[1].cidr) == "10.10.100.11"


def test_les_distributions_proposees_sont_celles_des_templates() -> None:
    """Une distro proposée sans template ferait échouer le provision après coup."""
    for provider in ("kvm", "incus", "outscale"):
        main_tf = (template_root() / "terraform" / provider / "main.tf").read_text(encoding="utf-8")
        bloc = re.search(r"distro_to_template\s*=\s*\{(.*?)\}", main_tf, re.DOTALL)
        assert bloc, provider
        assert set(re.findall(r"(\w+)\s*=", bloc.group(1))) == set(vms.DISTROS), provider


def test_le_nom_de_machine_suit_les_templates() -> None:
    assert vms.nom_de_machine("essai", "kvm") == "essai.lab"
    assert vms.nom_de_machine("essai", "incus") == "essai-lab"


# ── la CLI : ce qu'elle refuse, sans rien créer ───────────────────────────────

def test_create_refuse_un_nom_invalide_en_code_2_sans_rien_ecrire() -> None:
    res = runner.invoke(app, ["vm", "create", "Essai_VM"])
    assert res.exit_code == 2
    assert not vms.dossier_des_vm().exists()


def test_create_refuse_une_distribution_inconnue_en_code_2() -> None:
    res = runner.invoke(app, ["vm", "create", "essai", "--distro", "gentoo"])
    assert res.exit_code == 2
    assert not vms.dossier_des_vm().exists()


def test_create_refuse_un_nom_deja_pris_et_ne_touche_pas_a_la_vm() -> None:
    racine = vms.ecrire(vms.DemandeVM(nom="essai"), ipaddress.IPv4Network("10.10.100.0/24"))
    avant = (racine / "meta.yml").read_text(encoding="utf-8")
    res = runner.invoke(app, ["vm", "create", "essai", "--provider", "kvm"])
    assert res.exit_code == 1
    assert (racine / "meta.yml").read_text(encoding="utf-8") == avant


def test_create_refuse_un_nom_que_l_hyperviseur_porte_deja(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(vms, "machine_existe", lambda nom, provider: True)
    res = runner.invoke(app, ["vm", "create", "k8s-cp", "--provider", "kvm"])
    assert res.exit_code == 1
    assert not vms.dossier("k8s-cp").exists()


def test_ssh_sur_une_vm_inconnue_sort_en_1() -> None:
    res = runner.invoke(app, ["vm", "ssh", "absente"])
    assert res.exit_code == 1


def test_destroy_efface_les_fichiers_seulement_si_la_destruction_a_reussi(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path,
) -> None:
    import typer

    from dsoxlab.cli import destruction

    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "state"))
    monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path / "cache"))
    racine = vms.ecrire(vms.DemandeVM(nom="essai"), ipaddress.IPv4Network("10.10.100.0/24"))

    def echoue(*_a: object, **_k: object) -> None:
        raise typer.Exit(6)

    monkeypatch.setattr(destruction, "destroy", echoue)
    res = runner.invoke(app, ["vm", "destroy", "essai", "--yes"])
    assert res.exit_code == 6
    assert racine.is_dir(), "un échec doit laisser le dossier, seule poignée sur la VM"

    monkeypatch.setattr(destruction, "destroy", lambda *_a, **_k: None)
    res = runner.invoke(app, ["vm", "destroy", "essai", "--yes"])
    assert res.exit_code == 0
    assert not racine.exists()
