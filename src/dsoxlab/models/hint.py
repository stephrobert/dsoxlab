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

            # Format moderne i18n
            if "text_en" in h or "text_fr" in h:
                text_en = str(h.get("text_en", "")).rstrip("\n")
                text_fr = str(h.get("text_fr", "")).rstrip("\n")
            # Format legacy : text unique (base64 ou plain)
            elif "text" in h:
                raw = str(h["text"])
                # Tente base64 d'abord ; sinon fallback en plain text
                try:
                    decoded = base64.b64decode(raw.encode(), validate=True).decode()
                    text_en = decoded
                except (ValueError, binascii.Error, UnicodeDecodeError):
                    text_en = raw

            hints.append(
                Hint(
                    text_en=text_en,
                    text_fr=text_fr,
                    cost=int(h.get("cost", 10)),
                )
            )
        return cls(points=int(data.get("points", 100)), hints=hints)
