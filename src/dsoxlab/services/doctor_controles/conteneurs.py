"""Docker, requis dès qu'un lab déclare ``runtime.services``.

Extrait de ``services/doctor.py`` (issue #199), sans changement de
comportement. Voir ce module pour les principes du diagnostic.
"""

from __future__ import annotations

import shutil

from ...i18n import _
from ...models import LabDefinition
from .modele import STATE_UNKNOWN, Check, _check, _doctor


def uses_services(labs: list[LabDefinition]) -> bool:
    """Ce dépôt a-t-il au moins un lab qui déclare des conteneurs ?

    Lit le contrat, et rien d'autre : le moteur ne sait pas quelles images un
    catalogue déclare, et n'a pas à le savoir.
    """
    return any(lab.runtime.services for lab in labs)


def _check_docker() -> Check:
    """Un lab qui déclare ``runtime.services`` ne démarre pas sans moteur.

    Trois situations, et elles appellent trois gestes différents : le binaire
    n'est pas là (installer), il est là mais le démon ne répond pas (démarrer
    le service, ou se mettre dans le groupe), ou la sonde elle-même n'aboutit
    pas — auquel cas on ne sait pas, et on le dit plutôt que de trancher.
    """
    if shutil.which("docker") is None:
        return _check(
            "docker", False, _("detail_docker_missing"),
            hint="https://docs.docker.com/engine/install/",
        )
    result = _doctor()._sonder(["docker", "version", "--format", "{{.Server.Version}}"], delai=15)
    if result is None:
        return _check("docker", False, _("detail_docker_muet"), forced_state=STATE_UNKNOWN)
    if result.returncode != 0:
        # Le cas courant : le client répond, le démon non. Le message doit
        # nommer le démon, sinon on cherche un paquet déjà installé.
        detail = (result.stderr or result.stdout).strip().splitlines()
        return _check(
            "docker", False,
            detail[-1] if detail else _("detail_docker_daemon"),
            hint="https://docs.docker.com/engine/install/linux-postinstall/",
        )
    return _check("docker", True, result.stdout.strip() or "ok")
