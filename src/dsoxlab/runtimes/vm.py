"""VmRuntime — orchestre les playbooks Ansible des labs ``runtime: vm``.

Ce runtime est **agnostique du provider** d'infrastructure. Le provider
(kvm/aws/proxmox/...) est sélectionné au moment du provisionnement
(``dsoxlab provision``) ; ici on ne fait que cibler une **target** parmi
celles déclarées dans ``lab.yaml: runtime.targets[]``.

Contrat lab.yaml minimal pour ``runtime: vm`` ::

    runtime:
      type: vm
      targets:
        - { name: rhel,   host: alma-rhcsa-1.lab,  label_fr: "RHEL 10" }
        - { name: ubuntu, host: ubuntu-lfcs-1.lab, label_fr: "Ubuntu 24.04" }
      default: rhel              # cible si l'apprenant ne précise pas
      snapshot_required: false

Fichiers attendus à la racine du lab :

- ``setup.yaml``   — playbook qui pose l'état initial
- ``cleanup.yaml`` — playbook qui supprime tout

Convention impérative : les playbooks doivent cibler ``hosts: lab_target``
(le groupe Ansible synthétique injecté par dsoxlab avec le seul host
correspondant à la target choisie).
"""

from __future__ import annotations

import logging
import os
from typing import Any

from ..discovery.repo import find_meta_yml, read_repo_metadata
from ..models.repo import RepoMetadata
from ..infra import ansible as ansible_infra
from ..infra import snapshot as snapshot_infra
from ..infra.inventory import build_inventory, read_terraform_outputs
from ..models.lab import LabDefinition
from ..models.runtime import Target
from .base import BaseRuntime, EventCallback

logger = logging.getLogger(__name__)


class TargetNotResolved(RuntimeError):
    """Levée quand la target demandée n'existe pas ou que ``targets[]``
    est vide pour un lab ``runtime: vm``."""


class VmRuntime(BaseRuntime):
    """Runtime VM — invoque ``ansible-runner`` pour setup/cleanup.

    Sélection de la target (priorité décroissante) :

    1. Argument ``target_name`` (passé par la CLI via ``--target``).
    2. Variable d'env ``DSOXLAB_TARGET``.
    3. ``lab.runtime.default`` (si non vide).
    4. Première target déclarée dans ``lab.runtime.targets``.
    """

    def is_available(self) -> bool:
        return ansible_infra.is_available()

    def start(
        self,
        lab: LabDefinition,
        target_name: str | None = None,
        *,
        on_event: EventCallback | None = None,
    ) -> None:
        target = self._resolve_target(lab, target_name)
        repo_meta = self._repo_meta(lab)
        setup = lab.path / "setup.yaml"
        if not setup.is_file():
            raise FileNotFoundError(
                f"Le lab {lab.id} doit fournir setup.yaml à la racine "
                f"(contrat dsoxlab pour runtime: vm). Fichier attendu : {setup}"
            )

        if lab.runtime.snapshot_required:
            snap_name = f"pre-{lab.id}"
            try:
                snapshot_infra.create(repo_meta, [target.host], snap_name)
            except Exception as exc:  # noqa: BLE001
                logger.warning(
                    "Snapshot pré-setup non créé (%s). Le lab continue mais "
                    "le rollback ne sera pas disponible.", exc,
                )

        result = ansible_infra.run_playbook(
            playbook_path=setup,
            inventory=self._inventory(repo_meta, target),
            on_event=on_event,
        )
        if not result.ok:
            raise RuntimeError(
                f"setup.yaml a échoué pour {lab.id} sur target '{target.name}' "
                f"(rc={result.rc}, status={result.status}). Stats : {result.stats}"
            )

    def stop(self, lab: LabDefinition, target_name: str | None = None) -> None:
        """No-op : les VMs sont persistantes (gérées par dsoxlab destroy)."""
        del lab, target_name

    def reset(
        self,
        lab: LabDefinition,
        target_name: str | None = None,
        *,
        on_event: EventCallback | None = None,
    ) -> None:
        self.clean(lab, target_name, on_event=on_event)
        self.start(lab, target_name, on_event=on_event)

    def clean(
        self,
        lab: LabDefinition,
        target_name: str | None = None,
        *,
        on_event: EventCallback | None = None,
    ) -> None:
        target = self._resolve_target(lab, target_name)
        repo_meta = self._repo_meta(lab)
        cleanup = lab.path / "cleanup.yaml"
        if not cleanup.is_file():
            raise FileNotFoundError(
                f"Le lab {lab.id} doit fournir cleanup.yaml à la racine "
                f"(contrat dsoxlab pour runtime: vm). Fichier attendu : {cleanup}"
            )

        result = ansible_infra.run_playbook(
            playbook_path=cleanup,
            inventory=self._inventory(repo_meta, target),
            on_event=on_event,
        )
        if not result.ok:
            raise RuntimeError(
                f"cleanup.yaml a échoué pour {lab.id} sur target '{target.name}' "
                f"(rc={result.rc}, status={result.status})."
            )

    def status(self, lab: LabDefinition, target_name: str | None = None) -> str:
        del lab, target_name
        return "ready"

    def open_session(self, lab: LabDefinition) -> None:
        """Ouvre une session SSH interactive sur la target résolue.

        L'apprenant se retrouve directement loggé sur la VM cible
        (via bastion ProxyCommand si réseau privé) — il peut alors
        taper ``systemctl status demo-crashloop``, ``journalctl``,
        etc. comme s'il avait ssh manuellement.

        Bloquant : retour au shell dsoxlab quand l'apprenant tape
        ``exit``. Permet à ``dsoxlab run`` de continuer son flow
        (set_active_lab(None), message de fin).
        """
        import subprocess

        from ..infra.inventory import bastion_info, build_inventory, read_terraform_outputs

        target = self._resolve_target(lab, None)
        repo_meta = self._repo_meta(lab)
        tf_outputs = read_terraform_outputs(repo_meta)
        inventory = build_inventory(
            repo_meta,
            terraform_outputs=tf_outputs,
            target_fqdn=target.host,
        )
        host_vars = inventory["all"]["children"]["labenv"]["hosts"][target.host]
        ip = host_vars["ansible_host"]
        bastion = bastion_info(tf_outputs, repo_meta=repo_meta)
        ssh_key = repo_meta.path / "ssh" / "id_ed25519"

        cmd = [
            "ssh",
            # -F /dev/null : ignore la config SSH perso de l'apprenant
            # (~/.ssh/config) qui peut contenir un ProxyJump appliqué
            # par pattern d'IP (ex: "Host 10.*" → bastion tiers).
            "-F", "/dev/null",
            "-o", "StrictHostKeyChecking=no",
            "-o", "UserKnownHostsFile=/dev/null",
            "-i", str(ssh_key),
        ]
        if bastion:
            proxy_target = bastion["fqdn"] or bastion["public_ip"]
            cmd += [
                "-o",
                (
                    f"ProxyCommand=ssh -F /dev/null -W %h:%p "
                    f"-i {ssh_key} "
                    f"-o StrictHostKeyChecking=no "
                    f"-o UserKnownHostsFile=/dev/null "
                    f"{bastion['user']}@{proxy_target}"
                ),
            ]
        cmd.append(f"student@{ip}")
        # subprocess.call : on attend que l'apprenant tape exit.
        # Le flow dsoxlab run continue ensuite (cleanup contexte).
        subprocess.call(cmd)

    # ─── helpers ──────────────────────────────────────────────────────

    def _resolve_target(
        self, lab: LabDefinition, explicit_name: str | None
    ) -> Target:
        """Résout la target effective selon la priorité documentée.

        Priorité (décroissante) :

        1. ``explicit_name`` (passé par la CLI via ``--target``).
        2. Variable d'env ``DSOXLAB_TARGET``.
        3. ``ActiveContext.active_target`` lu depuis
           ``<repo>/.dsoxlab-context.json``.
        4. ``lab.runtime.default``.
        5. Première target déclarée.

        Raises:
            TargetNotResolved: si la liste ``runtime.targets`` est vide,
                ou si le nom résolu ne matche aucune target.
        """
        if not lab.runtime.targets:
            raise TargetNotResolved(
                f"Le lab {lab.id} (runtime: vm) doit déclarer au moins "
                f"une target dans runtime.targets[] de lab.yaml."
            )

        name = (
            explicit_name
            or os.environ.get("DSOXLAB_TARGET", "").strip()
            or self._target_from_context(lab)
            or None
        )
        target = lab.runtime.target(name)
        if target is None:
            available = ", ".join(t.name for t in lab.runtime.targets)
            raise TargetNotResolved(
                f"Target '{name}' inconnue pour le lab {lab.id}. "
                f"Targets disponibles : {available}"
            )
        return target

    @staticmethod
    def _target_from_context(lab: LabDefinition) -> str | None:
        """Lit ``ActiveContext.active_target`` depuis le repo du lab."""
        try:
            from ..config import read_context
            from ..discovery.repo import find_meta_yml

            meta_path = find_meta_yml(lab.path)
            if meta_path is None:
                return None
            ctx = read_context(meta_path.parent)
            return ctx.active_target or None
        except Exception:  # noqa: BLE001 — best-effort
            return None

    def _repo_meta(self, lab: LabDefinition) -> RepoMetadata:
        meta_path = find_meta_yml(lab.path)
        if meta_path is None:
            raise RuntimeError(
                f"Pas de meta.yml trouvé en remontant depuis {lab.path}. "
                f"dsoxlab ne peut pas dériver l'inventory."
            )
        meta = read_repo_metadata(meta_path.parent)
        if meta is None:
            raise RuntimeError(f"meta.yml invalide : {meta_path}")
        return meta

    def _inventory(
        self, repo_meta: RepoMetadata, target: Target
    ) -> dict[str, Any]:
        """Inventory filtré au seul host de la target choisie."""
        tf_outputs = read_terraform_outputs(repo_meta)
        return build_inventory(
            repo_meta,
            terraform_outputs=tf_outputs,
            target_fqdn=target.host,
        )
