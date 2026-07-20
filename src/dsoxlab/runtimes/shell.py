"""ShellRuntime — atelier shell-local 100 % déclaratif.

Pour les labs ``runtime: shell`` (ateliers de découverte du shell sur
le poste de l'apprenant), la préparation se déclare directement dans
``lab.yaml`` :

    runtime:
      type: shell
      workdir: challenge/work       # créé par dsoxlab run
      fixtures:                      # optionnel — copiés vers workdir
        - logs/auth.log
        - configs/sshd_config

`dsoxlab run` :

1. crée ``<lab>/<workdir>/`` (idempotent)
2. copie chaque ``<lab>/fixtures/<file>`` vers ``<lab>/<workdir>/<file>``

`dsoxlab clean` supprime ``<workdir>/``. Aucun script bash n'est invoqué
(décision 11.3 du REFACTORING-PLAN — zéro exception au déclaratif).
"""

from __future__ import annotations

import logging
import os
import shutil
from pathlib import Path

from ..models.lab import LabDefinition
from .base import BaseRuntime, EventCallback, SessionSpec

logger = logging.getLogger(__name__)


class ShellRuntime(BaseRuntime):
    """Runtime local 100 % déclaratif (workdir + fixtures).

    Aucune exécution de script bash. La préparation est limitée à
    create-directory + copy-fixtures, descriptible dans ``lab.yaml``.
    """

    def is_available(self) -> bool:
        return True

    def start(
        self,
        lab: LabDefinition,
        target_name: str | None = None,
        *,
        on_event: EventCallback | None = None,
    ) -> None:
        """Crée le ``workdir`` et copie les fixtures déclarées.

        ``target_name`` et ``on_event`` sont ignorés pour ce runtime
        (atelier shell-local, déclaratif pur : aucun event ansible-runner
        à remonter). Ils font partie du contrat ``BaseRuntime`` et doivent
        être acceptés, sinon tout appel de la CLI passant ``on_event``
        échoue en ``TypeError``.
        """
        del target_name, on_event
        workdir = self._workdir_path(lab)
        workdir.mkdir(parents=True, exist_ok=True)

        fixtures_root = lab.path / "fixtures"
        for rel in lab.runtime.fixtures:
            src = fixtures_root / rel
            if not src.is_file():
                logger.warning(
                    "Fixture déclarée mais introuvable : %s "
                    "(le lab devrait livrer ce fichier dans fixtures/)",
                    src,
                )
                continue
            dst = workdir / Path(rel).name
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dst)
            logger.info("fixture %s → %s", rel, dst)

    def session_spec(self, lab: LabDefinition) -> SessionSpec:
        """Un sous-shell dans ``<workdir>/``.

        Pose ``DSOXLAB_LAB_SESSION=<lab_id>`` dans l'env du sous-shell
        pour que les commandes lancées depuis ce shell (notamment
        ``dsoxlab submit``) sachent qu'elles tournent dans un sous-shell
        de session — utile pour adapter les CTA (ex. afficher "tape
        exit pour revenir") sans risque de fausse instruction quand
        l'apprenant exécute la commande depuis son shell parent.
        """
        return SessionSpec(
            command=[os.environ.get("SHELL", "bash")],
            cwd=self._workdir_path(lab),
            env={"DSOXLAB_LAB_SESSION": lab.id},
        )

    def stop(self, lab: LabDefinition, target_name: str | None = None) -> None:
        del lab, target_name

    def reset(
        self,
        lab: LabDefinition,
        target_name: str | None = None,
        *,
        on_event: EventCallback | None = None,
    ) -> None:
        del on_event
        self.clean(lab, target_name)
        self.start(lab, target_name)

    def clean(
        self,
        lab: LabDefinition,
        target_name: str | None = None,
        *,
        on_event: EventCallback | None = None,
    ) -> None:
        del target_name, on_event
        workdir = self._workdir_path(lab)
        if workdir.exists():
            shutil.rmtree(workdir)
            logger.info("workdir supprimé : %s", workdir)

    def status(self, lab: LabDefinition, target_name: str | None = None) -> str:
        del target_name
        return "ready" if self._workdir_path(lab).is_dir() else "stopped"

    # ─── helpers ──────────────────────────────────────────────────────

    def _workdir_path(self, lab: LabDefinition) -> Path:
        """Résout ``<lab>/<runtime.workdir>``."""
        return (lab.path / lab.runtime.workdir).resolve()
