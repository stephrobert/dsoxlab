"""Les deux garde-fous de la matrice de distributions (#84).

Le job qui joue le parcours sur cinq systèmes ne vaut que par deux réglages, et
tous deux sont silencieux quand ils sautent : la CI resterait verte, plus rien
ne serait mesuré, et personne ne le verrait avant le rapport de bug.

* Sans ``UV_PYTHON_DOWNLOADS=never``, uv installe son propre CPython
  « standalone », le même partout. Les cinq jobs mesureraient alors le réseau
  de GitHub, pas les cinq distributions.
* Sans ``DSOXLAB_E2E_WHEEL``, chaque distribution reconstruirait sa roue. On
  éprouverait cinq artefacts au lieu de celui que PyPI sert, et un défaut
  d'empaquetage pourrait se cacher derrière une construction qui, là, marche.

D'où ces tests sur la composition de la commande : ils coûtent une milliseconde
et attrapent la seule régression que la CI ne peut pas voir elle-même.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import ModuleType

RACINE = Path(__file__).resolve().parent.parent


def _script() -> ModuleType:
    """Le script chargé par son chemin : `scripts/` n'est pas un paquet.

    C'est volontaire (rien n'y est importable par le produit), donc le test
    passe par importlib plutôt que de transformer l'outillage en dépendance.
    """
    chemin = RACINE / "scripts" / "parcours-distribution.py"
    spec = importlib.util.spec_from_file_location("parcours_distribution", chemin)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_uv_ne_telecharge_jamais_son_propre_python() -> None:
    """Sinon la matrice mesure le réseau de GitHub, pas cinq distributions."""
    argv = _script()._argv_docker(
        "debian:13", RACINE, RACINE / "dist" / "dsoxlab-0.0.0-py3-none-any.whl", "true"
    )

    assert "UV_PYTHON_DOWNLOADS=never" in argv


def test_la_roue_est_fournie_et_jamais_reconstruite() -> None:
    """Une seule roue pour cinq systèmes : c'est ce qui rend l'écart lisible."""
    argv = _script()._argv_docker(
        "fedora:latest", RACINE, RACINE / "dist" / "dsoxlab-0.0.0-py3-none-any.whl", "true"
    )

    fourniture = [a for a in argv if a.startswith("DSOXLAB_E2E_WHEEL=")]
    assert fourniture == ["DSOXLAB_E2E_WHEEL=/travail/dist/dsoxlab-0.0.0-py3-none-any.whl"]


def test_le_depot_n_est_monte_qu_en_lecture() -> None:
    """Le parcours d'un utilisateur n'écrit pas dans les sources de l'outil.

    Le montage en lecture seule est ce qui le prouve : le jour où la suite en a
    besoin, elle échoue ici plutôt que de laisser passer un défaut réel.
    """
    argv = _script()._argv_docker(
        "archlinux:latest", RACINE, RACINE / "dist" / "roue.whl", "true"
    )

    montages = [argv[i + 1] for i, a in enumerate(argv) if a == "-v"]
    assert montages == [f"{RACINE}:/travail:ro"]


def test_un_amorcage_en_echec_arrete_tout() -> None:
    """`set -e` en tête : sans lui, la suite tournerait sur un Python absent,
    et le message d'erreur ne parlerait plus de la distribution."""
    commande = _script()._commande_conteneur("apt-get install python3", "/travail/x.whl")

    assert commande.splitlines()[0] == "set -e"
    assert "apt-get install python3" in commande
