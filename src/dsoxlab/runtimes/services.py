"""Gestion des services conteneurisés déclarés par un lab.

Certains labs ``shell`` ciblent une API que le poste n'héberge pas (un émulateur
de cloud, une base de données, un registre). Le lab la déclare dans
``runtime.services`` (voir :class:`dsoxlab.models.runtime.Service`), et ce module
démarre le conteneur avant ``run``/``check`` et l'arrête à ``destroy``/``clean``.

**dsoxlab reste agnostique.** Ce module lance **l'image que le lab déclare**, sur
les ports que le lab déclare, et ne connaît ni le cloud, ni le produit émulé.
Aucune chaîne « aws », « floci » ou autre n'apparaît ici : toute la spécificité
vit dans le ``lab.yaml`` du dépôt fournisseur.

Le moteur de conteneurs est **Docker** (le ``docker`` du PATH). Chaque conteneur
est nommé ``dsoxlab-<repo_id>-<service>`` pour éviter les collisions entre dépôts.
"""

from __future__ import annotations

import re
import socket
import time
from dataclasses import dataclass

from ..models.runtime import Service
from ..utils.shell import CommandError, run_command


class ServiceError(RuntimeError):
    """Un service n'a pas pu démarrer ou n'est jamais devenu disponible."""


@dataclass
class ServiceStatus:
    """État observé d'un service (pour ``dsoxlab status``)."""

    name: str
    container: str
    running: bool
    detail: str = ""


_NAME_SAFE = re.compile(r"[^a-zA-Z0-9_.-]")


def container_name(repo_id: str, service: Service) -> str:
    """Nom de conteneur namespacé, sûr pour Docker."""
    slug = _NAME_SAFE.sub("-", f"{repo_id}-{service.name}")
    return f"dsoxlab-{slug}"


def docker_available() -> bool:
    """True si le CLI ``docker`` répond (moteur joignable)."""
    try:
        return run_command(["docker", "version", "--format", "{{.Server.Version}}"],
                           check=False, timeout=15).ok
    except CommandError:
        return False


def _is_running(name: str) -> bool:
    res = run_command(
        ["docker", "inspect", "-f", "{{.State.Running}}", name],
        check=False, timeout=15,
    )
    return res.ok and res.stdout.strip() == "true"


def _exists(name: str) -> bool:
    return run_command(["docker", "inspect", name], check=False, timeout=15).ok


def _wait_tcp(port: int, timeout: int) -> bool:
    """Sonde ``localhost:port`` jusqu'à acceptation d'une connexion, ou timeout."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=2):
                return True
        except OSError:
            time.sleep(1)
    return False


def start(service: Service, repo_id: str) -> str:
    """Démarre (ou réutilise) le conteneur d'un service et attend sa disponibilité.

    Idempotent : si le conteneur tourne déjà, on ne le recrée pas. S'il existe
    mais est arrêté, on le retire d'abord. Retourne le nom du conteneur.

    Raises:
        ServiceError: Docker indisponible, échec du ``run``, ou service jamais prêt.
    """
    name = container_name(repo_id, service)

    if _is_running(name):
        if service.ready_tcp and not _wait_tcp(service.ready_tcp, service.ready_timeout):
            raise ServiceError(
                f"Le service '{service.name}' tourne mais son port "
                f"{service.ready_tcp} ne répond pas."
            )
        return name

    if _exists(name):
        run_command(["docker", "rm", "-f", name], check=False, timeout=30)

    cmd = ["docker", "run", "-d", "--name", name]
    for mapping in service.ports:
        cmd += ["-p", mapping]
    for key, value in service.env.items():
        cmd += ["-e", f"{key}={value}"]
    cmd += list(service.run_args)
    cmd.append(service.image)

    res = run_command(cmd, check=False, timeout=180)
    if not res.ok:
        raise ServiceError(
            f"Le démarrage du service '{service.name}' a échoué :\n{res.stderr.strip()}"
        )

    if service.ready_tcp and not _wait_tcp(service.ready_tcp, service.ready_timeout):
        raise ServiceError(
            f"Le service '{service.name}' n'a pas ouvert le port "
            f"{service.ready_tcp} en {service.ready_timeout}s."
        )
    return name


def stop(service: Service, repo_id: str) -> bool:
    """Arrête et retire le conteneur d'un service. True s'il existait."""
    name = container_name(repo_id, service)
    if not _exists(name):
        return False
    run_command(["docker", "rm", "-f", name], check=False, timeout=30)
    return True


def status(service: Service, repo_id: str) -> ServiceStatus:
    """État observé d'un service, sans le démarrer ni l'arrêter."""
    name = container_name(repo_id, service)
    if not _exists(name):
        return ServiceStatus(name=service.name, container=name, running=False, detail="absent")
    running = _is_running(name)
    return ServiceStatus(
        name=service.name, container=name, running=running,
        detail="running" if running else "stopped",
    )
