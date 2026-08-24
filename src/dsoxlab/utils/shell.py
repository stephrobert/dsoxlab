"""Wrapper centralisé pour l'exécution de commandes système."""

from __future__ import annotations

import logging
import subprocess
from dataclasses import dataclass
from pathlib import Path

logger = logging.getLogger(__name__)


#: Causes d'échec qui ne viennent pas du code de retour de la commande, mais
#: du fait qu'elle n'a pas pu s'exécuter du tout. Jetons **stables** : un
#: appelant les compare, il ne les affiche pas — le texte lisible est dans
#: ``stderr``, et la traduction dans la couche qui rend le message.
FAILURE_NOT_FOUND = "not_found"
"""Le binaire n'est pas dans le PATH."""

FAILURE_TIMEOUT = "timeout"
"""La commande a dépassé son délai. Elle tournait peut-être encore."""

FAILURE_OS_ERROR = "os_error"
"""Exec refusé, descripteur épuisé, binaire disparu entre-temps."""


@dataclass
class CommandResult:
    returncode: int
    stdout: str
    stderr: str

    failure: str | None = None
    """Pourquoi la commande n'a pas pu s'exécuter, ou ``None`` si elle a tourné.

    Distingue « la commande a répondu, mal » de « la commande n'a pas répondu ».
    Un appelant qui ne regarde que ``returncode`` traiterait un binaire absent
    comme un échec métier, et un délai dépassé comme un refus — deux causes qui
    appellent des gestes opposés (installer un paquet, ou réessayer).
    """

    @property
    def ok(self) -> bool:
        return self.returncode == 0 and self.failure is None


class CommandError(RuntimeError):
    """Levée quand une commande échoue et que check=True."""

    def __init__(self, cmd: list[str], result: CommandResult) -> None:
        self.cmd = cmd
        self.result = result
        super().__init__(
            f"Commande échouée (code {result.returncode}): {' '.join(cmd)}\n"
            f"stderr: {result.stderr.strip()}"
        )


def _echec(cmd: list[str], cause: str, detail: str, *, check: bool) -> CommandResult:
    """Traduit un échec d'exécution en résultat, ou en exception si ``check``.

    C'est ici que ``check=False`` tient sa promesse. Les trois causes levaient
    auparavant **quelles que soient** les options, si bien qu'un appelant qui
    croyait recevoir un ``CommandResult`` en toutes circonstances se trompait —
    et le nom du paramètre l'encourageait à le croire. Un `git` absent sortait
    donc en traceback Python sur la deuxième commande du parcours d'accueil.
    """
    resultat = CommandResult(returncode=-1, stdout="", stderr=detail, failure=cause)
    if check:
        raise CommandError(cmd, resultat)
    return resultat


def run_command(
    cmd: list[str],
    *,
    cwd: Path | None = None,
    timeout: int = 120,
    check: bool = True,
    env: dict[str, str] | None = None,
) -> CommandResult:
    """Exécute une commande système et retourne le résultat.

    Args:
        cmd: Liste de tokens de la commande.
        cwd: Répertoire de travail (optionnel).
        timeout: Timeout en secondes (défaut 120).
        check: Lève CommandError si la commande échoue — code de retour non
            nul, binaire absent, délai dépassé ou erreur système. Avec
            ``check=False``, **aucune** de ces situations ne lève : le résultat
            porte ``returncode = -1`` et un ``failure`` qui dit laquelle.
        env: Variables d'environnement supplémentaires.

    Returns:
        CommandResult avec returncode, stdout et stderr.

    Raises:
        CommandError: Si ``check=True`` et que la commande a échoué, pour
            n'importe laquelle des quatre causes ci-dessus.
    """
    logger.debug("run: %s (cwd=%s)", " ".join(cmd), cwd)

    try:
        # check=False délibéré : c'est CE wrapper qui implémente `check`, plus
        # bas et à sa façon — une CommandError qui porte la commande, le code
        # retour et stderr. Déléguer à subprocess lèverait un
        # CalledProcessError nu, et le paramètre `check` de cette fonction
        # n'aurait plus de sens.
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            cwd=cwd,
            timeout=timeout,
            env=env,
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        return _echec(cmd, FAILURE_TIMEOUT, str(exc), check=check)
    except FileNotFoundError:
        return _echec(cmd, FAILURE_NOT_FOUND, f"{cmd[0]}: No such file or directory",
                      check=check)
    except OSError as exc:
        # Un binaire qui disparaît entre deux appels, un exec refusé : l'échec
        # appartient à la commande, pas à l'appelant. Le laisser remonter en
        # OSError nu ferait planter un diagnostic en train de diagnostiquer.
        return _echec(cmd, FAILURE_OS_ERROR, str(exc), check=check)

    result = CommandResult(
        returncode=proc.returncode,
        stdout=proc.stdout,
        stderr=proc.stderr,
    )

    if result.ok:
        logger.debug("ok: returncode=0")
    else:
        logger.debug("fail: returncode=%d, stderr=%s", result.returncode, result.stderr.strip())

    if check and not result.ok:
        raise CommandError(cmd, result)

    return result
