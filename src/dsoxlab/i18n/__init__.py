"""Internationalisation — sélection de la langue via DSOXLAB_LANG (défaut : en)."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

_strings: dict[str, str] | None = None
_langue: str | None = None
_CONTEXT_FILE = ".dsoxlab-context.json"


def _read_context_lang() -> str | None:
    """Lit 'lang' dans .dsoxlab-context.json sans importer config (évite les imports circulaires)."""
    try:
        env = os.environ.get("LAB_HOME")
        root = Path(env).expanduser().resolve() if env else Path(__file__).parent.parent.parent.parent.resolve()
        ctx_path = root / _CONTEXT_FILE
        if ctx_path.exists():
            data = json.loads(ctx_path.read_text(encoding="utf-8"))
            lang = data.get("lang")
            if lang:
                return str(lang)[:2].lower()
    # Aveugle et silencieux : contexte absent, illisible ou JSON tronqué, la
    # réponse est la même — on retombe sur la langue par défaut. Ce module est
    # importé par tous les autres, il ne peut pas être une cause de panne.
    except Exception:  # noqa: S110, BLE001
        pass
    return None


def get_lang(ctx_lang: str | None = None) -> str:
    """Détermine la langue active.

    Ordre de priorité :
    1. Variable d'env DSOXLAB_LANG
    2. ctx_lang (passé explicitement)
    3. Fichier .dsoxlab-context.json
    4. Variable d'env système LANG
    5. "en" (défaut)
    """
    env_lang = os.environ.get("DSOXLAB_LANG", "").lower()
    if env_lang:
        return env_lang[:2]
    if ctx_lang:
        return ctx_lang[:2].lower()
    file_lang = _read_context_lang()
    if file_lang:
        return file_lang
    sys_lang = os.environ.get("LANG", "").lower()
    if sys_lang and len(sys_lang) >= 2:
        return sys_lang[:2]
    return "en"


def set_lang(lang: str) -> None:
    """Force le rechargement des strings dans la langue donnée.

    À appeler une fois en début de CLI, après lecture du contexte.
    """
    global _strings, _langue  # noqa: PLW0603 — table de traduction, un cache de processus
    _strings = _load(lang)
    _langue = lang


def langue_a_transmettre(ctx_lang: str | None = None) -> str:
    """La langue à poser dans ``DSOXLAB_LANG`` pour un processus enfant.

    Les tests d'un catalogue et ses playbooks choisissent leur langue par cette
    variable. Jusqu'à la 0.11.0, dsoxlab ne la posait pas : un apprenant qui avait
    choisi le français par ``dsoxlab use --lang fr``, ou par sa locale, lisait
    une interface française et des messages d'échec anglais. Seul ``DSOXLAB_LANG``
    posé à la main passait, par simple héritage.

    ``ctx_lang`` est la langue du contexte d'un dépôt précis, quand l'appelant le
    connaît. Sans elle, c'est celle que la CLI a retenue à son amorçage.
    """
    retenue = get_lang(ctx_lang=ctx_lang or _langue)
    return "fr" if retenue.startswith("fr") else "en"


def _load(lang: str = "en") -> dict[str, str]:
    if lang.startswith("fr"):
        from .strings.fr import STRINGS
    else:
        from .strings.en import STRINGS
    return STRINGS


def _(key: str, **kwargs: Any) -> str:
    """Retourne la chaîne traduite pour *key*, avec substitution optionnelle."""
    global _strings  # noqa: PLW0603 — idem : chargement paresseux du même cache
    if _strings is None:
        _strings = _load(get_lang())
    text = _strings.get(key, key)
    return text.format(**kwargs) if kwargs else text
