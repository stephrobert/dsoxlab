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

``snapshot_required`` engage l'outil, il ne l'informe pas :

- ``run`` prend un point de reprise du **disque** avant le ``setup.yaml``, et
  **échoue** s'il n'y arrive pas — un lab qui réclame un filet ne démarre pas
  sans lui ;
- ``reset`` ramène la machine à ce point plutôt que de rejouer le
  ``cleanup.yaml`` ;
- ``clean`` retire le point de reprise, et avec lui le fichier de recouvrement
  qu'il avait créé.

L'état **mémoire** n'est pas capturé : la reprise repart d'un disque cohérent,
pas de la seconde d'avant.

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
from ..i18n import _
from ..infra import ansible as ansible_infra
from ..infra import snapshot as snapshot_infra
from ..infra.inventory import build_inventory, read_terraform_outputs
from ..models.lab import LabDefinition
from ..models.repo import RepoMetadata
from ..models.runtime import Target
from .base import BaseRuntime, EventCallback, SessionSpec

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
                _("err_vm_setup_missing", lab_id=lab.id, path=setup)
            )

        if lab.runtime.snapshot_required:
            # « required » veut dire required. Ce bloc avalait l'échec en
            # `logger.warning`, et le journal n'est même pas configuré dans ce
            # paquet : le lab démarrait sans le filet qu'il réclame, `run`
            # sortait en 0, et l'apprenant l'apprenait au moment d'en avoir
            # besoin. C'est ce silence qui a laissé la fonctionnalité cassée
            # sans que personne ne le voie. Un lab qui tolère l'absence de
            # filet a le droit de le déclarer : c'est snapshot_required: false.
            try:
                snapshot_infra.create(repo_meta, [target.host], self._snap_name(lab))
            except Exception as exc:  # on ne filtre pas : tout échec du filet est un échec du lab
                raise RuntimeError(_(
                    "err_vm_snapshot_required",
                    lab_id=lab.id, host=target.host, error=str(exc),
                )) from exc

        result = ansible_infra.run_playbook(
            playbook_path=setup,
            inventory=self._inventory(repo_meta, target),
            on_event=on_event,
        )
        if not result.ok:
            raise RuntimeError(_(
                "err_vm_setup_failed",
                lab_id=lab.id, target=target.name, rc=result.rc,
                status=result.status, stats=result.stats,
            ))

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
        """Remet le lab à son état de départ.

        Un lab qui déclare ``snapshot_required: true`` est **ramené à son point
        de reprise** plutôt que nettoyé par son ``cleanup.yaml`` : c'est là que
        le filet sert, et c'est ce qui donne enfin un effet observable à ce
        champ du contrat. Le point de reprise ayant été pris **avant** le
        ``setup.yaml``, il faut rejouer celui-ci derrière.

        L'échec du retour arrière n'est pas rattrapé par un ``cleanup.yaml`` de
        repli : ce serait remplacer une garantie par une approximation sans le
        dire, exactement le défaut que ce runtime vient de solder.
        """
        if lab.runtime.snapshot_required:
            target = self._resolve_target(lab, target_name)
            repo_meta = self._repo_meta(lab)
            snapshot_infra.revert(repo_meta, [target.host], self._snap_name(lab))
            self.start(lab, target_name, on_event=on_event)
            return
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
                _("err_vm_cleanup_missing", lab_id=lab.id, path=cleanup)
            )

        result = ansible_infra.run_playbook(
            playbook_path=cleanup,
            inventory=self._inventory(repo_meta, target),
            on_event=on_event,
        )
        if not result.ok:
            raise RuntimeError(_(
                "err_vm_cleanup_failed",
                lab_id=lab.id, target=target.name, rc=result.rc,
                status=result.status,
            ))

        # Le point de reprise a fait son temps. Le laisser laisserait un
        # fichier de recouvrement que Terraform ne connaît pas, et qui
        # survivrait à la machine — le cousin des domaines orphelins de #107.
        # Best-effort : un nettoyage ne doit pas échouer sur ce qui a déjà
        # disparu, mais il dit ce qu'il n'a pas su retirer.
        if lab.runtime.snapshot_required:
            try:
                snapshot_infra.delete(repo_meta, [target.host], self._snap_name(lab))
            except Exception as exc:  # noqa: BLE001 — nettoyage best-effort
                logger.warning(
                    "Point de reprise %s non retiré : %s", self._snap_name(lab), exc
                )

    def status(self, lab: LabDefinition, target_name: str | None = None) -> str:
        del lab, target_name
        return "ready"

    def session_spec(self, lab: LabDefinition) -> SessionSpec:
        """La session SSH interactive sur la target résolue.

        L'apprenant se retrouve directement loggé sur la VM cible
        (via bastion ProxyCommand si réseau privé) — il peut alors
        taper ``systemctl status demo-crashloop``, ``journalctl``,
        etc. comme s'il avait ssh manuellement.

        Le compte de connexion est lu depuis l'inventaire
        (``ansible_user``) et non codé en dur : c'est le même compte que
        celui du ``ssh_config`` généré, donc ``dsoxlab ssh`` et un
        ``ssh -F <ssh_config>`` mènent au même endroit. Un lab qui
        restreint ``AllowUsers`` au compte de l'automatisation ne
        verrouille donc pas cette session.
        """
        from ..infra.inventory import bastion_info, build_inventory, read_terraform_outputs

        repo_meta = self._repo_meta(lab)

        if lab.runtime.session == "local":
            # Lab piloté depuis le poste : les hôtes restent provisionnés et
            # travaillés par le setup.yaml, mais l'apprenant écrit son code ici,
            # et ses commandes visent les cibles depuis la racine du dépôt —
            # c'est de là que les chemins des énoncés sont relatifs.
            return SessionSpec(
                command=[os.environ.get("SHELL", "bash")],
                cwd=repo_meta.path,
                env={"DSOXLAB_LAB_SESSION": lab.id},
            )

        target = self._resolve_target(lab, None)
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
        cmd.append(f"{host_vars.get('ansible_user', 'ansible')}@{ip}")
        return SessionSpec(command=cmd)

    # ─── helpers ──────────────────────────────────────────────────────

    @staticmethod
    def _snap_name(lab: LabDefinition) -> str:
        """Le nom du point de reprise du lab, calculé en **un seul endroit**.

        Il était recomposé sur place à chaque usage, ce qui ne se voyait pas
        tant qu'un seul usage existait ; à trois, une divergence d'un caractère
        aurait fait supprimer un snapshot qui n'existe pas et laissé le vrai
        derrière.
        """
        return f"pre-{lab.id}"

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
            raise TargetNotResolved(_("err_vm_no_target", lab_id=lab.id))

        name = (
            explicit_name
            or os.environ.get("DSOXLAB_TARGET", "").strip()
            or self._target_from_context(lab)
            or None
        )
        target = lab.runtime.target(name)
        if target is None:
            available = ", ".join(t.name for t in lab.runtime.targets)
            raise TargetNotResolved(_(
                "err_vm_target_unknown",
                name=name, lab_id=lab.id, available=available,
            ))
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
            raise RuntimeError(_("err_vm_no_meta", path=lab.path))
        meta = read_repo_metadata(meta_path.parent)
        if meta is None:
            raise RuntimeError(_("err_vm_meta_invalid", path=meta_path))
        return meta

    def _inventory(
        self, repo_meta: RepoMetadata, target: Target
    ) -> dict[str, Any]:
        """Inventory du lab : ``lab_target`` = host primaire, plus un groupe
        ``lab_<role>`` par rôle déclaré (labs multi-hôtes serveur/client).

        Le groupe ``labenv`` contient de toute façon tous les hôtes
        provisionnés ; les groupes synthétiques ne font que nommer les rôles
        pour que les playbooks n'aient pas à coder un FQDN en dur.
        """
        tf_outputs = read_terraform_outputs(repo_meta)
        return build_inventory(
            repo_meta,
            terraform_outputs=tf_outputs,
            target_fqdn=target.host,
            roles=target.roles or None,
        )
