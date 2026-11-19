"""`challenge` affiche un énoncé même sans `challenge/README.md`.

La commande ne lisait que `challenge/README.md`. Mesuré le 2026-11-19 sur le
disque : 229 labs de six catalogues n'ont pas ce fichier, dont les 156 du
catalogue Kubernetes. Pour eux, `challenge` n'affichait qu'un avertissement,
alors que leur énoncé (« ce qu'il faut obtenir ») est dans `scenario.md`, un
fichier que `validate-structure` exige. Un lecteur l'a signalé
(blog-roadmap#198).

On interroge la fonction qui choisit le fichier, pas le rendu Rich.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from dsoxlab.models.lab import LabDefinition, ValidationConfig
from dsoxlab.models.runtime import RuntimeConfig, RuntimeType
from dsoxlab.reporting.console import enonce_du_challenge


def _lab(chemin: Path) -> LabDefinition:
    return LabDefinition(
        id="demo",
        title="Demo",
        level="l1",
        path=chemin,
        doc_url="https://example.test/guide",
        runtime=RuntimeConfig(type=RuntimeType.SHELL, workdir="challenge/work"),
        skills=["x"],
        distros=["debian13"],
        validation=ValidationConfig(),
    )


def _poser(racine: Path, *relatifs: str) -> None:
    for relatif in relatifs:
        fichier = racine / relatif
        fichier.parent.mkdir(parents=True, exist_ok=True)
        fichier.write_text(f"# {relatif}\n", encoding="utf-8")


@pytest.mark.parametrize(
    ("presents", "lang", "attendu"),
    [
        # Le cas du lecteur : aucun challenge/README, l'énoncé est le scénario.
        (["scenario.md", "scenario.fr.md"], "fr", "scenario.fr.md"),
        (["scenario.md", "scenario.fr.md"], "en", "scenario.md"),
        (["scenario.md"], "fr", "scenario.md"),
        # Un challenge/README écrit garde la priorité sur le scénario.
        (["scenario.md", "challenge/README.md"], "en", "challenge/README.md"),
        (
            ["scenario.fr.md", "challenge/README.md", "challenge/README.fr.md"],
            "fr",
            "challenge/README.fr.md",
        ),
        (["scenario.fr.md", "challenge/README.md"], "fr", "challenge/README.md"),
    ],
)
def test_le_fichier_affiche(
    tmp_path: Path, presents: list[str], lang: str, attendu: str
) -> None:
    _poser(tmp_path, *presents)
    assert enonce_du_challenge(_lab(tmp_path), lang) == tmp_path / attendu


def test_sans_aucun_enonce_le_choix_est_vide_aussi(tmp_path: Path) -> None:
    """Le message d'absence ne reste que pour un lab qui n'a vraiment rien."""
    _poser(tmp_path, "README.md")
    assert enonce_du_challenge(_lab(tmp_path), "fr") is None
