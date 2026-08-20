#!/usr/bin/env python3
"""Rastérise la marque en PNG haute définition, depuis les SVG.

Les SVG font foi ; ces PNG en dérivent. Ils existent pour les endroits qui
n'acceptent pas de vecteur : l'aperçu social de GitHub, une présentation, une
vignette de plateforme, un README rendu par un outil sans support SVG.

**Le piège que ce script évite.** `convert fichier.svg -resize 1024x` rastérise
d'abord à la taille du `viewBox`, soit 48 pixels de côté, puis agrandit ce
bitmap : le résultat est flou et crénelé, alors que la source est vectorielle.
Il faut rastériser directement à la bonne résolution, ce que fait `-density`.
La différence n'est pas subtile, elle saute aux yeux à 100 %.

Usage :
    python3 scripts/generer-png-marque.py
"""

from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

RACINE = Path(__file__).resolve().parent.parent
SOURCE = RACINE / "docs" / "assets" / "brand"
CIBLE = SOURCE / "png"

#: Densité de rastérisation. Le viewBox de l'icône fait 48 unités ; à 1200 dpi
#: elle est rendue autour de 800 pixels avant redimensionnement, ce qui suffit
#: pour toutes les tailles produites ici sans jamais agrandir un bitmap.
DENSITE = "1200"

#: (source, largeur, fond, nom de sortie). Le fond `none` garde la
#: transparence : un logo posé sur une couleur qu'on ne connaît pas ne doit pas
#: traîner un carré blanc.
RENDUS: list[tuple[str, int, str, str]] = [
    ("dsoxlab-icon.svg", 256, "none", "dsoxlab-icon-256.png"),
    ("dsoxlab-icon.svg", 512, "none", "dsoxlab-icon-512.png"),
    ("dsoxlab-icon.svg", 1024, "none", "dsoxlab-icon-1024.png"),
    ("dsoxlab-icon-dark.svg", 512, "none", "dsoxlab-icon-dark-512.png"),
    ("dsoxlab-icon-dark.svg", 1024, "none", "dsoxlab-icon-dark-1024.png"),
    ("dsoxlab-lockup-light.svg", 1024, "none", "dsoxlab-lockup-light-1024.png"),
    ("dsoxlab-lockup-light.svg", 2048, "none", "dsoxlab-lockup-light-2048.png"),
    ("dsoxlab-lockup-dark.svg", 1024, "none", "dsoxlab-lockup-dark-1024.png"),
    ("dsoxlab-lockup-dark.svg", 2048, "none", "dsoxlab-lockup-dark-2048.png"),
]

#: L'aperçu social de GitHub. Ses dimensions sont imposées par la plateforme, et
#: le logo y est centré avec une marge large : la carte est recadrée par les
#: réseaux qui la republient, et ce qui touche le bord se fait couper.
SOCIAL = ("dsoxlab-lockup-light.svg", 1280, 640, "#FFFFFF", "dsoxlab-social-preview.png")
SOCIAL_DARK = ("dsoxlab-lockup-dark.svg", 1280, 640, "#0B1220",
               "dsoxlab-social-preview-dark.png")


def _convert(*args: str) -> None:
    subprocess.run(["convert", *args], check=True, capture_output=True)


def main() -> int:
    if shutil.which("convert") is None:
        print("ImageMagick absent : installe-le, ou rends les SVG autrement.")
        return 1

    CIBLE.mkdir(parents=True, exist_ok=True)

    for nom_svg, largeur, fond, sortie in RENDUS:
        _convert(
            "-background", fond, "-density", DENSITE,
            str(SOURCE / nom_svg), "-resize", f"{largeur}x",
            str(CIBLE / sortie),
        )
        poids = (CIBLE / sortie).stat().st_size
        print(f"  ✔ {sortie:36s} {poids // 1024:4d} Kio")

    for nom_svg, largeur, hauteur, fond, sortie in (SOCIAL, SOCIAL_DARK):
        _convert(
            "-background", "none", "-density", DENSITE,
            str(SOURCE / nom_svg), "-resize", f"{int(largeur * 0.55)}x",
            "-background", fond, "-gravity", "center",
            "-extent", f"{largeur}x{hauteur}",
            str(CIBLE / sortie),
        )
        poids = (CIBLE / sortie).stat().st_size
        print(f"  ✔ {sortie:36s} {poids // 1024:4d} Kio  ({largeur}x{hauteur})")

    return 0


if __name__ == "__main__":
    sys.exit(main())
