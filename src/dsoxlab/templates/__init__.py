"""Templates de provisioning packagés avec dsoxlab.

Le framework livre **tout le code de création** des labs (Terraform
modules par provider, cloud-init par distribution). Les dépôts
fournisseurs (linux-training, ansible-training, …) ne contiennent
que des **labs déclaratifs** (lab.yaml, setup.yaml, cleanup.yaml,
solution.yaml).

À chaque ``dsoxlab provision``, dsoxlab :

1. Lit ``meta.yml: infra.provider`` du dépôt fournisseur courant.
2. Copie ``templates/terraform/<provider>/*.tf`` vers
   ``~/.local/state/dsoxlab/<repo-id>/terraform/<provider>/``
   (work-dir XDG isolé par dépôt).
3. Génère ``<work-dir>/.dsoxlab.auto.tfvars.json`` depuis
   ``meta.yml: infra.hosts[]`` + ``providers.<provider>``.
4. Lance ``terraform -chdir=<work-dir> {init,apply,...}``.

Contrat invariant que tout template provider doit respecter :

- Inputs (variables.tf) : ``network_name``, ``network_cidr``,
  ``hosts`` (liste), ``provider_config`` (map d'overrides).
- Outputs (outputs.tf) : ``hosts`` (map FQDN → IP),
  ``bastion`` (objet ou null) — voir templates/terraform/README.md.

Les playbooks Ansible des labs (setup/cleanup/solution) ciblent le
groupe ``lab_target`` injecté dynamiquement par dsoxlab — ils sont
strictement portables entre providers.
"""

from __future__ import annotations

from pathlib import Path


def template_root() -> Path:
    """Retourne la racine des templates packagés (dsoxlab/templates/)."""
    return Path(__file__).parent.resolve()


def terraform_template(provider: str) -> Path:
    """Retourne le chemin du template Terraform pour un provider.

    Args:
        provider: nom du provider (ex. ``kvm``, ``outscale``, ``aws``).

    Returns:
        Chemin du dossier contenant les fichiers ``.tf``.

    Raises:
        FileNotFoundError: si aucun template n'existe pour ce provider.
    """
    path = template_root() / "terraform" / provider
    if not path.is_dir():
        raise FileNotFoundError(
            f"Template Terraform absent pour le provider '{provider}'. "
            f"Providers packagés dans dsoxlab : "
            f"{sorted(p.name for p in (template_root() / 'terraform').iterdir() if p.is_dir())}"
        )
    return path


def cloud_init_template(distro: str) -> Path:
    """Retourne le chemin du template cloud-init pour une distribution.

    Args:
        distro: ``almalinux``, ``ubuntu``, ``opensuse``, ``debian``…

    Returns:
        Chemin du fichier ``.yaml.tmpl``.

    Raises:
        FileNotFoundError: si pas de template pour cette distribution.
    """
    path = template_root() / "cloud-init" / f"{distro}.yaml.tmpl"
    if not path.is_file():
        raise FileNotFoundError(
            f"Template cloud-init absent pour la distribution '{distro}'. "
            f"Distros packagées : "
            f"{sorted(p.stem.replace('.yaml', '') for p in (template_root() / 'cloud-init').glob('*.yaml.tmpl'))}"
        )
    return path
