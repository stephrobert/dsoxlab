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


def test_debian12_is_supported_on_all_providers() -> None:
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


def test_le_pool_libvirt_n_est_plus_code_en_dur() -> None:
    """Le pool `default` n'existe pas sur une installation fraîche.

    Sur une Ubuntu 24.04 avec `libvirt-daemon-system`, `virsh pool-list --all`
    est vide : le provisionnement s'arrêtait sur un « Pool Not Found » brut de
    Terraform, sans qu'aucun réglage ne permette d'en viser un autre. Le nom
    était écrit en dur à quatre endroits du `main.tf`.
    """
    main_tf = (template_root() / "terraform" / "kvm" / "main.tf").read_text(
        encoding="utf-8"
    )

    assert not re.search(r'^\s*pool\s*=\s*"default"', main_tf, re.MULTILINE), (
        "aucun `pool = \"default\"` ne doit rester : le pool se lit dans "
        "provider_config, sinon un dépôt ne peut pas viser le sien"
    )
    assert 'storage_pool = lookup(var.provider_config, "storage_pool", "default")' in main_tf, (
        "le pool doit venir de meta.yml: infra.providers.kvm.storage_pool, "
        "avec `default` comme repli"
    )
    assert main_tf.count("pool = local.storage_pool") + main_tf.count(
        "pool     = local.storage_pool"
    ) == 4, "les quatre emplacements doivent tous passer par le local"


# ── Les paquets déclarés doivent exister sur les distributions du contrat ────
#
# Ajouté le 2026-10-19, après un provisionnement Debian 13 sorti en
# « status: error » : la liste citait `dnsutils`, un simple paquet de transition
# retiré de Debian 13 et d'Ubuntu 26. Il n'avait plus de candidat, cloud-init
# échouait sur son module de paquets, et `dig` comme `nslookup` manquaient sur
# chaque VM.
#
# CE QUE CE CONTRÔLE EST, ET CE QU'IL N'EST PAS
#
# C'est un lint, pas une mesure : rien ici n'interroge un miroir Debian, donc il
# ne peut pas dire qu'un paquet existe. Il dit seulement qu'aucun paquet connu
# pour avoir DISPARU ne figure dans la liste. La seule mesure qui vaut reste un
# provisionnement, et c'est lui qui a trouvé celui-ci : la liste ci-dessous
# s'allonge d'un nom chaque fois qu'un provisionnement en désigne un.

_PAQUETS_DISPARUS = {
    # nom retiré: ce qu'il faut écrire à la place
    "dnsutils": "bind9-dnsutils",
    "iproute": "iproute2",
    "netcat": "netcat-openbsd",
    "python-is-python3": "python3",
}

_PACKAGES_RE = re.compile(r"^packages:\s*$(.*?)^\S", re.DOTALL | re.MULTILINE)


def _paquets_declares(stem: str) -> list[str]:
    """Les paquets du bloc ``packages:`` d'un cloud-init packagé."""
    texte = cloud_init_template(stem).read_text(encoding="utf-8")
    bloc = _PACKAGES_RE.search(texte)
    if bloc is None:  # un template sans bloc packages est légitime
        return []
    return [
        ligne.strip().removeprefix("-").strip()
        for ligne in bloc.group(1).splitlines()
        if ligne.strip().startswith("-")
    ]


@pytest.mark.parametrize("stem", ("debian", "ubuntu", "almalinux"))
def test_aucun_paquet_de_transition_disparu(stem: str) -> None:
    fautifs = {
        paquet: _PAQUETS_DISPARUS[paquet]
        for paquet in _paquets_declares(stem)
        if paquet in _PAQUETS_DISPARUS
    }
    assert not fautifs, (
        f"{stem}.yaml.tmpl déclare un paquet qui n'a plus de candidat : "
        + ", ".join(f"{mauvais} (écrire {bon})" for mauvais, bon in fautifs.items())
        + ". cloud-init échoue alors sur TOUT son module de paquets, et le "
        "provisionnement sort en « status: error »."
    )


@pytest.mark.parametrize("stem", ("debian", "ubuntu"))
def test_les_outils_de_resolution_dns_sont_la(stem: str) -> None:
    """`dig` est l'outil de diagnostic d'un lab réseau : il doit être posé."""
    assert "bind9-dnsutils" in _paquets_declares(stem), (
        f"{stem}.yaml.tmpl ne pose plus d'outil de résolution DNS : dig et "
        "nslookup manqueront sur chaque VM."
    )
