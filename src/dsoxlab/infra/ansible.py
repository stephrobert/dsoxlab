"""Pilotage d'Ansible depuis Python via ``ansible-runner``.

dsoxlab n'invoque **jamais** ``ansible-playbook`` en sous-processus.
La bibliothèque ``ansible-runner`` (officielle Red Hat, utilisée par
AAP et ansible-navigator) fournit une API Python typée avec retours
structurés (events JSON par tâche, stats agrégées).

Cette couche est strictement **agnostique du domaine** : elle reçoit
un chemin de playbook + un inventory dict, exécute, retourne un
``PlaybookResult`` enrichi. Ce sont les modules métier (runtimes/vm.py,
services/lab_service.py) qui appellent cette couche.

Le hook ``logging.captureWarnings(True)`` côté ansible-runner produit
beaucoup de bruit ; on filtre par défaut sauf en mode verbeux.
"""

from __future__ import annotations

import logging
import os
import tempfile
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class PlaybookResult:
    """Résultat structuré d'une exécution de playbook."""

    rc: int
    """Code de retour (0 = succès)."""

    status: str
    """``successful`` | ``failed`` | ``canceled`` | ``timeout`` | ``unknown``."""

    stats: dict[str, dict[str, int]] = field(default_factory=dict)
    """Stats agrégées par hôte : ``{ "ok": {host: n}, "changed": {...},
    "failed": {...}, "skipped": {...}, "unreachable": {...} }``."""

    stdout: str = ""
    """Sortie agrégée (utile pour debug)."""

    @property
    def ok(self) -> bool:
        return self.rc == 0 and self.status == "successful"

    @property
    def total_changed(self) -> int:
        return sum(self.stats.get("changed", {}).values())

    @property
    def total_failed(self) -> int:
        return sum(self.stats.get("failed", {}).values()) + sum(
            self.stats.get("unreachable", {}).values()
        )


class AnsibleNotInstalled(RuntimeError):
    """Levée si ansible-runner n'est pas disponible."""


def is_available() -> bool:
    """Retourne True si ``ansible-runner`` est importable et opérationnel."""
    try:
        import ansible_runner  # noqa: F401
    except ImportError:
        return False
    return True


def run_playbook(
    playbook_path: Path,
    inventory: dict[str, Any] | Path,
    *,
    extra_vars: dict[str, Any] | None = None,
    vault_password_file: Path | None = None,
    quiet: bool = True,
    timeout_s: int | None = None,
    private_data_dir: Path | None = None,
    on_event: "Callable[[dict[str, Any]], None] | None" = None,
) -> PlaybookResult:
    """Exécute un playbook via ansible-runner et retourne le résultat.

    Args:
        playbook_path: Chemin absolu vers le ``.yaml`` du playbook.
        inventory: Soit un dict (format standard Ansible :
            ``{"all": {"hosts": {fqdn: {ansible_host, ansible_user,
            ansible_ssh_private_key_file, ...}}}}``) ; soit un chemin
            vers un fichier inventory.
        extra_vars: ``-e`` Ansible.
        vault_password_file: Chemin vers ``.vault-pass`` (pour les
            playbooks chiffrés ansible-vault).
        quiet: Si True, supprime stdout d'ansible-runner.
        timeout_s: Timeout total en secondes (None = pas de limite).
        private_data_dir: Répertoire de travail d'ansible-runner (logs,
            artifacts). Si None, un tmpdir est créé et nettoyé.

    Returns:
        ``PlaybookResult`` (rc, status, stats, stdout).

    Raises:
        AnsibleNotInstalled: Si ``ansible-runner`` n'est pas importable.
        FileNotFoundError: Si le playbook n'existe pas.
    """
    if not is_available():
        raise AnsibleNotInstalled(
            "ansible-runner non installé. Lance : "
            "uv tool install --force --with ansible-runner dsoxlab "
            "ou : pipx inject dsoxlab ansible-runner"
        )

    if not playbook_path.is_file():
        raise FileNotFoundError(f"Playbook absent : {playbook_path}")

    import ansible_runner

    cmdline_parts: list[str] = []
    if vault_password_file is not None:
        cmdline_parts.append(f"--vault-password-file={vault_password_file}")
    cmdline = " ".join(cmdline_parts) if cmdline_parts else None

    # ansible-runner attend playbook == nom du fichier dans
    # private_data_dir/project/. On utilise le pattern roles_path absolu
    # pour rester portable depuis le dépôt fournisseur.
    project_dir = playbook_path.parent

    # Narrowing direct sur `private_data_dir` (et non via un booléen
    # intermédiaire) : c'est ce qui permet de prouver que le chemin n'est
    # plus None au moment du `private_data_dir / "project"` ci-dessous.
    tmpdir_obj: tempfile.TemporaryDirectory[str] | None = None
    if private_data_dir is None:
        tmpdir_obj = tempfile.TemporaryDirectory(prefix="dsoxlab-runner-")
        private_data_dir = Path(tmpdir_obj.name)

    try:
        # ansible-runner cherche le playbook dans private_data_dir/project.
        # On crée un lien symbolique vers le project_dir réel.
        project_link = private_data_dir / "project"
        if not project_link.exists():
            project_link.symlink_to(project_dir, target_is_directory=True)

        kwargs: dict[str, Any] = {}
        if on_event is not None:
            def _safe_handler(event: dict[str, Any]) -> bool:
                """ansible-runner event_handler : doit retourner True
                pour continuer (False arrête le run). On wrap le
                callback utilisateur pour ne pas tuer le playbook si
                la CLI plante."""
                try:
                    on_event(event)
                except Exception:  # noqa: BLE001
                    logger.exception("on_event callback failed")
                return True

            kwargs["event_handler"] = _safe_handler

        runner = ansible_runner.run(
            playbook=playbook_path.name,
            private_data_dir=str(private_data_dir),
            inventory=inventory if isinstance(inventory, dict) else str(inventory),
            extravars=extra_vars or {},
            cmdline=cmdline,
            quiet=quiet,
            timeout=timeout_s,
            envvars=_env_overrides(),
            **kwargs,
        )

        return PlaybookResult(
            rc=runner.rc if runner.rc is not None else -1,
            status=runner.status or "unknown",
            stats=runner.stats or {},
            stdout=_read_stdout(runner),
        )
    finally:
        if tmpdir_obj is not None:
            tmpdir_obj.cleanup()


def _env_overrides() -> dict[str, str]:
    """Variables d'env qu'on force pour cohérence des labs.

    - ``ANSIBLE_HOST_KEY_CHECKING=False`` : les VMs lab sont jetables, pas
      de prompt sur la clé host à chaque provision.
    - ``ANSIBLE_STDOUT_CALLBACK=default`` : sortie stable lisible.
    """
    overrides = {
        "ANSIBLE_HOST_KEY_CHECKING": "False",
        "ANSIBLE_STDOUT_CALLBACK": "default",
    }
    # Conserve les overrides déjà posés dans l'env utilisateur
    for key, value in os.environ.items():
        if key.startswith("ANSIBLE_"):
            overrides.setdefault(key, value)
    return overrides


def _read_stdout(runner: Any) -> str:
    """Récupère le stdout agrégé d'un runner ansible-runner.

    L'attribut ``stdout`` peut être un IO non encore consommé selon la
    version. On essaye plusieurs accès.
    """
    stdout_attr = getattr(runner, "stdout", None)
    if stdout_attr is None:
        return ""
    if hasattr(stdout_attr, "read"):
        try:
            return str(stdout_attr.read())
        except Exception:  # noqa: BLE001 — best-effort logging
            return ""
    return str(stdout_attr)
