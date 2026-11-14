"""Les hôtes optionnels d'un catalogue (0.9.0, issue #365).

Un hôte de ``infra.optional_hosts`` n'est monté que pour les labs qui le
citent. Ces tests défendent les quatre promesses qui en découlent :

1. un ``provision`` du catalogue ne le monte pas, et ne détruit pas celui qu'un
   lab a monté ;
2. son adresse, et celle des autres, ne bougent pas selon qui est monté ;
3. ``destroy --optional-hosts`` ne retire que lui ;
4. le socle du catalogue lui est joué, même à empreinte inchangée.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from typer.testing import CliRunner

from dsoxlab.cli import app, destruction, parcours
from dsoxlab.infra import inventory, terraform
from dsoxlab.models.repo import RepoMetadata
from dsoxlab.services import bootstrap
from dsoxlab.services.doctor import _hotes_a_compter
from dsoxlab.validators.contract import validate_repo_fields

runner = CliRunner()

META = """\
repo:
  id: ha
  category: demo
infra:
  provider: kvm
  network: lab-ha
  cidr: 10.10.60.0/24
  hosts:
    - name: cp.lab
      ram_mb: 2048
    - name: w1.lab
      ram_mb: 1024
  optional_hosts:
    - name: cp2.lab
      ram_mb: 2560
    - name: lb.lab
      ram_mb: 512
"""


@pytest.fixture
def depot(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "state"))
    monkeypatch.setenv("DSOXLAB_NO_UPDATE_CHECK", "1")
    monkeypatch.setenv("DSOXLAB_LANG", "en")
    monkeypatch.delenv("DSOXLAB_PROVIDER", raising=False)
    repo = tmp_path / "repo"
    (repo / "ssh").mkdir(parents=True)
    (repo / "ssh" / "id_ed25519").write_text("clé factice", encoding="utf-8")
    (repo / "meta.yml").write_text(META, encoding="utf-8")
    return repo


def _meta(depot: Path) -> RepoMetadata:
    return RepoMetadata.from_yaml(depot / "meta.yml")


def _poser_le_state(tmp_path: Path, hotes: list[str], *, contenu: str | None = None) -> None:
    """Un state Terraform qui porte ces machines, comme le template kvm l'écrit."""
    dossier = tmp_path / "state" / "dsoxlab" / "ha" / "terraform" / "kvm"
    dossier.mkdir(parents=True, exist_ok=True)
    if contenu is None:
        contenu = json.dumps({"resources": [
            {"mode": "managed", "type": "libvirt_domain", "name": "host",
             "instances": [{"index_key": h, "attributes": {"name": h}} for h in hotes]},
            # Une autre ressource indexée par le même nom ne compte pas.
            {"mode": "managed", "type": "libvirt_volume", "name": "extra",
             "instances": [{"index_key": "lb.lab"}]},
        ]})
    (dossier / "terraform.tfstate").write_text(contenu, encoding="utf-8")


def _noms(actifs: list[tuple[int, Any]]) -> list[tuple[int, str]]:
    return [(index, h.name) for index, h in actifs]


# ── Le modèle ──────────────────────────────────────────────────────────────


def test_les_hotes_optionnels_suivent_les_communs(depot: Path) -> None:
    infra = _meta(depot).infra
    assert [h.name for h in infra.hosts] == ["cp.lab", "w1.lab", "cp2.lab", "lb.lab"]
    assert [h.name for h in infra.common_hosts] == ["cp.lab", "w1.lab"]
    assert [h.name for h in infra.optional_hosts] == ["cp2.lab", "lb.lab"]
    assert infra.host("lb.lab") is not None and infra.host("lb.lab").ram_mb == 512


def test_un_catalogue_sans_hote_optionnel_est_inchange(tmp_path: Path) -> None:
    (tmp_path / "meta.yml").write_text(
        "repo:\n  id: x\ninfra:\n  hosts:\n    - name: a.lab\n", encoding="utf-8"
    )
    infra = RepoMetadata.from_yaml(tmp_path / "meta.yml").infra
    assert infra.optional_hosts == [] and [h.name for h in infra.common_hosts] == ["a.lab"]


# ── Ce que Terraform reçoit ────────────────────────────────────────────────


def test_sans_state_terraform_ne_connait_que_les_communs(depot: Path) -> None:
    assert _noms(terraform.hotes_actifs(_meta(depot))) == [(0, "cp.lab"), (1, "w1.lab")]


def test_un_hote_demande_garde_l_index_de_sa_position_complete(depot: Path) -> None:
    """lb.lab est le 4e hôte déclaré : index 3, même sans cp2.lab devant lui."""
    actifs = terraform.hotes_actifs(_meta(depot), demandes=["lb.lab"])
    assert _noms(actifs) == [(0, "cp.lab"), (1, "w1.lab"), (3, "lb.lab")]


def test_un_hote_deja_monte_n_est_pas_detruit_par_un_provision(
    depot: Path, tmp_path: Path
) -> None:
    _poser_le_state(tmp_path, ["cp.lab", "w1.lab", "cp2.lab"])
    assert _noms(terraform.hotes_actifs(_meta(depot))) == [
        (0, "cp.lab"), (1, "w1.lab"), (2, "cp2.lab"),
    ]


def test_un_hote_retire_sort_de_var_hosts(depot: Path, tmp_path: Path) -> None:
    _poser_le_state(tmp_path, ["cp.lab", "w1.lab", "cp2.lab", "lb.lab"])
    actifs = terraform.hotes_actifs(_meta(depot), retires=["cp2.lab", "lb.lab"])
    assert _noms(actifs) == [(0, "cp.lab"), (1, "w1.lab")]


def test_un_hote_commun_ne_se_retire_jamais(depot: Path) -> None:
    actifs = terraform.hotes_actifs(_meta(depot), retires=["cp.lab"])
    assert ("cp.lab") in [h.name for _, h in actifs]


def test_un_state_illisible_retient_tous_les_optionnels(depot: Path, tmp_path: Path) -> None:
    """Au pire on crée une machine de trop ; les écarter en détruirait."""
    _poser_le_state(tmp_path, [], contenu="{ tronqué")
    assert terraform.hotes_au_state(_meta(depot)) is None
    assert [h.name for _, h in terraform.hotes_actifs(_meta(depot))] == [
        "cp.lab", "w1.lab", "cp2.lab", "lb.lab",
    ]


def test_le_state_se_lit_par_la_cle_du_for_each(depot: Path, tmp_path: Path) -> None:
    """Incus nomme ses instances sans points : la clé reste le FQDN."""
    contenu = json.dumps({"resources": [
        {"mode": "managed", "type": "incus_instance", "name": "host",
         "instances": [{"index_key": "cp2.lab", "attributes": {"name": "cp2-lab"}}]},
        {"mode": "data", "type": "libvirt_domain", "name": "host",
         "instances": [{"index_key": "lb.lab"}]},
    ]})
    _poser_le_state(tmp_path, [], contenu=contenu)
    assert terraform.hotes_au_state(_meta(depot)) == {"cp2.lab"}


def test_les_tfvars_portent_l_index_et_ecartent_les_optionnels_absents(
    depot: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(terraform.libvirt, "efi_loader", lambda: "/OVMF.fd")
    chemin = terraform.write_tfvars(_meta(depot), demandes=["lb.lab"])
    hotes = json.loads(chemin.read_text(encoding="utf-8"))["hosts"]
    assert [(h["name"], h["index"]) for h in hotes] == [
        ("cp.lab", 0), ("w1.lab", 1), ("lb.lab", 3),
    ]


def test_les_trois_templates_derivent_l_adresse_de_l_index() -> None:
    """Le rang dans var.hosts ne doit plus servir : il bouge avec les absents."""
    racine = Path(terraform.__file__).resolve().parent.parent / "templates" / "terraform"
    for provider in ("kvm", "incus", "outscale"):
        main = (racine / provider / "main.tf").read_text(encoding="utf-8")
        variables = (racine / provider / "variables.tf").read_text(encoding="utf-8")
        assert "for idx, h in var.hosts" not in main, provider
        assert "h.index" in main, provider
        assert "index = number" in variables, provider


# ── La mémoire comptée ─────────────────────────────────────────────────────


def test_doctor_seul_ne_compte_pas_les_optionnels(depot: Path) -> None:
    infra = _meta(depot).infra
    assert [h.name for h in _hotes_a_compter(infra, None)] == ["cp.lab", "w1.lab"]
    assert [h.name for h in _hotes_a_compter(infra, ["cp.lab", "lb.lab"])] == [
        "cp.lab", "lb.lab",
    ]
    assert [h.name for h in _hotes_a_compter(infra, ["inconnu.lab"])] == ["cp.lab", "w1.lab"]


# ── L'inventaire ───────────────────────────────────────────────────────────


def test_un_optionnel_absent_n_entre_pas_dans_l_inventaire_et_ne_crie_pas(
    depot: Path, caplog: pytest.LogCaptureFixture
) -> None:
    sorties = {"hosts": {"value": {"cp.lab": "10.10.60.11", "w1.lab": "10.10.60.12"}}}
    with caplog.at_level("WARNING"):
        inv = inventory.build_inventory(_meta(depot), terraform_outputs=sorties)
    hotes = inv["all"]["children"]["labenv"]["hosts"]
    assert sorted(hotes) == ["cp.lab", "w1.lab"]
    assert "cp2.lab" not in caplog.text and "lb.lab" not in caplog.text


def test_un_commun_absent_crie_toujours(
    depot: Path, caplog: pytest.LogCaptureFixture
) -> None:
    sorties = {"hosts": {"value": {"cp.lab": "10.10.60.11"}}}
    with caplog.at_level("WARNING"):
        inventory.build_inventory(_meta(depot), terraform_outputs=sorties)
    assert "w1.lab" in caplog.text


# ── Le socle ───────────────────────────────────────────────────────────────


def test_le_socle_se_rejoue_pour_un_hote_qui_ne_l_a_pas_recu(depot: Path) -> None:
    (depot / "socle.yaml").write_text("- hosts: all\n  tasks: []\n", encoding="utf-8")
    texte = (depot / "meta.yml").read_text(encoding="utf-8")
    (depot / "meta.yml").write_text(
        texte.replace("  network: lab-ha\n", "  network: lab-ha\n  bootstrap: socle.yaml\n"),
        encoding="utf-8",
    )
    meta = _meta(depot)
    travail = bootstrap.a_jouer(meta, hosts=["cp.lab", "w1.lab"])
    assert travail is not None
    bootstrap.enregistrer(meta, travail[1], ["cp.lab", "w1.lab"])

    assert bootstrap.a_jouer(meta, hosts=["cp.lab", "w1.lab"]) is None
    assert bootstrap.a_jouer(meta, hosts=["cp.lab", "lb.lab"]) is not None

    # Un provision --host ne fait pas oublier ceux qui l'avaient déjà reçu.
    bootstrap.enregistrer(meta, travail[1], ["lb.lab"])
    assert bootstrap.hotes_enregistres(meta) == {"cp.lab", "w1.lab", "lb.lab"}

    # Détruit, puis recréé : il doit le recevoir à nouveau.
    bootstrap.oublier_hotes(meta, ["lb.lab"])
    assert bootstrap.hotes_enregistres(meta) == {"cp.lab", "w1.lab"}
    assert bootstrap.a_jouer(meta, hosts=["lb.lab"]) is not None


# ── Le validateur ──────────────────────────────────────────────────────────


def test_un_nom_declare_deux_fois_est_signale(depot: Path) -> None:
    texte = (depot / "meta.yml").read_text(encoding="utf-8")
    (depot / "meta.yml").write_text(
        texte + "    - name: w1.lab\n", encoding="utf-8"
    )
    cles = [(i.key, i.params) for i in validate_repo_fields(depot).issues]
    assert ("hote_en_double", {"name": "w1.lab"}) in cles


def test_la_cle_optional_hosts_n_est_pas_hors_contrat(depot: Path) -> None:
    from dsoxlab.validators.contract import KNOWN_META_KEYS

    assert "infra.optional_hosts" in KNOWN_META_KEYS
    assert "infra.optional_hosts[].ram_mb" in KNOWN_META_KEYS


# ── destroy --optional-hosts ───────────────────────────────────────────────


@pytest.fixture
def retrait(monkeypatch: pytest.MonkeyPatch) -> list[list[str]]:
    """Terraform simulé : on note ce que le retrait aurait reçu."""
    appels: list[list[str]] = []
    monkeypatch.setattr(terraform, "is_available", lambda: True)
    monkeypatch.setattr(terraform, "init", lambda *a, **k: None)
    monkeypatch.setattr(
        terraform, "retirer_hotes_optionnels",
        lambda meta, noms, **k: appels.append(list(noms)),
    )
    monkeypatch.setattr(destruction, "_handle_orphans_after_destroy", lambda *a, **k: True)
    monkeypatch.setattr(destruction, "_purge_snapshots_before_destroy", lambda *a, **k: None)
    from dsoxlab.cli import infrastructure

    monkeypatch.setattr(infrastructure, "_ecrire_le_fragment_ssh", lambda meta: None)
    return appels


def test_destroy_optional_hosts_ne_vise_que_les_optionnels_montes(
    depot: Path, tmp_path: Path, retrait: list[list[str]]
) -> None:
    _poser_le_state(tmp_path, ["cp.lab", "w1.lab", "lb.lab"])
    resultat = runner.invoke(
        app, ["destroy", "--optional-hosts", "--yes", "--lab-home", str(depot)]
    )
    assert resultat.exit_code == 0, resultat.stdout
    assert retrait == [["lb.lab"]]


def test_destroy_optional_hosts_sans_rien_de_monte_ne_lance_rien(
    depot: Path, retrait: list[list[str]]
) -> None:
    resultat = runner.invoke(
        app, ["destroy", "--optional-hosts", "--yes", "--lab-home", str(depot)]
    )
    assert resultat.exit_code == 0, resultat.stdout
    assert retrait == []
    assert "nothing to remove" in resultat.stdout


def test_destroy_optional_hosts_refuse_host(depot: Path, retrait: list[list[str]]) -> None:
    resultat = runner.invoke(app, [
        "destroy", "--optional-hosts", "--host", "cp.lab", "--yes",
        "--lab-home", str(depot),
    ])
    assert resultat.exit_code == 1
    assert retrait == []


# ── run ────────────────────────────────────────────────────────────────────


class _Lab:
    """Le strict nécessaire de LabDefinition pour `_monter_les_hotes_optionnels`."""

    class runtime:  # imite l'attribut du vrai modèle
        class type:
            value = "vm"


@pytest.fixture
def montage(monkeypatch: pytest.MonkeyPatch) -> list[list[str] | None]:
    appels: list[list[str] | None] = []
    from dsoxlab.cli import demarrage, infrastructure

    monkeypatch.setattr(
        infrastructure, "provisionner", lambda root, host=None, **k: appels.append(host)
    )
    monkeypatch.setattr(demarrage, "_hotes_a_monter", lambda root, hotes: list(hotes))
    return appels


def _cible(monkeypatch: pytest.MonkeyPatch, hotes: list[str]) -> None:
    from dsoxlab.runtimes import vm

    class _Target:
        def hosts(self) -> list[str]:
            return hotes

    monkeypatch.setattr(vm, "resoudre_target", lambda lab, target: _Target())


def test_run_monte_les_optionnels_que_le_lab_cite(
    depot: Path, monkeypatch: pytest.MonkeyPatch, montage: list[list[str] | None]
) -> None:
    _cible(monkeypatch, ["cp.lab", "cp2.lab", "lb.lab"])
    parcours._monter_les_hotes_optionnels(depot, _Lab(), None)  # type: ignore[arg-type]
    assert montage == [["cp.lab", "cp2.lab", "lb.lab"]]


def test_run_ne_provisionne_rien_pour_un_lab_sans_optionnel(
    depot: Path, monkeypatch: pytest.MonkeyPatch, montage: list[list[str] | None]
) -> None:
    """Le comportement d'avant la 0.9.0 : run ne monte jamais d'infra."""
    _cible(monkeypatch, ["cp.lab", "w1.lab"])
    parcours._monter_les_hotes_optionnels(depot, _Lab(), None)  # type: ignore[arg-type]
    assert montage == []


@pytest.mark.parametrize("valeur", ['"cp2.lab"', "{name: cp2.lab}", "[cp2.lab]", "[{ram_mb: 512}]"])
def test_optional_hosts_mal_forme_leve_dans_le_contrat(depot: Path, valeur: str) -> None:
    # Le lab fautif est alors écarté avec un avertissement, sans trace Python.
    meta = META.split("  optional_hosts:")[0] + f"  optional_hosts: {valeur}\n"
    (depot / "meta.yml").write_text(meta, encoding="utf-8")
    with pytest.raises((KeyError, ValueError)):
        _meta(depot)


# ── start et reset ─────────────────────────────────────────────────────────


def _lab_vm(identifiant: str, roles: dict[str, str]) -> str:
    lignes = "".join(f"        {role}: {hote}\n" for role, hote in roles.items())
    return (
        f"id: {identifiant}\ntitle: {identifiant}\nlevel: l1\nskills: [demo]\n"
        "distros: [any]\ndoc_url: https://example.test/d/\n"
        "runtime:\n  type: vm\n  targets:\n    - name: cible\n      host: cp.lab\n"
        f"      roles:\n{lignes}  default: cible\n"
    )


@pytest.fixture
def labs_vm(depot: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Deux labs vm : l'un cite l'optionnel lb.lab par un rôle, l'autre non."""
    for nom, roles in (
        ("avec-lb", {"lb": "lb.lab"}),
        ("sans-optionnel", {"worker": "w1.lab"}),
    ):
        dossier = depot / "labs" / "demo" / nom
        (dossier / "challenge" / "tests").mkdir(parents=True)
        (dossier / "lab.yaml").write_text(_lab_vm(nom, roles), encoding="utf-8")
        for playbook in ("setup.yaml", "cleanup.yaml"):
            (dossier / playbook).write_text("- hosts: lab_target\n  tasks: []\n",
                                            encoding="utf-8")
    monkeypatch.delenv("DSOXLAB_TARGET", raising=False)
    return depot


@pytest.fixture
def espion_start(monkeypatch: pytest.MonkeyPatch) -> dict[str, Any]:
    """Ce que `start` passe à `provisionner`, sans rien monter ni jouer."""
    from dsoxlab.cli import demarrage, infrastructure
    from dsoxlab.services import doctor

    vu: dict[str, Any] = {"host": "jamais appelé"}

    def _faux_provision(root: Path, **kw: Any) -> None:
        vu["host"] = kw.get("host")

    monkeypatch.setattr(infrastructure, "provisionner", _faux_provision)
    monkeypatch.setattr(demarrage, "provisionner", _faux_provision, raising=False)
    monkeypatch.setattr(parcours, "run", lambda **kw: None)
    monkeypatch.setattr(
        doctor, "collect_checks",
        lambda root, meta, hosts=None: doctor.DoctorReport(
            required=[doctor._check("python", True, "3.13")]
        ),
    )
    return vu


def test_start_passe_l_optionnel_cite_par_un_role_a_provisionner(
    labs_vm: Path, espion_start: dict[str, Any]
) -> None:
    resultat = runner.invoke(app, ["start", "avec-lb", "--lab-home", str(labs_vm)])
    assert resultat.exit_code == 0, resultat.output
    assert espion_start["host"] == ["cp.lab", "lb.lab"]


def test_start_n_ajoute_aucun_optionnel_a_un_lab_qui_n_en_cite_pas(
    labs_vm: Path, espion_start: dict[str, Any]
) -> None:
    resultat = runner.invoke(
        app, ["start", "sans-optionnel", "--lab-home", str(labs_vm)]
    )
    assert resultat.exit_code == 0, resultat.output
    assert espion_start["host"] == ["cp.lab", "w1.lab"]


def test_reset_ne_retire_jamais_un_hote_optionnel_monte(
    labs_vm: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`reset` rejoue cleanup puis setup ; il ne touche pas à Terraform.

    On simule la frontière la plus basse, le playbook, et on observe tout ce
    par où un retrait passerait : le retrait dédié, une destruction, un apply,
    et des tfvars écrits avec `retires=`.
    """
    from dsoxlab.infra import ansible
    from dsoxlab.infra.ansible import PlaybookResult
    from dsoxlab.runtimes.vm import VmRuntime

    _poser_le_state(tmp_path, ["cp.lab", "w1.lab", "lb.lab"])
    appels: list[str] = []
    playbooks: list[str] = []

    def _noter(nom: str):  # type: ignore[no-untyped-def]
        return lambda *a, **k: appels.append(nom)

    for nom in ("retirer_hotes_optionnels", "destroy", "apply"):
        monkeypatch.setattr(terraform, nom, _noter(nom))
    ecrire = terraform.write_tfvars

    def _tfvars(meta: Any, **kw: Any) -> Path:
        if kw.get("retires"):
            appels.append(f"tfvars retires={kw['retires']}")
        return ecrire(meta, **kw)

    monkeypatch.setattr(terraform, "write_tfvars", _tfvars)
    monkeypatch.setattr(ansible, "is_available", lambda: True)
    monkeypatch.setattr(
        ansible, "run_playbook",
        lambda playbook_path, **k: playbooks.append(Path(playbook_path).name)
        or PlaybookResult(rc=0, status="successful"),
    )
    monkeypatch.setattr(VmRuntime, "_inventory", lambda self, meta, target: {})

    resultat = runner.invoke(
        app, ["reset", "avec-lb", "--yes", "--lab-home", str(labs_vm)]
    )
    assert resultat.exit_code == 0, resultat.output
    # Le témoin que le chemin réel a été parcouru : sans lui, un reset qui
    # sortirait tôt passerait ce test sans rien prouver.
    assert playbooks == ["cleanup.yaml", "setup.yaml"]
    assert appels == []
