"""Interface abstraite commune à tous les runtimes."""

from __future__ import annotations

import os
import shlex
import subprocess
from abc import ABC, abstractmethod
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from ..models.lab import LabDefinition

EventCallback = Callable[[dict[str, Any]], None]


@dataclass(frozen=True)
class SessionSpec:
    """Comment ouvrir la session interactive d'un lab, sans l'ouvrir.

    Décrire la session au lieu de l'exécuter sert deux usages que
    ``subprocess.call`` rendait impossibles :

    - **montrer la commande** plutôt que de la lancer, pour que l'apprenant la
      tape lui-même. Le jour de l'examen il n'y aura pas de raccourci : voir la
      commande à chaque fois vaut mieux que la voir exécutée à sa place ;
    - laisser une autre interface (TUI) décider du mode d'attachement, puisque
      ces commandes prennent le terminal courant.

    ``env`` ne porte que les variables à AJOUTER à l'environnement courant, pas
    un environnement complet : un sous-shell privé de ``PATH`` serait inutile.
    """

    command: list[str]
    cwd: Path | None = None
    env: dict[str, str] = field(default_factory=dict)

    def display(self) -> str:
        """La commande telle qu'un apprenant la taperait, quoting compris."""
        return shlex.join(self.command)


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

    def session_spec(self, lab: LabDefinition) -> SessionSpec | None:
        """Décrit la session interactive de ce lab, sans l'ouvrir.

        Retourne None quand le runtime n'en propose pas. Un runtime concret n'a
        que cette méthode à implémenter : l'exécution est commune, cf.
        ``open_session``.
        """
        del lab
        return None

    def open_session(self, lab: LabDefinition) -> None:
        """Ouvre la session interactive et rend la main quand elle se termine.

        Bloquant, et prend le terminal courant : c'est voulu pour la CLI, mais
        c'est aussi pourquoi ``session_spec`` existe. Une interface qui ne peut
        pas céder son TTY doit décrire la session plutôt que l'ouvrir.
        """
        spec = self.session_spec(lab)
        if spec is None:
            return
        if spec.cwd is not None:
            spec.cwd.mkdir(parents=True, exist_ok=True)
        subprocess.call(
            spec.command,
            cwd=spec.cwd,
            env={**os.environ, **spec.env} if spec.env else None,
        )
