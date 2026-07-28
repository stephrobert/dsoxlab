"""Gestion des services conteneurisés déclarés par un lab.

Certains labs ``shell`` ciblent une API que le poste n'héberge pas (un émulateur
de cloud, une base de données, un registre). Le lab la déclare dans
``runtime.services`` (voir :class:`dsoxlab.models.runtime.Service`), et ce module
démarre le conteneur avant ``run``/``check`` et l'arrête à ``destroy``/``clean``.

Un conteneur debout n'est pas toujours un service utilisable : une base veut son
schéma, un coffre ses secrets. ``post_start`` joue ces commandes dans le
conteneur une fois le service prêt, ce qui évite au lab de fournir un script
bash d'initialisation que l'apprenant devrait penser à lancer.

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


def _wait_exec(name: str, argv: list[str], timeout: int) -> bool:
    """Rejoue une sonde DANS le conteneur jusqu'à ce qu'elle réussisse.

    C'est le seul signal fiable de disponibilité quand le port est publié :
    ``_wait_tcp`` interroge alors le proxy de Docker, qui accepte les connexions
    dès le ``run``, avant que le service écoute.
    """
    deadline = time.monotonic() + timeout
    while True:
        if run_command(["docker", "exec", name, *argv], check=False, timeout=30).ok:
            return True
        if time.monotonic() >= deadline:
            return False
        time.sleep(1)


def _wait_ready(service: Service, name: str) -> None:
    """Attend que le service réponde vraiment, puis rend la main.

    Deux étages complémentaires : ``ready_tcp`` élimine le conteneur mort-né
    sans rien exiger de l'image, ``ready_exec`` prouve que le service répond.
    """
    if service.ready_tcp and not _wait_tcp(service.ready_tcp, service.ready_timeout):
        raise ServiceError(
            f"Le service '{service.name}' n'a pas ouvert le port "
            f"{service.ready_tcp} en {service.ready_timeout}s."
        )
    if service.ready_exec and not _wait_exec(name, service.ready_exec, service.ready_timeout):
        raise ServiceError(
            f"Le service '{service.name}' n'a jamais répondu à « "
            f"{' '.join(service.ready_exec)} » en {service.ready_timeout}s."
        )


def _run_post_start(service: Service, name: str) -> None:
    """Joue les commandes d'initialisation DANS le conteneur, une fois prêt.

    Après ``ready_tcp``, jamais avant : un port qui accepte une connexion ne
    garantit pas un service qui répond, et une initialisation jouée trop tôt
    échoue de façon intermittente — le pire des symptômes à diagnostiquer.

    Sans shell (``docker exec`` reçoit l'argv tel quel), donc pas d'expansion ni
    de redirection : ce que le lab déclare est ce qui s'exécute.
    """
    for argv in service.post_start:
        res = run_command(["docker", "exec", name, *argv], check=False, timeout=120)
        if not res.ok:
            raise ServiceError(
                f"L'initialisation du service '{service.name}' a échoué sur "
                f"« {' '.join(argv)} » :\n{(res.stderr or res.stdout).strip()}"
            )


def start(service: Service, repo_id: str) -> str:
    """Démarre (ou réutilise) le conteneur d'un service et attend sa disponibilité.

    Idempotent : si le conteneur tourne déjà, on ne le recrée pas. S'il existe
    mais est arrêté, on le retire d'abord. Retourne le nom du conteneur.

    ``post_start`` est rejoué dans les deux cas, y compris sur un conteneur
    réutilisé : c'est ce qui rend l'état de départ identique d'un lab à l'autre,
    quel que soit ce que l'exercice précédent a laissé derrière lui.

    Raises:
        ServiceError: Docker indisponible, échec du ``run``, service jamais
            prêt, ou commande ``post_start`` en échec.
    """
    name = container_name(repo_id, service)

    if _is_running(name):
        _wait_ready(service, name)
        _run_post_start(service, name)
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

    _wait_ready(service, name)
    _run_post_start(service, name)
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
