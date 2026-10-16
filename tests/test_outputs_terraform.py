"""Les outputs de Terraform sont une entrée que dsoxlab ne produit pas (#71).

Ils viennent d'un binaire externe dont la version, les providers et le schéma de
sortie bougent sans que l'outil le sache. `terraform output -json` encapsule
chaque valeur dans ``{"nom": {"value": …, "type": …}}``, mais un state écrit par
une autre version, un provider qui a renommé sa sortie, ou un state édité à la
main arrivent chez le même lecteur.

Le défaut ci-dessous a été trouvé par `fuzz/fuzz_terraform_outputs.py`, sur un
document de trente-quatre octets. Ce test le fige : le fuzzing découvre, un test
empêche le retour.
"""

from __future__ import annotations

import logging
from pathlib import Path

import pytest

from dsoxlab.infra.inventory import InfraNotProvisioned, build_inventory
from dsoxlab.models.repo import RepoMetadata

META = """\
repo:
  id: essai
  category: demo
infra:
  provider: kvm
  network: essai-net
  cidr: 10.99.0.0/24
  hosts:
    - name: un.lab
      distro: alma10
"""


@pytest.fixture
def repo_meta(tmp_path: Path) -> RepoMetadata:
    chemin = tmp_path / "meta.yml"
    chemin.write_text(META, encoding="utf-8")
    return RepoMetadata.from_yaml(chemin)


#: Un meta à DEUX hôtes : c'est la seule façon d'avoir des outputs Terraform
#: tout en ayant un hôte qui n'y figure pas, le cas où l'anomalie est réelle.
META_DEUX_HOTES = META.replace(
    "    - name: un.lab\n      distro: alma10\n",
    "    - name: un.lab\n      distro: alma10\n"
    "    - name: deux.lab\n      distro: alma10\n",
)


@pytest.fixture
def repo_meta_deux(tmp_path: Path) -> RepoMetadata:
    chemin = tmp_path / "meta-deux.yml"
    chemin.write_text(META_DEUX_HOTES, encoding="utf-8")
    return RepoMetadata.from_yaml(chemin)


def test_sans_aucun_output_l_absence_d_ip_n_est_pas_un_avertissement(
    repo_meta: RepoMetadata, caplog: pytest.LogCaptureFixture
) -> None:
    """Rien de provisionné est l'état NORMAL avant `provision`.

    Mesuré le 2026-10-16 : `dsoxlab infra status` sur un catalogue à labs `vm`
    sans infrastructure debout déversait une ligne de logger brut par hôte,
    puis disait proprement la même chose (« aucune ne tourne »). Le logger
    doublait l'interface, en moins lisible. L'information reste au journal et
    ressort avec `-v` : elle passe en `info`, pas à la trappe.
    """
    caplog.set_level(logging.INFO, logger="dsoxlab.infra.inventory")
    with pytest.raises(InfraNotProvisioned):
        build_inventory(repo_meta, terraform_outputs={})

    niveaux = {enregistrement.levelno for enregistrement in caplog.records}
    assert logging.WARNING not in niveaux, (
        "l'absence totale d'infrastructure ne doit pas produire d'avertissement : "
        f"niveaux relevés {sorted(niveaux)}"
    )
    assert any("nothing is provisioned" in r.getMessage() for r in caplog.records)


def test_un_hote_absent_d_outputs_existants_reste_un_avertissement(
    repo_meta_deux: RepoMetadata, caplog: pytest.LogCaptureFixture
) -> None:
    """Là, l'infrastructure est debout et il manque une machine : ça doit crier.

    C'est le signal qu'il ne fallait pas perdre en silenciant le cas normal.
    """
    caplog.set_level(logging.INFO, logger="dsoxlab.infra.inventory")
    inventaire = build_inventory(
        repo_meta_deux,
        terraform_outputs={"hosts": {"value": {"un.lab": "10.99.0.11"}}},
    )

    assert "un.lab" in inventaire["all"]["children"]["labenv"]["hosts"]
    avertissements = [r for r in caplog.records if r.levelno >= logging.WARNING]
    assert any("deux.lab" in r.getMessage() for r in avertissements), (
        "un hôte manquant alors que la stack est debout doit produire un "
        f"avertissement ; relevé : {[r.getMessage() for r in caplog.records]}"
    )


def test_un_output_hosts_qui_n_est_pas_un_objet_ne_leve_pas(repo_meta: RepoMetadata) -> None:
    """`{"hosts": {"value": "10.99.0.11"}}` faisait `AttributeError`.

    Le code prenait `raw.get("value", raw)` pour un mapping et appelait
    `.items()` dessus. Le résultat était un traceback au moment de jouer un lab,
    sans jamais dire que la cause était un state Terraform périmé.

    Ce qui est attendu à la place n'est pas « ça marche » : c'est la phrase que
    la CLI sait déjà rendre quand aucun hôte n'a d'adresse.
    """
    with pytest.raises(InfraNotProvisioned):
        build_inventory(repo_meta, terraform_outputs={"hosts": {"value": "10.99.0.11"}})


@pytest.mark.parametrize(
    ("nom", "outputs"),
    [
        ("value en liste", {"hosts": {"value": ["10.99.0.11"]}}),
        ("value nulle", {"hosts": {"value": None}}),
        ("value numérique", {"hosts": {"value": 167837707}}),
        ("hosts en liste", {"hosts": ["10.99.0.11"]}),
        ("hosts en chaîne", {"hosts": "10.99.0.11"}),
        ("sortie d'une autre version", {"autre_chose": {"value": 42}}),
    ],
    ids=lambda v: v if isinstance(v, str) else "",
)
def test_aucune_forme_d_output_ne_rend_un_traceback(
    repo_meta: RepoMetadata, nom: str, outputs: dict[str, object]
) -> None:
    """Toutes ces formes sont plausibles, aucune ne doit surprendre l'appelant.

    Le contrat n'est pas que dsoxlab les honore : c'est qu'il les refuse par une
    exception que la CLI sait rendre en une phrase.
    """
    with pytest.raises(InfraNotProvisioned):
        build_inventory(repo_meta, terraform_outputs=outputs)


def test_la_forme_normale_reste_lue(repo_meta: RepoMetadata) -> None:
    """Le contre-test : sans lui, refuser TOUT passerait pour une correction."""
    inventaire = build_inventory(
        repo_meta, terraform_outputs={"hosts": {"value": {"un.lab": "10.99.0.11"}}}
    )

    hotes = inventaire["all"]["children"]["labenv"]["hosts"]
    assert hotes["un.lab"]["ansible_host"] == "10.99.0.11"


def test_la_forme_aplatie_reste_lue(repo_meta: RepoMetadata) -> None:
    """L'autre forme acceptée, selon d'où viennent les outputs."""
    inventaire = build_inventory(repo_meta, terraform_outputs={"hosts": {"un.lab": "10.99.0.11"}})

    hotes = inventaire["all"]["children"]["labenv"]["hosts"]
    assert hotes["un.lab"]["ansible_host"] == "10.99.0.11"
