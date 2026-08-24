"""Wrapper centralisé pour l'exécution de commandes système."""

from __future__ import annotations

import logging
import subprocess
from dataclasses import dataclass
from pathlib import Path

logger = logging.getLogger(__name__)


@dataclass
class CommandResult:
    returncode: int
    stdout: str
    stderr: str

    @property
    def ok(self) -> bool:
        return self.returncode == 0


class CommandError(RuntimeError):
    """Levée quand une commande échoue et que check=True."""

    def __init__(self, cmd: list[str], result: CommandResult) -> None:
        self.cmd = cmd
        self.result = result
        super().__init__(
            f"Commande échouée (code {result.returncode}): {' '.join(cmd)}\n"
            f"stderr: {result.stderr.strip()}"
        )


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
        check: Lève CommandError si le code de retour est != 0.
        env: Variables d'environnement supplémentaires.

    Returns:
        CommandResult avec returncode, stdout et stderr.

    Raises:
        CommandError: Si check=True et le code de retour est != 0.
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
        raise CommandError(cmd, CommandResult(returncode=-1, stdout="", stderr=str(exc))) from exc
    except FileNotFoundError as exc:
        raise CommandError(
            cmd, CommandResult(returncode=-1, stdout="", stderr=f"Commande introuvable: {cmd[0]}")
        ) from exc
    except OSError as exc:
        # Un binaire qui disparaît entre deux appels, un exec refusé : l'échec
        # appartient à la commande, pas à l'appelant. Le laisser remonter en
        # OSError nu ferait planter un diagnostic en train de diagnostiquer.
        raise CommandError(
            cmd, CommandResult(returncode=-1, stdout="", stderr=str(exc))
        ) from exc

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
