"""RuntimeManager — sélectionne et instancie le bon runtime."""

from __future__ import annotations

from ..models.lab import LabDefinition
from ..models.runtime import RuntimeType
from .base import BaseRuntime
from .shell import ShellRuntime
from .vm import VmRuntime


class RuntimeManager:
    """Retourne le runtime adapté à un lab et vérifie sa disponibilité."""

    def get(self, lab: LabDefinition) -> BaseRuntime:
        runtime = self._build(lab)
        if not runtime.is_available():
            raise RuntimeError(
                f"Le runtime '{lab.runtime.type.value}' n'est pas "
                f"disponible sur cette machine. Installe les "
                f"dépendances (`dsoxlab instructor bootstrap`) ou "
                f"utilise un lab compatible avec un autre runtime."
            )
        return runtime

    def _build(self, lab: LabDefinition) -> BaseRuntime:
        # ``vm`` est la cible. ``kvm`` et ``incus`` sont des alias
        # historiques tolérés ; ils sont traités comme ``vm`` (la
        # discrimination du provider se fait via meta.yml: infra.provider).
        rt_type = lab.runtime.type
        if rt_type == RuntimeType.SHELL:
            return ShellRuntime()
        if rt_type in (RuntimeType.VM, RuntimeType.KVM, RuntimeType.INCUS):
            return VmRuntime()
        raise ValueError(f"RuntimeType inconnu : {rt_type}")
