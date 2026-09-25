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

import subprocess
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
    # Sans simulation, le détail dépendrait de la machine qui joue le test —
    # un runner de CI est lui-même une VM, un poste de développement souvent pas.
    monkeypatch.setattr(
        doctor, "_hebergement", lambda: doctor.Hebergement(dans_une_vm=None),
    )
    check = doctor._check_hw_virt()

    assert check.key == "hw_virt"
    assert check.state == doctor.STATE_FAILED
    # Le geste (BIOS, virtualisation imbriquée) appartient à l'humain, machine
    # éteinte : aucun correctif exécutable ne doit être proposé.
    assert check.fix is None


def test_dans_une_vm_le_message_nomme_l_imbrication(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Le cas de toute image prête à l'emploi (issue #91).

    Parler du BIOS à qui tourne dans une VM l'envoie chercher un réglage qui
    n'existe pas chez lui : la machine virtuelle n'a pas de BIOS à visiter, et
    l'imbrication s'active sur l'hôte, à l'extérieur.
    """
    monkeypatch.setattr(doctor, "_KVM_DEVICE", tmp_path / "absent")
    monkeypatch.setattr(
        doctor, "_hebergement",
        lambda: doctor.Hebergement(dans_une_vm=True, hyperviseur="vmware"),
    )

    check = doctor._check_hw_virt()

    assert check.state == doctor.STATE_FAILED
    bas = check.detail.lower()
    assert "vmware" in bas          # l'hyperviseur est nommé, pas deviné
    assert "imbriquée" in bas or "nested" in bas
    assert "bios" not in bas        # la fausse piste a disparu


def test_sur_du_metal_nu_le_message_envoie_au_bios(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Le symétrique : sur une machine physique, l'imbrication n'a aucun sens."""
    monkeypatch.setattr(doctor, "_KVM_DEVICE", tmp_path / "absent")
    monkeypatch.setattr(
        doctor, "_hebergement", lambda: doctor.Hebergement(dans_une_vm=False),
    )

    check = doctor._check_hw_virt()

    bas = check.detail.lower()
    assert "bios" in bas
    assert "imbriquée" not in bas and "nested" not in bas


def test_un_hebergement_indetermine_garde_le_ou(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Ne pas savoir n'autorise pas à choisir : les deux consignes restent.

    C'est la même règle que pour `unknown` sur un verdict — on n'affirme pas ce
    qu'on n'a pas mesuré. Ici elle porte sur la consigne, pas sur l'état.
    """
    monkeypatch.setattr(doctor, "_KVM_DEVICE", tmp_path / "absent")
    monkeypatch.setattr(
        doctor, "_hebergement", lambda: doctor.Hebergement(dans_une_vm=None),
    )

    check = doctor._check_hw_virt()

    bas = check.detail.lower()
    assert "bios" in bas
    assert "imbriquée" in bas or "nested" in bas


# ── où tourne ce système : la sonde qui décide du message ─────────────────────

def _completed(sortie: str, code: int) -> subprocess.CompletedProcess[str]:
    return subprocess.CompletedProcess(args=[], returncode=code, stdout=sortie,
                                       stderr="")


def test_systemd_detect_virt_nomme_l_hyperviseur(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Nommer vaut mieux qu'un booléen : la consigne diffère par produit."""
    monkeypatch.setattr(
        doctor, "_sonder", lambda *a, **k: _completed("vmware\n", 0),
    )

    hote = doctor._hebergement()

    assert hote.dans_une_vm is True
    assert hote.hyperviseur == "vmware"


def test_le_metal_nu_se_lit_dans_le_code_retour(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """`systemd-detect-virt --vm` sort en 1 avec « none » : c'est une mesure.

    La traiter comme un échec de sonde ferait retomber sur le repli, et surtout
    conclurait « je ne sais pas » là où la réponse est claire.
    """
    monkeypatch.setattr(
        doctor, "_sonder", lambda *a, **k: _completed("none\n", 1),
    )

    assert doctor._hebergement().dans_une_vm is False


def test_le_repli_lit_le_drapeau_hypervisor(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`systemd-detect-virt` n'est pas universel : une image minimale s'en passe."""
    cpuinfo = tmp_path / "cpuinfo"
    cpuinfo.write_text("processor\t: 0\nflags\t\t: fpu vme hypervisor lm\n")
    monkeypatch.setattr(doctor, "_sonder", lambda *a, **k: None)
    monkeypatch.setattr(doctor, "_CPUINFO", cpuinfo)

    hote = doctor._hebergement()

    assert hote.dans_une_vm is True
    # Le repli tranche la question, mais ne nomme personne : ne pas inventer.
    assert hote.hyperviseur == ""


def test_un_cpuinfo_sans_drapeau_vaut_metal_nu(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    cpuinfo = tmp_path / "cpuinfo"
    cpuinfo.write_text("processor\t: 0\nflags\t\t: fpu vme de pse tsc\n")
    monkeypatch.setattr(doctor, "_sonder", lambda *a, **k: None)
    monkeypatch.setattr(doctor, "_CPUINFO", cpuinfo)

    assert doctor._hebergement().dans_une_vm is False


def test_un_cpuinfo_illisible_ne_conclut_rien(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Les deux sondes muettes : l'ignorance est un état, pas un défaut à cacher."""
    monkeypatch.setattr(doctor, "_sonder", lambda *a, **k: None)
    monkeypatch.setattr(doctor, "_CPUINFO", tmp_path / "jamais-ecrit")

    assert doctor._hebergement().dans_une_vm is None


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


def test_un_pool_plus_petit_que_le_nominal_ne_peint_plus_en_rouge(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Le comportement change délibérément (issue #209).

    Ce test exigeait l'inverse : un pool plus petit que la somme des tailles
    déclarées faisait échouer le contrôle. Or ces tailles sont NOMINALES et les
    qcow2 s'allouent à la demande — le catalogue Linux annonce 65 Go pour 3,2 Go
    réellement occupés, mesurés par un utilisateur dont `doctor` était rouge en
    contrôle **requis** sur une installation qui provisionnait très bien.

    Comparer un maximum théorique à une mesure ne prouve rien. Le chiffre reste
    affiché, annoncé comme un maximum, et un manque d'espace RÉEL se dit au
    moment où il se produit, par `explique_echec_provision`.
    """
    monkeypatch.setattr(doctor, "_mem_available_mb", lambda: 8192)
    monkeypatch.setattr(doctor, "_pool_available_gb", lambda pool: 8)

    check = doctor._check_resources(_infra(), "kvm")

    assert check.state == doctor.STATE_OK
    # Les deux chiffres restent lisibles : le pire cas dit quelque chose de vrai.
    assert "8" in check.detail
    assert "25" in check.detail


def test_une_ram_insuffisante_echoue_meme_avec_un_pool_etroit(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """La régression à craindre : tout rendre informatif et ne plus rien juger.

    La RAM, elle, se compare : `MemAvailable` et la somme des `ram_mb` sont deux
    mesures de même nature.
    """
    monkeypatch.setattr(doctor, "_mem_available_mb", lambda: 512)
    monkeypatch.setattr(doctor, "_pool_available_gb", lambda pool: 8)

    check = doctor._check_resources(_infra(), "kvm")

    assert check.state == doctor.STATE_FAILED


def test_un_pool_plein_est_explique_au_moment_de_l_echec() -> None:
    """Le pendant du contrôle assoupli : sans lui, on retirerait un garde-fou.

    libvirt rend « no space left on device » sans nommer le pool ni le geste.
    """
    connu = doctor.explique_echec_provision(
        "Error: error creating volume: no space left on device"
    )

    assert connu is not None
    explication, commande = connu
    assert "pool" in explication.lower()
    assert "pool-info" in commande


def test_un_pool_plein_nomme_le_pool_du_depot() -> None:
    """Une commande proposée qui vise le mauvais pool échoue à la copie.

    libvirt ne nomme pas le pool dans « no space left on device » : c'est
    l'appelant qui le sait, par `nom_du_pool`, et qui le transmet.
    """
    connu = doctor.explique_echec_provision(
        "Error: error creating volume: no space left on device",
        pool="labs-ssd",
    )

    assert connu is not None
    assert "labs-ssd" in connu[1]


def test_le_pool_du_depot_vient_des_overrides() -> None:
    """`storage_pool` du `meta.yml` prime, `default` n'est que le repli."""
    assert doctor.nom_du_pool(_infra()) == "default"

    infra = _infra()
    infra.providers = {"kvm": {"storage_pool": "labs-ssd"}}
    assert doctor.nom_du_pool(infra) == "labs-ssd"


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
