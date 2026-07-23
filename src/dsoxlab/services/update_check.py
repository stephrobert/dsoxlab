"""Signale à l'utilisateur qu'une version plus récente existe sur PyPI.

Un apprenant installe `dsoxlab` une fois et ne revient jamais voir s'il
existe mieux. Il joue alors des labs avec une CLI qui traîne des défauts
corrigés depuis, et remonte des problèmes déjà résolus. D'où cet avis, mais
il doit se faire oublier : trois règles le tiennent.

1. **Il ne peut pas polluer une sortie machine.** Le message part sur
   `stderr`, jamais sur `stdout`. Le contrat JSON de `--json` reste lisible
   quoi qu'il arrive, y compris si l'avis tombe au milieu d'un pipeline.
   (Un document JSON précédé d'une ligne de texte, c'est le défaut corrigé
   en 0.1.23 ; il ne sera pas réintroduit par la porte de derrière.)
2. **Il ne peut pas faire échouer une commande.** Réseau coupé, PyPI en
   panne, proxy hostile, réponse illisible : tout est avalé en silence.
   Vérifier une version n'est jamais une raison de casser un `check`.
3. **Il ne coûte pas une requête par commande.** Le résultat est mis en
   cache un jour. Sans cela, chaque `dsoxlab list-labs` paierait un aller
   retour réseau, et une salle de formation entière taperait sur PyPI.

Désactivation : `DSOXLAB_NO_UPDATE_CHECK=1`.
"""

from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.request
from pathlib import Path

#: Un jour. Assez court pour qu'une correction se sache, assez long pour
#: qu'une session de travail ne déclenche qu'une seule requête.
CACHE_TTL_SECONDS = 24 * 60 * 60

#: Court volontairement : l'avis est un bonus, pas un préalable. Mieux vaut
#: ne rien dire que faire attendre quelqu'un devant son terminal.
HTTP_TIMEOUT_SECONDS = 2.0

PYPI_URL = "https://pypi.org/pypi/dsoxlab/json"

_ENV_OPT_OUT = "DSOXLAB_NO_UPDATE_CHECK"


def _xdg_cache_home() -> Path:
    """Racine du cache utilisateur, conforme XDG."""
    raw = os.environ.get("XDG_CACHE_HOME")
    if raw:
        return Path(raw)
    return Path.home() / ".cache"


def cache_path() -> Path:
    """Fichier où l'on retient la dernière version vue et sa date."""
    return _xdg_cache_home() / "dsoxlab" / "version-check.json"


def parse_version(raw: str) -> tuple[int, int, int]:
    """Découpe « 0.1.24 » en (0, 1, 24), sans dépendance externe.

    Le projet suit le versionnage sémantique, donc trois nombres suffisent.
    Tout suffixe (« 0.2.0rc1 », « 1.0.0.dev3 ») est tronqué à sa partie
    numérique : une pré-release n'est jamais proposée comme une nouveauté,
    ce qui est le comportement voulu.
    """
    parts: list[int] = []
    for chunk in raw.strip().split(".")[:3]:
        digits = ""
        for char in chunk:
            if not char.isdigit():
                break
            digits += char
        parts.append(int(digits) if digits else 0)
    while len(parts) < 3:
        parts.append(0)
    return parts[0], parts[1], parts[2]


def _read_cache(now: float) -> str | None:
    """Version retenue si le cache est encore frais, sinon None."""
    path = cache_path()
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        checked_at = float(payload["checked_at"])
        latest = str(payload["latest"])
    except (OSError, ValueError, KeyError, TypeError):
        # Cache absent, tronqué, ou écrit par une version antérieure au
        # format actuel : on le traite comme absent, jamais comme une erreur.
        return None
    if now - checked_at > CACHE_TTL_SECONDS:
        return None
    return latest


def _write_cache(latest: str, now: float) -> None:
    """Retient la version vue. Un échec d'écriture n'est pas une erreur."""
    path = cache_path()
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps({"checked_at": now, "latest": latest}),
            encoding="utf-8",
        )
    except OSError:
        # Home en lecture seule, quota dépassé, cache monté ailleurs : on
        # perd le cache, donc on refera une requête. Sans conséquence.
        return


def fetch_latest_version() -> str | None:
    """Interroge PyPI. Rend None dès que quoi que ce soit se passe mal."""
    try:
        request = urllib.request.Request(  # noqa: S310 - URL constante, https
            PYPI_URL,
            headers={"Accept": "application/json"},
        )
        with urllib.request.urlopen(  # noqa: S310 - idem
            request, timeout=HTTP_TIMEOUT_SECONDS
        ) as response:
            payload = json.loads(response.read().decode("utf-8"))
        latest = payload["info"]["version"]
    except (urllib.error.URLError, OSError, ValueError, KeyError, TypeError):
        # Hors ligne, DNS muet, PyPI en panne, proxy qui rend du HTML,
        # schéma modifié : aucun de ces cas ne regarde l'utilisateur.
        return None
    if not isinstance(latest, str) or not latest.strip():
        return None
    return latest.strip()


def available_update(current: str, *, force: bool = False) -> str | None:
    """Rend la version disponible si elle est plus récente, sinon None.

    Args:
        current: version installée (``dsoxlab.__version__``).
        force: ignorer le cache et interroger PyPI malgré tout. Utilisé par
            ``dsoxlab doctor``, où l'utilisateur demande explicitement un
            diagnostic et attend une réponse fraîche.
    """
    if os.environ.get(_ENV_OPT_OUT):
        return None

    now = time.time()
    latest = None if force else _read_cache(now)
    if latest is None:
        latest = fetch_latest_version()
        if latest is None:
            return None
        _write_cache(latest, now)

    try:
        if parse_version(latest) <= parse_version(current):
            return None
    except (ValueError, TypeError):
        return None
    return latest
