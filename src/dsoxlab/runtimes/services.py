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

import hashlib
import json
import re
import socket
import time
from collections.abc import Callable
from dataclasses import dataclass

from ..i18n import _
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


def network_name(repo_id: str) -> str:
    """Réseau partagé par les services d'un même dépôt."""
    return f"dsoxlab-{_NAME_SAFE.sub('-', repo_id)}"


def _ensure_network(name: str) -> None:
    """Crée le réseau s'il n'existe pas. Idempotent.

    Un lab a souvent besoin de plusieurs conteneurs qui se parlent — une
    application et sa base. Sur le bridge par défaut de Docker, ils n'ont
    aucune résolution par nom : l'application ne peut joindre sa base que par
    une IP qu'on ne connaît pas d'avance. Un réseau *user-defined* apporte le
    DNS interne, et c'est la seule façon d'écrire `DB_HOST: db` dans un lab.
    """
    if run_command(["docker", "network", "inspect", name],
                   check=False, timeout=15).ok:
        return
    res = run_command(["docker", "network", "create", name], check=False, timeout=30)
    if res.ok:
        return
    # Deux labs démarrés en parallèle peuvent le créer en même temps : ce n'est
    # un échec que si le réseau n'existe toujours pas après coup.
    if not run_command(["docker", "network", "inspect", name],
                       check=False, timeout=15).ok:
        raise ServiceError(
            _("err_service_network_failed", name=name, detail=res.stderr.strip())
        )


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


_CONFIG_LABEL = "info.dsoxlab.service-config"


def _config_fingerprint(service: Service) -> str:
    """Empreinte de ce que le lab déclare : image, ports, env, arguments bruts.

    Deux labs d'un même dépôt qui déclarent un service de même ``name`` visent
    le même nom de conteneur. Si leurs déclarations diffèrent, le conteneur du
    premier ne convient pas au second, et le réutiliser tel quel donne un lab
    silencieusement inutilisable.
    """
    charge = json.dumps(
        {
            "image": service.image,
            "ports": list(service.ports),
            "env": dict(sorted(service.env.items())),
            "run_args": list(service.run_args),
        },
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(charge.encode("utf-8")).hexdigest()[:16]


def _running_fingerprint(name: str) -> str | None:
    """Empreinte portée par le conteneur en place, ``None`` s'il n'en a pas.

    Un conteneur créé par une version antérieure de dsoxlab n'a pas le label :
    il est alors traité comme divergent, donc recréé une fois.
    """
    res = run_command(
        ["docker", "inspect", "-f", "{{json .Config.Labels}}", name],
        check=False,
        timeout=15,
    )
    if not res.ok:
        return None
    try:
        labels = json.loads(res.stdout.strip() or "null") or {}
    except json.JSONDecodeError:
        return None
    valeur = labels.get(_CONFIG_LABEL)
    return valeur if isinstance(valeur, str) else None


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
        raise ServiceError(_(
            "err_service_port_closed",
            name=service.name, port=service.ready_tcp,
            timeout=service.ready_timeout,
        ))
    if service.ready_exec and not _wait_exec(name, service.ready_exec, service.ready_timeout):
        raise ServiceError(_(
            "err_service_probe_failed",
            name=service.name, probe=" ".join(service.ready_exec),
            timeout=service.ready_timeout,
        ))


def _diagnostic_arret(name: str) -> tuple[str, str]:
    """Pourquoi ce conteneur n'est plus debout : code de sortie et dernières lignes.

    Docker, lui, répond ``container <64 caractères hexadécimaux> is not
    running`` : vrai, inexploitable, et cité tel quel il accuse la commande
    qu'on essayait de jouer plutôt que l'arrêt qui l'empêche.
    """
    code = run_command(["docker", "inspect", "-f", "{{.State.ExitCode}}", name],
                       check=False, timeout=15)
    logs = run_command(["docker", "logs", "--tail", "10", name],
                       check=False, timeout=15)
    sortie = (logs.stdout or logs.stderr).strip()
    return code.stdout.strip() or "?", sortie or "(aucune)"


def _run_post_start(service: Service, name: str) -> None:
    """Joue les commandes d'initialisation DANS le conteneur, une fois prêt.

    Après ``ready_tcp``, jamais avant : un port qui accepte une connexion ne
    garantit pas un service qui répond, et une initialisation jouée trop tôt
    échoue de façon intermittente — le pire des symptômes à diagnostiquer.

    Un ``docker exec`` exige un conteneur debout. Quand il échoue, on regarde
    donc **pourquoi avant d'accuser la commande** : si le conteneur s'est
    arrêté, la réponse de Docker est ``container <64 caractères hexadécimaux>
    is not running``, et la reprendre telle quelle envoie chercher un défaut
    dans une commande qui n'a jamais été jouée. La cause utile est le code de
    sortie et les logs du conteneur.

    Le contrôle n'a lieu qu'en cas d'échec : le chemin nominal ne paie aucun
    appel supplémentaire, et un conteneur sain n'est jamais interrogé pour rien.

    Sans shell (``docker exec`` reçoit l'argv tel quel), donc pas d'expansion ni
    de redirection : ce que le lab déclare est ce qui s'exécute.
    """
    for argv in service.post_start:
        res = run_command(["docker", "exec", name, *argv], check=False, timeout=120)
        if res.ok:
            continue
        if not _is_running(name):
            code, logs = _diagnostic_arret(name)
            raise ServiceError(_(
                "err_service_container_stopped",
                name=service.name, container=name, code=code, logs=logs,
            ))
        raise ServiceError(_(
            "err_service_post_start_failed",
            name=service.name, command=" ".join(argv),
            detail=(res.stderr or res.stdout).strip(),
        ))


#: Le tirage d'une image n'a rien à voir avec le démarrage d'un conteneur :
#: il traverse le réseau, et une image de plusieurs gigaoctets sur le réseau
#: partagé d'une salle de formation dépasse largement le délai d'un `run`.
_DELAI_TIRAGE = 1800


def _image_locale(image: str) -> bool:
    return run_command(["docker", "image", "inspect", image],
                       check=False, timeout=15).ok


def _tirer(image: str, notifier: Callable[[str], None] | None) -> None:
    """Tire l'image si elle n'est pas déjà là, en le disant.

    Le premier ``docker run`` tirait l'image dans son propre délai. Deux
    conséquences : au-delà, la commande échouait sur un message de démarrage
    qui ne parlait pas du réseau ; et en deçà, l'apprenant voyait `run` pendre
    plusieurs minutes sans savoir que quelque chose se téléchargeait.
    """
    if _image_locale(image):
        return
    if notifier is not None:
        notifier(image)
    res = run_command(["docker", "pull", image], check=False,
                      timeout=_DELAI_TIRAGE)
    if not res.ok:
        raise ServiceError(_("service_pull_echec", image=image,
                             detail=(res.stderr or res.stdout).strip()))


def start(service: Service, repo_id: str, *,
          notifier: Callable[[str], None] | None = None) -> str:
    """Démarre (ou réutilise) le conteneur d'un service et attend sa disponibilité.

    Idempotent : si le conteneur tourne déjà **avec la configuration déclarée**,
    on ne le recrée pas. S'il existe mais est arrêté, on le retire d'abord.
    Retourne le nom du conteneur.

    La réutilisation compare l'empreinte de la déclaration à celle du conteneur
    en place. Sans cette comparaison, deux labs d'un même dépôt déclarant un
    service homonyme aux options différentes se partagent le conteneur du
    premier arrivé : le second démarre sur un service qui n'a ni ses ports, ni
    ses variables, ni ses arguments de lancement, et le lab échoue là où
    l'apprenant n'a rien fait de faux.

    ``post_start`` est rejoué dans les deux cas, y compris sur un conteneur
    réutilisé : c'est ce qui rend l'état de départ identique d'un lab à l'autre,
    quel que soit ce que l'exercice précédent a laissé derrière lui.

    Raises:
        ServiceError: Docker indisponible, échec du ``run``, service jamais
            prêt, ou commande ``post_start`` en échec.
    """
    name = container_name(repo_id, service)
    empreinte = _config_fingerprint(service)

    if _is_running(name) and _running_fingerprint(name) == empreinte:
        _wait_ready(service, name)
        _run_post_start(service, name)
        return name

    if _exists(name):
        run_command(["docker", "rm", "-f", name], check=False, timeout=30)

    # Réseau partagé + alias : depuis un autre service du même dépôt, celui-ci
    # se joint par son `name` déclaré (`db`, `vault`…), pas par le nom complet
    # du conteneur. C'est ce qui rend `DATASOURCES_DEFAULT_HOST: db` écrivable
    # dans un lab.yaml.
    reseau = network_name(repo_id)
    _ensure_network(reseau)

    cmd = ["docker", "run", "-d", "--name", name,
           "--network", reseau, "--network-alias", service.name,
           "--label", f"{_CONFIG_LABEL}={empreinte}"]
    for mapping in service.ports:
        cmd += ["-p", mapping]
    for key, value in service.env.items():
        cmd += ["-e", f"{key}={value}"]
    cmd += list(service.run_args)
    cmd.append(service.image)

    _tirer(service.image, notifier)
    res = run_command(cmd, check=False, timeout=180)
    if not res.ok:
        raise ServiceError(_(
            "err_service_start_failed",
            name=service.name, detail=res.stderr.strip(),
        ))

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
