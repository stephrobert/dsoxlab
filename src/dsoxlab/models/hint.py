"""Modèle de données pour les hints de challenge.

Deux formats supportés dans ``challenge/hints.yaml`` :

1. **Format moderne i18n** (recommandé) ::

       hints:
         - id: 1
           cost: 5
           text_en: "First English hint"
           text_fr: "Premier indice en français"

2. **Format legacy** (rétro-compat) — texte unique encodé base64 pour
   éviter la lecture directe du fichier ::

       hints:
         - text: "VG9uIGFzdHVjZSBpY2k="  # base64
           cost: 10

Le format moderne accepte aussi un ``text:`` sans encodage (le base64
est la convention legacy).
"""

from __future__ import annotations

import base64
import binascii
from dataclasses import dataclass, field
from pathlib import Path

import yaml


def _decode_hint(raw: object) -> str:
    """Décode un texte d'indice : base64 si possible, sinon plain text.

    Permet d'obfusquer les indices (les garder illisibles en clair dans le
    fichier) tout en supportant du texte brut. S'applique aux champs
    ``text_en``/``text_fr`` (i18n) comme au ``text`` legacy.
    """
    text = str(raw or "")
    if not text:
        return ""
    try:
        return base64.b64decode(text.encode(), validate=True).decode().rstrip("\n")
    except (ValueError, binascii.Error, UnicodeDecodeError):
        return text.rstrip("\n")


@dataclass
class Hint:
    text_en: str = ""
    text_fr: str = ""
    cost: int = 10

    def text(self, lang: str = "en") -> str:
        """Retourne le texte dans la langue demandée, fallback EN."""
        if lang == "fr" and self.text_fr:
            return self.text_fr
        return self.text_en


@dataclass
class HintFile:
    points: int = 100
    hints: list[Hint] = field(default_factory=list)

    @classmethod
    def load(cls, challenge_dir: Path) -> "HintFile":
        """Charge ``challenge/hints.yaml``. Retourne un HintFile vide si absent."""
        path = challenge_dir / "hints.yaml"
        if not path.exists():
            return cls()
        with path.open(encoding="utf-8") as fh:
            data = yaml.safe_load(fh) or {}

        hints: list[Hint] = []
        for h in data.get("hints", []):
            text_en = ""
            text_fr = ""

            # Format moderne i18n. text_en/text_fr acceptent aussi le base64
            # (même obfuscation que le legacy) : on tente le décodage, fallback
            # plain text.
            if "text_en" in h or "text_fr" in h:
                text_en = _decode_hint(h.get("text_en", ""))
                text_fr = _decode_hint(h.get("text_fr", ""))
            # Format legacy : text unique (base64 ou plain)
            elif "text" in h:
                text_en = _decode_hint(h["text"])

            hints.append(
                Hint(
                    text_en=text_en,
                    text_fr=text_fr,
                    cost=int(h.get("cost", 10)),
                )
            )
        return cls(points=int(data.get("points", 100)), hints=hints)
