"""Abstraction snapshots multi-provider.

Le dispatch lit ``meta.yml: infra.provider`` et délègue à
``snapshot/<provider>.py``. Chaque module provider expose la même
interface :

- ``create(repo_meta, hosts, name) -> None``
- ``revert(repo_meta, hosts, name) -> None``
- ``delete(repo_meta, hosts, name) -> None``
- ``purge(repo_meta, hosts) -> list[str]``
- ``list_(repo_meta, host) -> list[str]``

``purge`` est l'opération que réclame la destruction d'une infrastructure : un
snapshot laisse derrière lui un artefact de stockage que l'outil de
provisionnement ne connaît pas, et qui lui survivrait. Elle rend ce qu'elle a
retiré, pour que l'appelant puisse le dire.

Si un provider n'est pas encore implémenté,
``NotImplementedError`` est levée avec un message explicite.

État MVP : seul ``kvm`` est implémenté (via ``virsh``). Les providers
``proxmox``, ``aws``, ``gcp``, ``azure`` lèveront ``NotImplementedError``
jusqu'à leur implémentation.
"""

from __future__ import annotations

import importlib
from typing import Protocol

from ...i18n import _
from ...models.repo import RepoMetadata


class SnapshotError(RuntimeError):
    """Levée quand un snapshot existe mais ne peut pas servir de point de reprise.

    Distincte de ``CommandError`` (``virsh`` a échoué) et de ``DomainNotFound``
    (la machine n'existe pas) : ici l'hyperviseur répond, la machine est là, et
    c'est **l'état du snapshot** qui interdit l'opération demandée. Les trois
    appellent des gestes différents, les confondre ferait écrire un message
    faux.
    """


class SnapshotBackend(Protocol):
    """Contrat à respecter par chaque module ``snapshot/<provider>.py``."""

    def create(
        self, repo_meta: RepoMetadata, hosts: list[str], name: str
    ) -> None: ...

    def revert(
        self, repo_meta: RepoMetadata, hosts: list[str], name: str
    ) -> None: ...

    def delete(
        self, repo_meta: RepoMetadata, hosts: list[str], name: str
    ) -> None: ...

    def purge(
        self, repo_meta: RepoMetadata, hosts: list[str]
    ) -> list[str]: ...

    def list_(
        self, repo_meta: RepoMetadata, host: str
    ) -> list[str]: ...


def _backend(repo_meta: RepoMetadata) -> SnapshotBackend:
    """Retourne le module snapshot correspondant au provider courant.

    Raises:
        NotImplementedError: si le provider n'a pas de backend snapshot.
    """
    provider = repo_meta.infra.require_provider()
    try:
        module = importlib.import_module(
            f"dsoxlab.infra.snapshot.{provider}"
        )
    except ImportError as exc:
        raise NotImplementedError(
            _("err_snapshot_provider_unsupported", provider=provider)
        ) from exc
    return module


def create(repo_meta: RepoMetadata, hosts: list[str], name: str) -> None:
    """Crée un snapshot ``name`` sur chaque host listé."""
    _backend(repo_meta).create(repo_meta, hosts, name)


def revert(repo_meta: RepoMetadata, hosts: list[str], name: str) -> None:
    """Restaure chaque host depuis son snapshot ``name``."""
    _backend(repo_meta).revert(repo_meta, hosts, name)


def delete(repo_meta: RepoMetadata, hosts: list[str], name: str) -> None:
    """Supprime le snapshot ``name`` sur chaque host."""
    _backend(repo_meta).delete(repo_meta, hosts, name)


def purge(repo_meta: RepoMetadata, hosts: list[str]) -> list[str]:
    """Retire tout snapshot et tout artefact de stockage laissé sur ces hosts.

    Returns:
        Les artefacts réellement retirés, pour que l'appelant les nomme.
    """
    return _backend(repo_meta).purge(repo_meta, hosts)


def list_(repo_meta: RepoMetadata, host: str) -> list[str]:
    """Retourne la liste des snapshots existants pour ``host``."""
    return _backend(repo_meta).list_(repo_meta, host)


def host_names(repo_meta: RepoMetadata) -> list[str]:
    """Helper : extrait la liste des FQDN depuis ``meta.yml: infra.hosts``."""
    return [h.name for h in repo_meta.infra.hosts]
