"""Backend snapshot KVM via ``virsh`` (libvirt).

Note : Terraform ``dmacvicar/libvirt`` ne gère pas les snapshots
libvirt. C'est une limitation connue ; on bypass en invoquant
``virsh snapshot-*`` directement. Les snapshots sont stockés dans le
state libvirt local — ils survivent au redémarrage de l'hôte.

**Le nom du domaine n'est pas déduit, il est résolu.** Le template Terraform
packagé ici nomme le domaine avec le ``infra.hosts[].name`` du ``meta.yml``
**tel quel**, c'est-à-dire un FQDN (``control-node.lab``). Ce module a
longtemps supposé l'inverse — qu'il fallait couper le suffixe — et visait donc
un domaine inexistant. La résolution passe désormais par
``infra.libvirt.resolve_domain``, qui interroge libvirt et accepte le nom court
en repli, pour les infrastructures créées par une version antérieure du
template.
"""

from __future__ import annotations

import logging

from ...models.repo import RepoMetadata
from ...utils.shell import CommandError, run_command
from ..libvirt import DomainNotFound, list_domains, resolve_domain

logger = logging.getLogger(__name__)


def create(repo_meta: RepoMetadata, hosts: list[str], name: str) -> None:
    """Crée un snapshot ``name`` sur chaque domaine libvirt listé.

    Raises:
        DomainNotFound: si un hôte ne correspond à aucun domaine.
    """
    del repo_meta  # non utilisé — meta.yml accessible via host_fqdn → domain
    known = list_domains()
    for fqdn in hosts:
        domain = resolve_domain(fqdn, known=known)
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
    """Revert chaque domaine vers son snapshot ``name``.

    Raises:
        DomainNotFound: si un hôte ne correspond à aucun domaine.
    """
    del repo_meta
    known = list_domains()
    for fqdn in hosts:
        domain = resolve_domain(fqdn, known=known)
        logger.info("virsh snapshot-revert %s %s", domain, name)
        run_command(
            ["sudo", "virsh", "snapshot-revert", domain, name],
            timeout=120,
        )


def delete(repo_meta: RepoMetadata, hosts: list[str], name: str) -> None:
    """Supprime le snapshot ``name`` sur chaque domaine.

    Best-effort assumé : un snapshot déjà absent, comme un domaine déjà
    détruit, ne doit pas faire échouer un nettoyage. Les deux cas sont
    journalisés en nommant ce qui manque.
    """
    del repo_meta
    known = list_domains()
    for fqdn in hosts:
        try:
            domain = resolve_domain(fqdn, known=known)
        except DomainNotFound as exc:
            logger.warning("snapshot-delete ignoré : %s", exc)
            continue
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
    """Retourne la liste des snapshots libvirt pour ``host``.

    Raises:
        DomainNotFound: si l'hôte ne correspond à aucun domaine. Rendre une
            liste vide confondrait « ce domaine n'a pas de snapshot » avec
            « ce domaine n'existe pas », qui appellent des gestes opposés.
    """
    del repo_meta
    domain = resolve_domain(host)
    result = run_command(
        ["sudo", "virsh", "snapshot-list", domain, "--name"],
        check=False,
    )
    if not result.ok:
        return []
    return [line.strip() for line in result.stdout.splitlines() if line.strip()]
