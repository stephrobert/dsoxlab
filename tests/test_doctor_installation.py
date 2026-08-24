"""Ce que `doctor` doit dire d'une machine qui n'est pas encore prête.

Ces cas viennent d'un audit joué sur une VM Ubuntu 24.04 neuve : entre un
`dsoxlab doctor` **vert** et le premier lab `vm` jouable, il fallait six
interventions que rien ne documentait. Le diagnostic passait à côté de chacune,
et l'apprenant les découvrait une par une, en langage Terraform ou en `rc=127`.

Chaque test ci-dessous épingle une de ces omissions.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from dsoxlab.i18n import _
from dsoxlab.models.lab import LabDefinition, ValidationConfig
from dsoxlab.models.repo import InfraDefinition, RepoMetadata
from dsoxlab.models.runtime import RuntimeConfig, RuntimeType, Target
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


def _repo(
    provider: str = "",
    candidates: list[str] | None = None,
    overrides: dict[str, dict[str, object]] | None = None,
) -> RepoMetadata:
    return RepoMetadata(
        id="demo",
        category="demo",
        infra=InfraDefinition(
            provider=provider,
            providers_available=candidates or [],
            providers=overrides or {},
        ),
    )


def _labs(monkeypatch: pytest.MonkeyPatch, labs: list[LabDefinition]) -> None:
    monkeypatch.setattr(doctor, "get_all_labs", lambda root: labs)


def _labels(checks: list[doctor.Check]) -> set[str]:
    return {c.label for c in checks}


@pytest.fixture
def hyperviseur_ok(monkeypatch: pytest.MonkeyPatch) -> None:
    """Les deux hyperviseurs installés et fonctionnels.

    Les sondes réelles lancent virsh et incus : plusieurs secondes, et un
    résultat qui dépend de la machine. Ce qu'on vérifie ici est le contenu du
    diagnostic, pas les sondes.
    """
    monkeypatch.setattr(
        doctor, "_hypervisor_checks",
        lambda: {
            "kvm": doctor._check("kvm", True, "libvirt 10.0.0"),
            "incus": doctor._check("incus", True, "daemon ok"),
        },
    )


@pytest.fixture
def outillage_present(monkeypatch: pytest.MonkeyPatch) -> None:
    """Terraform et ansible-playbook installés.

    Les tests qui portent sur autre chose ne doivent pas dépendre de la machine
    qui les exécute : ceux-ci passaient en local et tombaient sur un runner CI
    dépourvu de terraform.
    """
    monkeypatch.setattr(
        doctor, "_check_terraform",
        lambda: doctor._check("terraform", True, "Terraform v1.0.0"),
    )
    monkeypatch.setattr(
        doctor, "_check_ansible",
        lambda: doctor._check("ansible", True, "ok"),
    )


@pytest.fixture
def outillage_absent(monkeypatch: pytest.MonkeyPatch) -> None:
    """Ni terraform ni ansible-playbook, comme sur une machine neuve."""
    monkeypatch.setattr(doctor.shutil, "which", lambda name: None)
    monkeypatch.setattr(
        doctor.ansible_infra, "has_ansible_playbook", lambda: False
    )


# ── terraform et ansible, les deux absents du diagnostic ──────────────────────

def test_terraform_et_ansible_sont_requis_par_un_depot_a_labs_vm(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    hyperviseur_ok: None,
    outillage_absent: None,
) -> None:
    """Sans eux, `provision` et `run` échouent. Ils manquaient au diagnostic.

    Terraform n'était vérifié nulle part, et le contrôle d'ansible portait sur
    l'import de la bibliothèque : il était vert sur une machine où aucun
    playbook ne pouvait tourner.
    """
    _labs(monkeypatch, [_lab("a", RuntimeType.VM)])
    report = doctor.collect_checks(tmp_path, _repo(provider="kvm"))

    requis = _labels(report.required)
    assert _("check_terraform") in requis
    assert _("check_ansible") in requis

    echecs = _labels(report.failing())
    assert _("check_terraform") in echecs
    assert _("check_ansible") in echecs


def test_un_terraform_present_mais_en_erreur_ne_doit_pas_passer_pour_vert(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Le contrôle ne lisait pas le code retour de `terraform version`.

    Un binaire présent mais inutilisable (plugin cache corrompu, wrapper cassé,
    binaire d'une autre architecture) sortait en rc != 0 sans rien sur stdout.
    Le contrôle affichait alors « ok » et se déclarait vert, puis `provision`
    échouait sur une machine que `doctor` venait de dire prête.
    """
    monkeypatch.setattr(doctor.shutil, "which", lambda name: "/usr/bin/terraform")
    monkeypatch.setattr(
        doctor.subprocess, "run",
        lambda *a, **kw: subprocess.CompletedProcess(
            args=a[0] if a else [], returncode=1,
            stdout="", stderr="Error: Failed to load plugin schemas\n",
        ),
    )

    check = doctor._check_terraform()

    assert not check.ok, "un terraform qui sort en erreur n'est pas un terraform utilisable"
    assert "Failed to load plugin schemas" in check.detail


def test_un_terraform_qui_repond_correctement_reste_vert(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Le contre-cas, sans quoi le précédent passerait aussi sur un bug inverse."""
    monkeypatch.setattr(doctor.shutil, "which", lambda name: "/usr/bin/terraform")
    monkeypatch.setattr(
        doctor.subprocess, "run",
        lambda *a, **kw: subprocess.CompletedProcess(
            args=a[0] if a else [], returncode=0,
            stdout="Terraform v1.9.5\non linux_amd64\n", stderr="",
        ),
    )

    check = doctor._check_terraform()

    assert check.ok
    assert check.detail == "Terraform v1.9.5"


def test_un_depot_sans_lab_vm_n_exige_ni_terraform_ni_ansible(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    hyperviseur_ok: None,
    outillage_absent: None,
) -> None:
    """`terraform-training` est entièrement `shell` : rien de tout cela ne le
    concerne, et le lui montrer en rouge serait le décourager pour rien."""
    _labs(monkeypatch, [_lab("a", RuntimeType.SHELL)])
    report = doctor.collect_checks(tmp_path, _repo())

    requis = _labels(report.required)
    assert _("check_terraform") not in requis
    assert _("check_ansible") not in requis


def test_ansible_est_reparable_automatiquement(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    hyperviseur_ok: None,
    outillage_absent: None,
) -> None:
    """`uv tool install ansible-core` est sûr et sans ambiguïté : --fix le joue.

    Terraform, lui, ne porte qu'un `hint` : son installation passe par un dépôt
    tiers, ce n'est pas à l'outil de la décider.
    """
    _labs(monkeypatch, [_lab("a", RuntimeType.VM)])
    report = doctor.collect_checks(tmp_path, _repo(provider="kvm"))

    par_label = {c.label: c for c in report.required}
    correctif = par_label[_("check_ansible")].fix
    assert correctif is not None
    assert correctif.display == "uv tool install ansible-core"
    assert correctif.kind is doctor.FixKind.AUTOMATIC
    assert par_label[_("check_terraform")].fix is None
    assert "terraform" in (par_label[_("check_terraform")].hint or "")


# ── les contrôles de configuration ne parlent qu'après l'installation ─────────

def test_les_controles_kvm_se_taisent_si_virsh_manque(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Trois lignes rouges pour une seule cause noient celle qui compte.

    Le contrôle du pool porte sur la CONFIGURATION d'un libvirt déjà installé :
    l'afficher quand libvirt lui-même manque n'apprend rien.
    """
    monkeypatch.setattr(
        doctor, "_hypervisor_checks",
        lambda: {
            "kvm": doctor._check("kvm", False, "not found", fix="apt install"),
            "incus": doctor._check("incus", True, "ok"),
        },
    )
    _labs(monkeypatch, [_lab("a", RuntimeType.VM)])
    report = doctor.collect_checks(tmp_path, _repo(provider="kvm"))

    requis = _labels(report.required)
    assert _("check_kvm") in requis
    assert _("check_libvirt_pool") not in requis


def test_les_controles_kvm_apparaissent_une_fois_virsh_present(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, hyperviseur_ok: None
) -> None:
    _labs(monkeypatch, [_lab("a", RuntimeType.VM)])
    report = doctor.collect_checks(tmp_path, _repo(provider="kvm"))

    requis = _labels(report.required)
    assert _("check_libvirt_pool") in requis
    # genisoimage ne concerne qu'incus : sur kvm, ce serait du bruit.
    assert _("check_iso_tool") not in requis


def test_genisoimage_est_exige_sur_incus_seulement(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, hyperviseur_ok: None
) -> None:
    """Incus fabrique le CD-ROM `agent:config` sur l'hôte : sans outil ISO,
    aucune instance de type virtual-machine ne démarre."""
    _labs(monkeypatch, [_lab("a", RuntimeType.VM)])
    report = doctor.collect_checks(tmp_path, _repo(provider="incus"))

    assert _("check_iso_tool") in _labels(report.required)
    assert _("check_libvirt_pool") not in _labels(report.required)


# ── le pool visé est celui du dépôt, pas un nom présumé ───────────────────────

def test_le_pool_verifie_est_celui_que_le_depot_declare(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, hyperviseur_ok: None
) -> None:
    """Un dépôt peut viser son propre pool via infra.providers.kvm.storage_pool.

    Vérifier « default » en dur afficherait alors du rouge sur un pool
    parfaitement configuré.
    """
    vus: list[str] = []

    def _faux_check(pool: str) -> doctor.Check:
        vus.append(pool)
        return doctor._check("libvirt_pool", True, pool)

    monkeypatch.setattr(doctor, "_check_libvirt_pool", _faux_check)
    _labs(monkeypatch, [_lab("a", RuntimeType.VM)])
    doctor.collect_checks(
        tmp_path,
        _repo(provider="kvm", overrides={"kvm": {"storage_pool": "labs-pool"}}),
    )

    assert vus == ["labs-pool"]


def test_sans_declaration_le_pool_verifie_est_default(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, hyperviseur_ok: None
) -> None:
    vus: list[str] = []
    monkeypatch.setattr(
        doctor, "_check_libvirt_pool",
        lambda pool: (vus.append(pool), doctor._check("p", True, pool))[1],
    )
    _labs(monkeypatch, [_lab("a", RuntimeType.VM)])
    doctor.collect_checks(tmp_path, _repo(provider="kvm"))

    assert vus == ["default"]


# ── le tableau informatif cesse de mentir ─────────────────────────────────────

def test_sans_provider_choisi_le_tableau_ne_dit_plus_non_requis(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    hyperviseur_ok: None,
    outillage_present: None,
) -> None:
    """Le tableau s'intitulait « non requis ici » et affirmait « ces composants
    ne bloquent rien », au-dessus des deux hyperviseurs dont l'un est
    indispensable pour jouer 64 labs sur 84.

    Les checks restent hors du requis, sans quoi `--fix` proposerait
    d'installer kvm ET incus pour un choix qui n'est pas fait : c'est le
    libellé qui devait changer.
    """
    _labs(monkeypatch, [_lab("a", RuntimeType.VM)])
    report = doctor.collect_checks(tmp_path, _repo(candidates=["kvm", "incus"]))

    assert report.optional_title_key == "doctor_choose_title"
    assert report.optional_hint_key == "doctor_choose_hint"
    reparables = {c.label for c in report.fixable()}
    assert _("check_kvm") not in reparables
    assert _("check_incus") not in reparables, (
        "--fix ne doit pas installer un hyperviseur pour un choix non fait"
    )


def test_un_depot_sans_lab_vm_garde_le_tableau_informatif(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, hyperviseur_ok: None
) -> None:
    """Là, « non requis ici » est vrai, et doit le rester."""
    _labs(monkeypatch, [_lab("a", RuntimeType.SHELL)])
    report = doctor.collect_checks(tmp_path, _repo())

    assert report.optional_title_key == "doctor_optional_title"
    assert report.optional_hint_key == "doctor_optional_hint"


@pytest.mark.parametrize(
    "cle",
    ["doctor_choose_title", "doctor_choose_hint"],
)
def test_les_nouvelles_cles_existent_dans_les_deux_langues(cle: str) -> None:
    """Une clé qui n'existe que d'un côté n'existe pas."""
    from dsoxlab.i18n.strings.en import STRINGS as EN
    from dsoxlab.i18n.strings.fr import STRINGS as FR

    assert cle in EN and cle in FR
    assert EN[cle] != FR[cle], "une traduction identique est probablement oubliée"


# ── ce qu'on ne peut pas affirmer d'avance, on le dit à l'échec ───────────────

@pytest.mark.parametrize(
    ("erreur", "attendu"),
    [
        (
            "Error: Pool Not Found\nStorage pool 'default' not found",
            "explain_pool_not_found",
        ),
        (
            (
                "operation failed: domain 'alma-rhcsa-2.lab' already exists with "
                "uuid 95409cf2-d226-44c8-b8ee-16b5bd614ce6"
            ),
            "explain_domain_exists",
        ),
    ],
)
def test_les_erreurs_terraform_connues_sont_traduites(
    erreur: str, attendu: str
) -> None:
    """Terraform est exact et opaque. Quand la cause est connue et le correctif
    tient en une ligne, on les donne au lieu de laisser chercher."""
    resultat = doctor.explique_echec_provision(erreur)

    assert resultat is not None, f"« {erreur[:40]}… » doit être reconnu"
    explication, commande = resultat
    assert explication == _(attendu)
    assert commande, "une explication sans commande n'aide qu'à moitié"


def test_l_apparmor_n_est_propose_que_si_l_override_manque(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Sinon ce serait une fausse piste : mesuré sur une machine où l'override
    est absent et où huit domaines tournent pourtant sans incident, donc son
    absence ne prouve rien à elle seule. On ne l'avance qu'une fois le
    « Permission denied » réellement survenu."""
    erreur = "Could not open '/var/lib/libvirt/images/x.qcow2': Permission denied"

    monkeypatch.setattr(doctor, "apparmor_override_absent", lambda: True)
    resultat = doctor.explique_echec_provision(erreur)
    assert resultat is not None
    assert resultat[0] == _("explain_apparmor_denied")
    assert " rwk," in resultat[1], "le droit k est indispensable, pas r seul"

    monkeypatch.setattr(doctor, "apparmor_override_absent", lambda: False)
    assert doctor.explique_echec_provision(erreur) is None


def test_une_erreur_inconnue_ne_produit_aucune_explication() -> None:
    """On ne devine pas : une explication inventée coûte plus qu'aucune."""
    assert doctor.explique_echec_provision("boom") is None
    assert doctor.explique_echec_provision("") is None


# ── absent et inactif sont deux états, pas un seul ───────────────────────────

def _virsh_pools(actifs: list[str], definis: list[str]):
    """Simule `virsh pool-list [--all] --name`.

    La sonde réelle est jouée : c'est bien elle qui oubliait le `--all`, donc
    la remplacer par un faux `_pools_libvirt` ne prouverait rien. On ne
    contrefait que virsh, au niveau du sous-processus.
    """

    def _run(cmd, *args, **kwargs):  # type: ignore[no-untyped-def]
        noms = definis if "--all" in cmd else actifs
        return subprocess.CompletedProcess(
            args=cmd, returncode=0, stdout="\n".join(noms) + "\n", stderr="",
        )

    return _run


def test_un_pool_actif_est_vert(monkeypatch: pytest.MonkeyPatch) -> None:
    """Le contre-cas, sans lequel les deux suivants passeraient sur un bug
    qui rendrait tout pool rouge."""
    monkeypatch.setattr(
        doctor.subprocess, "run", _virsh_pools(["default"], ["default"])
    )
    check = doctor._check_libvirt_pool("default")

    assert check.ok
    assert check.detail == "default"
    assert check.fix is None


def test_un_pool_absent_fait_proposer_sa_creation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Une Ubuntu fraîche n'en déclare aucun. Les quatre étapes comptent :
    `pool-define-as` seul laisse un pool inactif, où rien ne s'écrit."""
    monkeypatch.setattr(doctor.subprocess, "run", _virsh_pools([], []))
    check = doctor._check_libvirt_pool("default")

    assert not check.ok
    assert check.detail == _("detail_pool_missing", pool="default")
    assert check.fix is not None
    for etape in ("pool-define-as", "pool-build", "pool-start", "pool-autostart"):
        assert etape in check.fix.display, (
            f"« {etape} » manque à la création du pool"
        )


def test_un_pool_defini_mais_arrete_est_dit_tel_quel(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Le défaut que ce lot corrige.

    `virsh pool-list --name` ne liste que les pools **actifs**. Un pool défini
    mais jamais démarré n'y figurait pas, le contrôle le déclarait introuvable,
    et proposait un `pool-define-as` qui échoue aussitôt sur « pool already
    exists ». Terraform, lui, sort sur un tout autre message (« storage pool
    'x' is not active ») et le geste qui débloque est `pool-start`.
    """
    monkeypatch.setattr(
        doctor.subprocess, "run", _virsh_pools([], ["default"])
    )
    check = doctor._check_libvirt_pool("default")

    assert not check.ok
    assert check.detail == _("detail_pool_inactive", pool="default")
    assert check.fix is not None
    assert "pool-start" in check.fix.display
    assert "pool-autostart" in check.fix.display
    assert "pool-define-as" not in check.fix.display, (
        "définir un pool qui existe déjà échoue : la remédiation mentirait"
    )


def test_le_pool_du_depot_est_celui_qui_est_sonde(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Un dépôt qui vise son propre pool ne doit pas se voir répondre sur
    « default », ni dans le constat ni dans la remédiation."""
    monkeypatch.setattr(
        doctor.subprocess, "run", _virsh_pools(["default"], ["default"])
    )
    check = doctor._check_libvirt_pool("labs-pool")

    assert not check.ok
    assert "labs-pool" in check.detail
    assert check.fix is not None
    assert "labs-pool" in check.fix.display
    assert "default" not in check.fix.display


def test_un_virsh_muet_ne_conclut_pas_a_l_absence(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Sonder n'est pas deviner : un virsh injoignable ne prouve pas qu'un pool
    manque, et le rouge appartient alors au contrôle KVM, pas à celui-ci."""

    def _run(cmd, *args, **kwargs):  # type: ignore[no-untyped-def]
        raise OSError("virsh a disparu entre deux appels")

    monkeypatch.setattr(doctor.subprocess, "run", _run)
    check = doctor._check_libvirt_pool("default")

    assert check.ok
    assert check.detail == _("detail_pool_unknown")


# ── la remédiation nomme le pool que Terraform a nommé ────────────────────────

def test_le_pool_absent_est_lu_dans_le_message(monkeypatch: pytest.MonkeyPatch) -> None:
    """Message réel de terraform-provider-libvirt 0.9.8, relevé sur la machine.

    La remédiation codait « default » en dur : un dépôt qui vise son pool via
    `infra.providers.kvm.storage_pool` se voyait proposer la création d'un pool
    que personne n'utilise, et restait bloqué.
    """
    erreur = (
        "Error: Pool Not Found\n\nStorage pool 'labs-pool' not found: Storage "
        "pool not found: no storage pool with matching name 'labs-pool'"
    )
    resultat = doctor.explique_echec_provision(erreur)

    assert resultat is not None
    explication, commande = resultat
    assert explication == _("explain_pool_not_found")
    assert "labs-pool" in commande
    assert "default" not in commande


def test_un_pool_inactif_est_reconnu_a_l_echec() -> None:
    """Autre message réel, mesuré en appliquant sur un pool défini non démarré.

    Il ne dit pas la même chose que « Pool Not Found » et n'appelle pas le même
    geste : le confondre avec l'absence renverrait vers une création qui échoue.
    """
    erreur = (
        "Error: Volume Creation Failed\n\nFailed to create storage volume: "
        "Requested operation is not valid: storage pool 'labs-pool' is not active"
    )
    resultat = doctor.explique_echec_provision(erreur)

    assert resultat is not None
    explication, commande = resultat
    assert explication == _("explain_pool_inactive")
    assert "pool-start labs-pool" in commande
    assert "pool-define-as" not in commande


@pytest.mark.parametrize(
    "cle",
    ["detail_pool_inactive", "explain_pool_inactive"],
)
def test_les_cles_du_pool_inactif_sont_bilingues(cle: str) -> None:
    """Une clé qui n'existe que d'un côté n'existe pas."""
    from dsoxlab.i18n.strings.en import STRINGS as EN
    from dsoxlab.i18n.strings.fr import STRINGS as FR

    assert cle in EN and cle in FR
    assert EN[cle] != FR[cle], "une traduction identique est probablement oubliée"


# ── une sonde muette ne doit pas emporter le diagnostic ──────────────────────

def test_une_sonde_qui_pend_ne_leve_pas(monkeypatch: pytest.MonkeyPatch) -> None:
    """`virsh version` peut pendre : le contrôle le rapporte, il ne plante pas.

    Mesuré en environnement contraint, où la socket libvirt ne répond jamais :
    la `TimeoutExpired` remontait jusqu'au bout et emportait toute la commande.
    Depuis que `doctor --json` est une interface, elle emporte aussi le document
    que l'appelant attendait, et lui rend une trace Python à la place.
    """
    import subprocess

    monkeypatch.setattr(doctor.shutil, "which", lambda _nom: "/usr/bin/virsh")

    def _pend(*_a: object, **_k: object) -> object:
        raise subprocess.TimeoutExpired(cmd=["virsh", "version"], timeout=5)

    monkeypatch.setattr(doctor.subprocess, "run", _pend)

    controle = doctor._check_kvm()

    assert controle.key == "kvm"
    assert not controle.ok
    assert controle.fix, "un échec doit nommer le geste qui le corrige"
