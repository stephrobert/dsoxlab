"""Un dépôt qui ne provisionne que de l'infrastructure, sans un seul TP.

C'est un usage réel et déjà en production (`lab-guides-validation` : des VM
jetables pour rejouer un guide avant publication). Le socle s'y prête depuis
toujours — `provision`, `destroy`, `ssh` et `infra status` ne lisent que le
`meta.yml` — mais deux surfaces le traitaient comme un catalogue raté.

`repo.category`, purement pédagogique, était exigé de tous : il fallait inventer
une valeur que rien ne lit (issue #231). Et `doctor` déduisait le besoin
d'hyperviseur des seuls labs, donc rangeait terraform et libvirt en
« informatifs » sur le seul dépôt dont ils conditionnent la commande principale
(issue #230). Un `--strict` y rendait 0 sur un environnement incapable de monter
quoi que ce soit.

Le contre-exemple est tenu ici aussi : `terraform-training` n'a aucun bloc
`infra:`, et rien ne doit y devenir requis.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from dsoxlab.models._contract import ContractError
from dsoxlab.models.lab import LabDefinition, ValidationConfig
from dsoxlab.models.repo import HostDefinition, InfraDefinition, RepoMetadata
from dsoxlab.models.runtime import RuntimeConfig, RuntimeType
from dsoxlab.services import doctor
from dsoxlab.validators.contract import validate_repo_fields

STACK = """\
repo:
  id: ma-stack
  title: Stack jetable

infra:
  provider: kvm
  network: lab-stack
  cidr: 10.10.90.0/24
  hosts:
    - name: db.lab
      distro: debian13
"""


def _lab_shell(lab_id: str = "demo") -> LabDefinition:
    return LabDefinition(
        id=lab_id,
        title=lab_id,
        level="l1",
        skills=["s"],
        runtime=RuntimeConfig(type=RuntimeType.SHELL, workdir="challenge/work"),
        distros=["debian13"],
        doc_url="https://example.test/doc",
        validation=ValidationConfig(),
    )


def _meta(*, hosts: bool) -> RepoMetadata:
    infra = InfraDefinition(
        provider="kvm",
        hosts=[HostDefinition(name="db.lab")] if hosts else [],
    )
    return RepoMetadata(id="demo", category="", infra=infra)


def _poser_lab(racine: Path, lab_id: str = "demo") -> None:
    dossier = racine / "labs" / lab_id
    dossier.mkdir(parents=True)
    (dossier / "lab.yaml").write_text(f"id: {lab_id}\n", encoding="utf-8")


# ── le contrat : `category` n'est plus exigé de tous ──────────────────────────

def test_un_meta_sans_category_se_charge(tmp_path: Path) -> None:
    """La seule friction bloquante d'un usage infra pur (issue #231)."""
    chemin = tmp_path / "meta.yml"
    chemin.write_text(STACK, encoding="utf-8")

    meta = RepoMetadata.from_yaml(chemin)

    assert meta.id == "ma-stack"
    assert meta.category == ""
    assert [h.name for h in meta.infra.hosts] == ["db.lab"]


def test_repo_id_reste_exige(tmp_path: Path) -> None:
    """`id` nomme l'espace d'état et les conteneurs : lui n'est pas déductible."""
    chemin = tmp_path / "meta.yml"
    chemin.write_text("repo:\n  category: linux\n", encoding="utf-8")

    with pytest.raises(ContractError):
        RepoMetadata.from_yaml(chemin)


# ── le contrôle déplacé : réclamé à qui porte des labs, à lui seul ────────────

def test_category_absente_est_signalee_quand_des_labs_existent(tmp_path: Path) -> None:
    (tmp_path / "meta.yml").write_text(STACK, encoding="utf-8")
    _poser_lab(tmp_path)

    report = validate_repo_fields(tmp_path)

    assert not report.ok
    assert [i.key for i in report.issues] == ["category_absente_avec_labs"]
    assert report.issues[0].params == {"labs": 1}


def test_category_absente_ne_dit_rien_sans_lab(tmp_path: Path) -> None:
    """C'est tout l'objet du changement : une stack d'infra n'a rien à déclarer."""
    (tmp_path / "meta.yml").write_text(STACK, encoding="utf-8")

    assert validate_repo_fields(tmp_path).ok


def test_une_category_declaree_ne_dit_rien(tmp_path: Path) -> None:
    (tmp_path / "meta.yml").write_text(
        "repo:\n  id: demo\n  category: linux\n", encoding="utf-8"
    )
    _poser_lab(tmp_path)

    assert validate_repo_fields(tmp_path).ok


def test_un_meta_illisible_ne_produit_pas_un_second_rouge(tmp_path: Path) -> None:
    """`validate_schema_versions` le dit déjà : une cause, une ligne."""
    (tmp_path / "meta.yml").write_text("repo: [oui\n  - non", encoding="utf-8")
    _poser_lab(tmp_path)

    assert validate_repo_fields(tmp_path).ok


# ── doctor : un hôte déclaré est un engagement ───────────────────────────────

def _noms(checks: list[doctor.Check]) -> set[str]:
    return {c.key for c in checks}


def test_des_hotes_declares_rendent_l_hyperviseur_requis(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Zéro lab, deux hôtes : c'est le dépôt qui provisionne le plus (issue #230)."""
    monkeypatch.setattr(doctor, "get_all_labs", lambda _root: [])

    report = doctor.collect_checks(tmp_path, _meta(hosts=True))

    requis = _noms(report.required)
    assert "terraform" in requis
    assert "egress" in requis
    assert "provider" in requis


def test_sans_bloc_infra_rien_ne_devient_requis(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Le contre-exemple `terraform-training` : labs `shell`, aucun `infra:`.

    C'est lui qui attrape la régression inverse, celle où l'on rendrait tout
    requis partout et où le premier lancement virerait au rouge.
    """
    monkeypatch.setattr(doctor, "get_all_labs", lambda _root: [_lab_shell()])

    report = doctor.collect_checks(tmp_path, _meta(hosts=False))

    # terraform n'est pas seulement hors du requis : sans rien à provisionner,
    # il ne figure dans aucune des deux listes. Les hyperviseurs, eux, restent
    # affichés en informatifs, et c'est ce qui évite le rouge du premier
    # lancement sur un catalogue entièrement `shell`.
    assert "terraform" not in _noms(report.required)
    assert "egress" not in _noms(report.required)
    assert {"kvm", "incus"} <= _noms(report.optional)


def test_zero_lab_n_est_pas_un_defaut_sur_une_stack_d_infra(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Ce rouge était le seul que voyait l'utilisateur d'un dépôt de VM."""
    monkeypatch.setattr(doctor, "get_all_labs", lambda _root: [])

    report = doctor.collect_checks(tmp_path, _meta(hosts=True))
    labs = next(c for c in report.required if c.key == "labs")

    assert labs.ok


def test_zero_lab_reste_un_defaut_sur_un_catalogue(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Sans infra déclarée, zéro lab veut toujours dire « il manque quelque chose »."""
    monkeypatch.setattr(doctor, "get_all_labs", lambda _root: [])

    report = doctor.collect_checks(tmp_path, _meta(hosts=False))
    labs = next(c for c in report.required if c.key == "labs")

    assert not labs.ok
