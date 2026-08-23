"""Joue la suite E2E dans une distribution, sur le Python que cette distribution package.

Les utilisateurs de dsoxlab n'ont pas des versions de Python différentes : ils
ont des **distributions** différentes. C'est là que le produit casse, parce que
ce qu'il pilote (ssh, terraform, libvirt, docker, sudo) y est packagé
autrement, dans d'autres versions, avec d'autres chemins. Une matrice qui ne
fait varier que Python sur un seul Ubuntu ne mesure rien de tout cela.

Ce script est le même pour toutes les distributions : ce qui change tient dans
la commande d'amorçage, passée en argument. Un script par distribution ferait
converger cinq scénarios différents vers cinq verts qui ne disent rien.

Il tourne en CI (un job par distribution, cf. `.github/workflows/ci.yml`) et
**à la main**, ce qui est le point : la matrice se rejoue sur un poste avant
d'être poussée.

    uv build --wheel --out-dir dist
    python3 scripts/parcours-distribution.py \
        --image debian:13 \
        --bootstrap 'apt-get update -qq && apt-get install -y -qq python3 python3-venv python3-pip' \
        --wheel dist/dsoxlab-*.whl

Deux garde-fous portent tout le sens de l'exercice.

``UV_PYTHON_DOWNLOADS=never`` interdit à uv de télécharger son propre CPython.
uv en installe un « standalone » par défaut, identique partout : la matrice ne
mesurerait plus alors que le réseau de GitHub. Avec ce garde-fou, la roue
s'installe sur le Python de la distribution, et c'est le seul moyen d'apprendre
qu'elle en package un trop vieux.

``DSOXLAB_E2E_WHEEL`` fournit la roue **déjà construite** : la suite sait la
lire, donc aucune distribution ne reconstruit, et toutes éprouvent l'artefact
que PyPI servirait plutôt que cinq artefacts différents.
"""

from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
from pathlib import Path

#: Le dépôt, monté **en lecture seule** dans le conteneur. Le parcours d'un
#: utilisateur n'écrit jamais dans les sources de l'outil : si un jour il en a
#: besoin, c'est un défaut, et le montage le fait apparaître ici.
POINT_TRAVAIL = "/travail"

#: L'environnement du harnais (uv + pytest), séparé de celui où la roue sera
#: installée. Sans cette séparation, la suite testerait sa propre installation
#: plutôt que l'empaquetage.
HARNAIS = "/opt/harnais"


def _commande_conteneur(amorcage: str, roue_dans_conteneur: str) -> str:
    """Les étapes jouées **dans** la distribution, dans l'ordre.

    Composées ici plutôt que dans un fichier shell : le dépôt n'en contient
    aucun, et l'orchestration reste en Python comme le reste de l'outillage.
    """
    etapes = [
        # `set -e` : une étape ratée arrête tout. Sans lui, un amorçage en échec
        # laisserait la suite tourner sur un Python absent, et le message
        # d'erreur ne parlerait plus de la distribution.
        "set -e",
        "echo '── amorçage de la distribution ──'",
        amorcage,
        "echo '── le Python de cette distribution ──'",
        "python3 --version",
        f"python3 -m venv {HARNAIS}",
        f"{HARNAIS}/bin/pip install --quiet --disable-pip-version-check uv pytest",
        f"export PATH={HARNAIS}/bin:$PATH",
        f"cd {POINT_TRAVAIL}",
        "echo '── parcours de bout en bout ──'",
        # `-p no:cacheprovider` : le dépôt est monté en lecture seule, et pytest
        # tenterait sinon d'y écrire son cache. Un avertissement, pas un échec,
        # mais un avertissement qu'on lira un jour comme un vrai problème.
        f"exec {HARNAIS}/bin/python -m pytest tests_e2e -q -p no:cacheprovider",
    ]
    return "\n".join(etapes)


def _argv_docker(image: str, depot: Path, roue: Path, amorcage: str) -> list[str]:
    # La roue est prise **dans** le dépôt monté : un seul montage, donc un seul
    # chemin à raisonner, et rien à recopier avant de lancer le conteneur.
    relative = roue.resolve().relative_to(depot.resolve())
    dans_conteneur = f"{POINT_TRAVAIL}/{relative}"

    return [
        "docker", "run", "--rm",
        # Les distributions Debian posent des questions à l'installation si on
        # ne les en dispense pas, et le conteneur n'a pas de terminal.
        "-e", "DEBIAN_FRONTEND=noninteractive",
        "-e", "UV_PYTHON_DOWNLOADS=never",
        "-e", f"DSOXLAB_E2E_WHEEL={dans_conteneur}",
        "-v", f"{depot.resolve()}:{POINT_TRAVAIL}:ro",
        "-w", POINT_TRAVAIL,
        image,
        "sh", "-c", _commande_conteneur(amorcage, dans_conteneur),
    ]


def main() -> int:
    analyseur = argparse.ArgumentParser(description=__doc__ or "")
    analyseur.add_argument("--image", required=True, help="image de la distribution")
    analyseur.add_argument(
        "--bootstrap",
        required=True,
        help="commande qui installe python3, venv et pip dans cette distribution",
    )
    analyseur.add_argument(
        "--wheel", required=True, type=Path, help="la roue à éprouver, dans le dépôt"
    )
    analyseur.add_argument(
        "--repo",
        type=Path,
        default=Path(__file__).resolve().parent.parent,
        help="racine du dépôt (défaut : celle de ce script)",
    )
    arguments = analyseur.parse_args()

    if shutil.which("docker") is None:
        # On n'ignore pas en silence : une matrice de distributions désactivée
        # est une matrice qui n'existe pas.
        print("docker est introuvable, et ce contrôle ne sait pas s'en passer.", file=sys.stderr)
        return 127

    if not arguments.wheel.is_file():
        print(f"roue introuvable : {arguments.wheel}", file=sys.stderr)
        return 2

    argv = _argv_docker(arguments.image, arguments.repo, arguments.wheel, arguments.bootstrap)
    print(f"── {arguments.image} ──", flush=True)
    return subprocess.run(argv, check=False).returncode


if __name__ == "__main__":
    raise SystemExit(main())
