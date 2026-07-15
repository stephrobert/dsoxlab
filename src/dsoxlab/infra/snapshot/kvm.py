"""Backend snapshot KVM via ``virsh`` (libvirt).

Note : Terraform ``dmacvicar/libvirt`` ne gère pas les snapshots
libvirt. C'est une limitation connue ; on bypass en invoquant
``virsh snapshot-*`` directement. Les snapshots sont stockés dans le
state libvirt local — ils survivent au redémarrage de l'hôte.

Le nom de domaine libvirt **doit matcher le FQDN sans le suffixe**
``.lab``. Convention dsoxlab : ``alma-rhcsa-1.lab`` côté logique,
``alma-rhcsa-1`` côté virsh.
"""

from __future__ import annotations

import logging

from ...models.repo import RepoMetadata
from ...utils.shell import CommandError, run_command

logger = logging.getLogger(__name__)


def _domain_name(host_fqdn: str) -> str:
    """Convertit un FQDN logique en nom de domaine libvirt.

    Convention : ``alma-rhcsa-1.lab`` → ``alma-rhcsa-1``.
    """
    return host_fqdn.split(".", 1)[0]


def create(repo_meta: RepoMetadata, hosts: list[str], name: str) -> None:
    """Crée un snapshot ``name`` sur chaque domaine libvirt listé."""
    del repo_meta  # non utilisé — meta.yml accessible via host_fqdn → domain
    for fqdn in hosts:
        domain = _domain_name(fqdn)
        logger.info("virsh snapshot-create-as %s %s", domain, name)
        run_command(
            [
                "sudo", "virsh", "snapshot-create-as",
                "--domain", domain,
                "--name", name,
                "--description", "dsoxlab checkpoint",
                "--atomic",
            ],
            timeout=120,
        )


def revert(repo_meta: RepoMetadata, hosts: list[str], name: str) -> None:
    """Revert chaque domaine vers son snapshot ``name``."""
    del repo_meta
    for fqdn in hosts:
        domain = _domain_name(fqdn)
        logger.info("virsh snapshot-revert %s %s", domain, name)
        run_command(
            ["sudo", "virsh", "snapshot-revert", domain, name],
            timeout=120,
        )


def delete(repo_meta: RepoMetadata, hosts: list[str], name: str) -> None:
    """Supprime le snapshot ``name`` sur chaque domaine."""
    del repo_meta
    for fqdn in hosts:
        domain = _domain_name(fqdn)
        try:
            run_command(
                ["sudo", "virsh", "snapshot-delete", domain, name],
                timeout=60,
                check=True,
            )
        except CommandError as exc:
            logger.warning(
                "snapshot-delete a échoué pour %s/%s : %s",
                domain, name, exc.result.stderr.strip(),
            )


def list_(repo_meta: RepoMetadata, host: str) -> list[str]:
    """Retourne la liste des snapshots libvirt pour ``host``."""
    del repo_meta
    domain = _domain_name(host)
    result = run_command(
        ["sudo", "virsh", "snapshot-list", domain, "--name"],
        check=False,
    )
    if not result.ok:
        return []
    return [line.strip() for line in result.stdout.splitlines() if line.strip()]
