"""Internationalisation — sélection de la langue via DSOXLAB_LANG (défaut : en)."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

_strings: dict[str, str] | None = None
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
    except Exception:  # noqa: S110 — contexte illisible/absent : on retombe sur la langue par défaut
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
    global _strings
    _strings = _load(lang)


def _load(lang: str = "en") -> dict[str, str]:
    if lang.startswith("fr"):
        from .strings.fr import STRINGS
    else:
        from .strings.en import STRINGS
    return STRINGS


def _(key: str, **kwargs: Any) -> str:
    """Retourne la chaîne traduite pour *key*, avec substitution optionnelle."""
    global _strings
    if _strings is None:
        _strings = _load(get_lang())
    text = _strings.get(key, key)
    return text.format(**kwargs) if kwargs else text
