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
2. copie chaque ``<lab>/fixtures/<file>`` vers ``<lab>/<workdir>/<file>``, en
   **préservant le chemin déclaré** : ``modules/stockage/main.tf`` arrive en
   ``<workdir>/modules/stockage/main.tf``, et les répertoires intermédiaires
   sont créés. Un lab Terraform peut donc livrer un module local sans que son
   ``main.tf`` écrase celui de la racine. Un chemin absolu ou contenant ``..``
   est refusé : une fixture ne sort jamais du workdir.

`dsoxlab clean` supprime ``<workdir>/``. Aucun script bash n'est invoqué
(décision 11.3 du REFACTORING-PLAN — zéro exception au déclaratif).

PRÉPARER UN TERRAIN (issue #298). Un lab shell **peut** porter ``setup.yaml``
et ``cleanup.yaml`` à sa racine : les mêmes playbooks Ansible qu'un lab
``vm``, joués sur ``localhost`` en connexion locale par le même
ansible-runner. C'est ce qui permet à une épreuve de monter des machines, un
stockage partagé ou une panne tirée au hasard avant que l'apprenant commence,
sans renoncer au déclaratif : un playbook, pas un script. ``run`` le joue après
les fixtures, ``clean`` joue ``cleanup.yaml`` avant d'effacer le workdir, et
``reset`` enchaîne les deux. Les playbooks reçoivent ``lab_id``,
``lab_workdir`` et ``lab_state_dir`` (voir ``lab_state.repertoire_etat``). Un
lab shell qui n'en porte pas se comporte exactement comme avant.
"""

from __future__ import annotations

import json
import logging
import os
import re
import shutil
import sys
from pathlib import Path

from ..discovery.repo import find_meta_yml
from ..i18n import _
from ..infra import ansible as ansible_infra
from ..models.lab import LabDefinition
from .base import BaseRuntime, EventCallback, SessionSpec

logger = logging.getLogger(__name__)


def cause_d_echec(sortie: str) -> str:
    """La tâche qui a échoué et son message, extraits de la sortie d'Ansible.

    Sans eux, « setup.yaml a échoué (rc=2) » laisse l'auteur comme l'apprenant
    rejouer le playbook à la main pour savoir ce qui s'est passé : c'est ce
    qu'a coûté la première préparation d'épreuve (issue #298). Rend une chaîne
    vide si la sortie ne nomme aucun échec, jamais une supposition.
    """
    fatal = None
    for m in re.finditer(r"^fatal: \[[^\]]+\]: [A-Z]+! => (.*)$", sortie, re.MULTILINE):
        fatal = m
    if fatal is None:
        return ""
    taches = re.findall(r"^TASK \[(.+?)\]", sortie[: fatal.start()], re.MULTILINE)
    message = fatal.group(1).strip()
    try:
        donnees = json.loads(message)
        message = str(donnees.get("msg") or donnees.get("stderr") or message)
    except ValueError:
        pass
    tache = taches[-1] if taches else "?"
    return f"\n  {_('shell_playbook_task')} : {tache}\n  {message[:600]}"


class FixtureError(RuntimeError):
    """Une fixture déclarée n'a pas pu être copiée : le lab serait injouable.

    Hérite de ``RuntimeError`` parce que la CLI en attrape déjà un autour de
    ``run`` : le message, déjà traduit, s'affiche et la commande sort en 2.
    """


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
        """Crée le ``workdir``, copie les fixtures déclarées, joue ``setup.yaml``.

        ``target_name`` est ignoré pour ce runtime (atelier shell-local). Il
        fait partie du contrat ``BaseRuntime`` et doit être accepté, sinon tout
        appel de la CLI le passant échoue en ``TypeError``. ``on_event`` ne
        sert que si le lab porte un ``setup.yaml`` (#298).
        """
        del target_name
        workdir = self._workdir_path(lab)
        workdir.mkdir(parents=True, exist_ok=True)

        fixtures_root = lab.path / "fixtures"
        # Deux passes. La première refuse, la seconde copie : un `workdir`
        # à moitié rempli est pire qu'un refus, parce qu'il a l'air de marcher.
        # Les fautes sont TOUTES collectées avant de lever — un auteur corrige
        # en une passe plutôt qu'en autant de `run` qu'il a de fixtures.
        a_copier: list[tuple[Path, Path]] = []
        fautes: list[str] = []
        for rel in lab.runtime.fixtures:
            chemin = Path(rel)
            if chemin.is_absolute() or ".." in chemin.parts:
                fautes.append(_("fixture_hors_workdir", fixture=rel))
                continue
            src = fixtures_root / chemin
            if not src.is_file():
                fautes.append(_("fixture_introuvable", fixture=rel))
                continue
            a_copier.append((src, workdir / chemin))

        if fautes:
            # Un `logger.warning` laissait `run` sortir en 0 sur un workdir vide,
            # et l'apprenant sans rien à faire. Le lab est cassé : on le dit.
            raise FixtureError(
                _("fixture_lab_injouable", lab=lab.id, count=len(fautes))
                + "\n  - " + "\n  - ".join(fautes)
            )

        for src, dst in a_copier:
            # Le chemin déclaré est PRÉSERVÉ : `modules/stockage/main.tf` arrive
            # en `<workdir>/modules/stockage/main.tf`. Aplatir sur le nom de
            # base rendait impossible tout lab à modules (deux `main.tf` dans
            # l'arborescence s'écrasaient l'un l'autre).
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dst)
            logger.info("fixture %s -> %s", src.name, dst)

        # Après les fixtures : le playbook peut s'appuyer sur ce qu'elles posent.
        self._jouer(lab, "setup.yaml", on_event)

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
        self.clean(lab, target_name, on_event=on_event)
        self.start(lab, target_name, on_event=on_event)

    def clean(
        self,
        lab: LabDefinition,
        target_name: str | None = None,
        *,
        on_event: EventCallback | None = None,
    ) -> None:
        del target_name
        # Avant d'effacer le workdir : le nettoyage peut avoir besoin de ce qui
        # s'y trouve (un state Terraform, par exemple) pour défaire le terrain.
        self._jouer(lab, "cleanup.yaml", on_event)
        workdir = self._workdir_path(lab)
        if workdir.exists():
            shutil.rmtree(workdir)
            logger.info("workdir removed: %s", workdir)

    def status(self, lab: LabDefinition, target_name: str | None = None) -> str:
        del target_name
        return "ready" if self._workdir_path(lab).is_dir() else "stopped"

    # ─── helpers ──────────────────────────────────────────────────────

    def _jouer(self, lab: LabDefinition, nom: str, on_event: EventCallback | None) -> None:
        """Joue ``<lab>/<nom>`` sur localhost s'il existe, sinon ne fait rien.

        Un échec lève ``RuntimeError`` : la CLI l'attrape déjà autour de
        ``run``, affiche le message et sort en 2, sans ouvrir de session sur un
        terrain à moitié préparé.
        """
        playbook = lab.path / nom
        if not playbook.is_file():
            return
        # Import au moment de l'appel : `services` importe déjà les runtimes,
        # un import de module ferait un cycle à la première importation.
        from ..services.lab_state import repertoire_etat

        meta = find_meta_yml(lab.path)
        racine = meta.parent if meta else lab.path.parent
        etat = repertoire_etat(racine, lab.id)
        etat.mkdir(parents=True, exist_ok=True)
        resultat = ansible_infra.run_playbook(
            playbook_path=playbook,
            inventory={"all": {"hosts": {"localhost": {
                "ansible_connection": "local",
                # L'interpréteur de dsoxlab lui-même : il existe toujours, là
                # où une découverte automatique pourrait en choisir un autre.
                "ansible_python_interpreter": sys.executable,
            }}}},
            extra_vars={
                "lab_id": lab.id,
                "lab_workdir": str(self._workdir_path(lab)),
                "lab_state_dir": str(etat),
            },
            on_event=on_event,
        )
        if not resultat.ok:
            raise RuntimeError(_(
                "err_shell_playbook_failed",
                lab_id=lab.id, playbook=nom, rc=resultat.rc, status=resultat.status,
            ) + cause_d_echec(resultat.stdout))

    def _workdir_path(self, lab: LabDefinition) -> Path:
        """Résout ``<lab>/<runtime.workdir>``."""
        return (lab.path / lab.runtime.workdir).resolve()
