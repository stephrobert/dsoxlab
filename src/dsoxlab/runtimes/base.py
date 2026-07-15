"""Interface abstraite commune à tous les runtimes."""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Callable
from typing import Any

from ..models.lab import LabDefinition

EventCallback = Callable[[dict[str, Any]], None]


class BaseRuntime(ABC):
    """Contrat commun pour ShellRuntime et VmRuntime.

    Le paramètre ``target_name`` est utilisé uniquement par
    ``VmRuntime`` pour sélectionner une cible dans la liste
    ``runtime.targets[]``. Il est ignoré par ``ShellRuntime``.

    ``on_event`` permet à la CLI de recevoir les events
    ansible-runner pour alimenter une progress bar (cf. dsoxlab run).
    Ignoré par ShellRuntime (déclaratif pur, pas de playbook Ansible).
    """

    @abstractmethod
    def start(
        self,
        lab: LabDefinition,
        target_name: str | None = None,
        *,
        on_event: EventCallback | None = None,
    ) -> None:
        """Prépare et démarre l'environnement du lab."""

    @abstractmethod
    def stop(self, lab: LabDefinition, target_name: str | None = None) -> None:
        """Arrête proprement l'environnement."""

    @abstractmethod
    def reset(
        self,
        lab: LabDefinition,
        target_name: str | None = None,
        *,
        on_event: EventCallback | None = None,
    ) -> None:
        """Remet le lab à l'état initial."""

    @abstractmethod
    def clean(
        self,
        lab: LabDefinition,
        target_name: str | None = None,
        *,
        on_event: EventCallback | None = None,
    ) -> None:
        """Supprime toutes les ressources créées par ce lab."""

    @abstractmethod
    def status(self, lab: LabDefinition, target_name: str | None = None) -> str:
        """Retourne l'état courant de l'environnement."""

    @abstractmethod
    def is_available(self) -> bool:
        """Retourne True si ce runtime est utilisable sur la machine courante."""

    def open_session(self, lab: LabDefinition) -> None:
        """Ouvre une session interactive dans le répertoire du lab."""
