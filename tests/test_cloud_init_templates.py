"""Cohérence entre le mapping distro des providers Terraform et les cloud-init.

Chaque `main.tf` de provider déclare un bloc ``distro_to_template`` qui associe
une distro pédagogique (``debian12``, ``ubuntu24``…) au *stem* d'un template
cloud-init packagé sous ``templates/cloud-init/<stem>.yaml.tmpl``. Si une distro
pointe vers un template absent, ``cloud_init_template()`` lève au moment du
provision, sur un provider donné seulement, et jamais en test.

Ce fichier ferme ce trou : il a été ajouté après qu'un mapping ``debian12 =
"debian"`` a été déclaré dans les trois providers alors que ``debian.yaml.tmpl``
n'existait pas encore. Il garde aussi les trois providers alignés entre eux.
"""

from __future__ import annotations

import re

import pytest

from dsoxlab.templates import cloud_init_template, template_root

PROVIDERS = ("kvm", "incus", "outscale")

_BLOCK_RE = re.compile(r"distro_to_template\s*=\s*\{(.*?)\}", re.DOTALL)
_ENTRY_RE = re.compile(r"(\w+)\s*=\s*\"([^\"]+)\"")


def _distro_to_template(provider: str) -> dict[str, str]:
    """Extrait le bloc ``distro_to_template`` du main.tf d'un provider."""
    main_tf = template_root() / "terraform" / provider / "main.tf"
    block = _BLOCK_RE.search(main_tf.read_text(encoding="utf-8"))
    assert block, f"bloc distro_to_template introuvable dans {main_tf}"
    return dict(_ENTRY_RE.findall(block.group(1)))


@pytest.mark.parametrize("provider", PROVIDERS)
def test_every_mapped_distro_has_a_cloud_init(provider: str) -> None:
    mapping = _distro_to_template(provider)
    assert mapping, f"{provider} : distro_to_template vide"
    for distro, stem in mapping.items():
        # cloud_init_template lève FileNotFoundError si le template manque :
        # c'est exactement l'échec de provision qu'on veut attraper ici.
        path = cloud_init_template(stem)
        assert path.is_file(), f"{provider}: {distro} -> {stem}.yaml.tmpl absent"


def test_debian12_supported_on_all_providers() -> None:
    """debian12 doit être mappé partout, vers le cloud-init debian."""
    for provider in PROVIDERS:
        mapping = _distro_to_template(provider)
        assert mapping.get("debian12") == "debian", (
            f"{provider} : debian12 doit pointer vers le template 'debian'"
        )
    assert cloud_init_template("debian").is_file()


def test_all_providers_share_the_same_distro_set() -> None:
    """Les trois providers doivent proposer les mêmes distros (pas de trou)."""
    sets = {p: frozenset(_distro_to_template(p)) for p in PROVIDERS}
    reference = sets["kvm"]
    for provider, distros in sets.items():
        assert distros == reference, (
            f"{provider} diverge de kvm : {distros ^ reference}"
        )


def test_no_orphan_cloud_init_used() -> None:
    """Tout template cloud-init packagé est bien un fichier .yaml.tmpl lisible."""
    cloud_init_dir = template_root() / "cloud-init"
    for tmpl in cloud_init_dir.glob("*.yaml.tmpl"):
        stem = tmpl.name[: -len(".yaml.tmpl")]
        assert cloud_init_template(stem) == tmpl
