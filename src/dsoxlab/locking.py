"""Verrou d'écriture par dépôt : une seule invocation modifie l'état à la fois.

Deux terminaux ouverts, c'est le cas normal chez un apprenant. Rien n'empêchait
jusqu'ici deux ``dsoxlab`` d'écrire en même temps sur le même état, et cet état
est éparpillé :

- ``<repo>/.dsoxlab-context.json``, réécrit **en entier** par ``config._persist``
  (deux écritures concurrentes : la dernière gagne, la première est perdue sans
  trace) ;
- le state Terraform sous ``~/.local/state/dsoxlab/<repo-id>/terraform/`` ;
- l'inventaire et le fragment ``ssh_config`` régénérés en cache ;
- les conteneurs de ``runtime.services``, nommés par dépôt donc partagés.

La SQLite ``<repo>/.dsoxlab.db`` est la seule pièce déjà protégée, par SQLite.

Où se pose le verrou, et pourquoi pas dans le dépôt
===================================================

Sous ``~/.local/state/dsoxlab/<identité>/dsoxlab.lock``, c'est-à-dire **à la
racine du répertoire d'état de ce dépôt**, celui-là même qui porte le state
Terraform. Le poser dans le dépôt de labs aurait paru plus naturel (c'est là
que vivent ``.dsoxlab.db`` et ``.dsoxlab-context.json``), mais chaque dépôt
fournisseur ignore ces deux fichiers **nommément**, pas par un motif : un
troisième fichier apparaîtrait en untracked chez tous, et il faudrait modifier
trois dépôts pour livrer un verrou.

L'identité est ``repo.id`` quand le ``meta.yml`` est lisible, sinon le nom du
répertoire suffixé d'une empreinte de son chemin absolu. Prendre ``repo.id`` en
premier n'est pas un détail : deux clones du même catalogue partagent le **même**
work-dir Terraform, donc doivent partager le verrou. Les sérialiser inutilement
ne coûte rien ; les laisser s'écrire dessus coûte un state corrompu.

Un verrou périmé, et pourquoi il n'existe pas ici
=================================================

Le verrou est un ``flock`` (``LOCK_EX | LOCK_NB``). Le noyau le relâche **de
lui-même** quand le descripteur se ferme, y compris si le processus meurt d'un
``SIGKILL``, et il ne survit évidemment pas à un redémarrage. Il n'y a donc
aucun verrou à « reprendre » : la question de la reprise, qui est la vraie
difficulté des verrous par fichier-sentinelle, ne se pose pas.

Ce qui survit, c'est le **fichier**, et le nom de son ancien détenteur. On le
tronque en le relâchant pour qu'il ne raconte pas une invocation terminée, et on
ne le supprime **jamais** : effacer un fichier de verrou est la course classique
où un processus retire sous les pieds d'un autre l'inode qu'il tient déjà.

Le verrou n'est pas hérité par les sous-processus : Python crée ses descripteurs
non héritables (PEP 446), et ``exec`` les referme. Le sous-shell ouvert par
``dsoxlab run`` ne tient donc rien, ce qui est indispensable, puisque
l'apprenant y tape ``dsoxlab check``.
"""

from __future__ import annotations

import errno
import fcntl
import hashlib
import json
import logging
import os
import re
import socket
import time
from pathlib import Path
from types import TracebackType
from typing import Any, Self

import yaml

from .config import xdg_state_home

logger = logging.getLogger(__name__)

#: Code de sortie d'une commande refusée parce qu'une autre tient le verrou.
#: Distinct des codes déjà employés (1 à 6) : un script qui enchaîne des
#: commandes doit pouvoir réessayer sur celui-ci et abandonner sur les autres.
EXIT_LOCKED = 7

#: Caractères tolérés dans un nom de répertoire dérivé d'une donnée du contrat.
_HORS_SLUG = re.compile(r"[^A-Za-z0-9_.-]")

#: Errnos qui disent « ce système de fichiers ne sait pas verrouiller ».
#: On dégrade alors au lieu de refuser de travailler : un ``~/.local/state``
#: monté sur un NFS sans lockd rendrait l'outil inutilisable, ce qui est un
#: prix bien supérieur au risque qu'on couvre.
_SANS_VERROU = frozenset({errno.ENOLCK, errno.ENOSYS, errno.EOPNOTSUPP, errno.EINVAL})


class LockHolder:
    """Ce que le détenteur du verrou a écrit de lui-même dans le fichier."""

    __slots__ = ("command", "host", "pid", "since")

    def __init__(self, command: str, pid: int, since: float, host: str) -> None:
        self.command = command
        self.pid = pid
        self.since = since
        self.host = host

    @property
    def age_seconds(self) -> int:
        """Âge du verrou, jamais négatif même si l'horloge a reculé."""
        return max(0, int(time.time() - self.since))

    @property
    def age_label(self) -> str:
        """L'âge en ``12m03s`` : de la mise en forme, aucun mot à traduire."""
        total = self.age_seconds
        return f"{total // 60}m{total % 60:02d}s" if total >= 60 else f"{total}s"


class RepoLocked(RuntimeError):
    """Le verrou de ce dépôt est déjà tenu par une autre invocation.

    Porte des **données** (le détenteur, le chemin), pas une phrase : c'est la
    CLI qui compose le message traduit, comme le fait déjà ``ProviderUnresolved``.
    """

    def __init__(self, path: Path, holder: LockHolder | None) -> None:
        self.path = path
        self.holder = holder
        super().__init__(str(path))


def _repo_id(root: Path) -> str | None:
    """``repo.id`` du ``meta.yml``, ou ``None`` s'il n'est pas lisible.

    Lecture volontairement minimale et tolérante : le verrou se prend **avant**
    tout le reste, et un ``meta.yml`` illisible ne doit pas empêcher de
    verrouiller : il fait seulement retomber sur l'identité par chemin.
    """
    from .discovery.repo import find_meta_yml

    chemin = find_meta_yml(root)
    if chemin is None:
        return None
    try:
        brut: Any = yaml.safe_load(chemin.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, yaml.YAMLError):
        return None
    if not isinstance(brut, dict):
        return None
    depot = brut.get("repo")
    if not isinstance(depot, dict):
        return None
    ident = depot.get("id")
    if isinstance(ident, str) and ident.strip():
        return ident.strip()
    return None


def lock_identity(root: Path) -> str:
    """Identité de dépôt sous laquelle le verrou est posé."""
    ident = _repo_id(root)
    if ident:
        return _HORS_SLUG.sub("-", ident)
    resolu = root.expanduser().resolve()
    empreinte = hashlib.sha256(str(resolu).encode("utf-8")).hexdigest()[:12]
    nom = _HORS_SLUG.sub("-", resolu.name) or "repo"
    return f"{nom}-{empreinte}"


def lock_path(root: Path) -> Path:
    """Chemin du fichier de verrou de ce dépôt."""
    return xdg_state_home() / "dsoxlab" / lock_identity(root) / "dsoxlab.lock"


def _lire_detenteur(fd: int) -> LockHolder | None:
    """Relit le fichier de verrou par son descripteur, sans jamais lever.

    Un fichier vide (verrou relâché à l'instant), tronqué ou écrit par une
    version antérieure rend ``None`` : la CLI dira alors qu'une autre invocation
    travaille, sans pouvoir la nommer. C'est moins précis, jamais faux.
    """
    try:
        os.lseek(fd, 0, os.SEEK_SET)
        brut = os.read(fd, 4096).decode("utf-8")
    except (OSError, UnicodeDecodeError):
        return None
    if not brut.strip():
        return None
    try:
        data = json.loads(brut)
    except json.JSONDecodeError:
        return None
    if not isinstance(data, dict):
        return None
    pid = data.get("pid")
    since = data.get("since")
    return LockHolder(
        command=str(data.get("command") or "?"),
        pid=pid if isinstance(pid, int) else 0,
        since=float(since) if isinstance(since, int | float) else time.time(),
        host=str(data.get("host") or ""),
    )


class RepoLock:
    """Le verrou d'écriture d'un dépôt, pris pour la durée d'une commande.

    S'utilise en gestionnaire de contexte. ``__enter__`` ne reprend pas un
    verrou déjà tenu par cette instance : la CLI acquiert d'abord (pour traduire
    le refus en message et en code de sortie), puis ouvre le ``with`` sur
    l'instance déjà acquise.
    """

    def __init__(self, root: Path, command: str) -> None:
        self.path = lock_path(root)
        self.command = command
        self._fd: int | None = None
        self._degrade = False

    @property
    def held(self) -> bool:
        """Le verrou est-il réellement tenu par ce processus ?"""
        return self._fd is not None and not self._degrade

    def acquire(self) -> None:
        """Prend le verrou, ou lève ``RepoLocked`` si un autre le tient.

        Ne bloque jamais : une attente silencieuse ferait passer un conflit
        pour une lenteur, alors que l'apprenant a justement besoin de savoir
        quelle commande tourne ailleurs.
        """
        if self._fd is not None:
            return
        self.path.parent.mkdir(parents=True, exist_ok=True)
        fd = os.open(self.path, os.O_RDWR | os.O_CREAT | os.O_CLOEXEC, 0o600)
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as exc:
            if exc.errno in (errno.EACCES, errno.EAGAIN):
                detenteur = _lire_detenteur(fd)
                os.close(fd)
                raise RepoLocked(self.path, detenteur) from None
            if exc.errno in _SANS_VERROU:
                # Dégradé assumé et tracé : mieux vaut un outil qui travaille
                # sans filet qu'un outil qui refuse de démarrer.
                logger.warning(
                    "verrou indisponible sur %s (%s) : la commande continue "
                    "sans protection contre une invocation concurrente",
                    self.path, exc.strerror,
                )
                self._fd = fd
                self._degrade = True
                return
            os.close(fd)
            raise
        self._fd = fd
        self._ecrire_detenteur(fd)

    def _ecrire_detenteur(self, fd: int) -> None:
        """Inscrit qui tient le verrou. Best-effort : un échec ne l'annule pas."""
        charge = json.dumps({
            "command": self.command,
            "pid": os.getpid(),
            "since": time.time(),
            "host": socket.gethostname(),
        })
        try:
            os.ftruncate(fd, 0)
            os.lseek(fd, 0, os.SEEK_SET)
            os.write(fd, charge.encode("utf-8"))
        except OSError:
            logger.warning("verrou pris, mais son détenteur n'a pas pu être inscrit")

    def release(self) -> None:
        """Relâche le verrou et efface la trace du détenteur.

        La troncature vient **avant** la fermeture : le fichier survit, et un
        contenu périmé ferait accuser une commande terminée depuis longtemps.
        """
        fd = self._fd
        if fd is None:
            return
        self._fd = None
        if not self._degrade:
            try:
                os.ftruncate(fd, 0)
            except OSError:
                logger.debug("troncature du verrou impossible", exc_info=True)
        self._degrade = False
        os.close(fd)

    def __enter__(self) -> Self:
        self.acquire()
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        del exc_type, exc, tb
        self.release()
