"""L'énoncé d'un lab vit dans `challenge/README.md`, et nulle part ailleurs.

`dsoxlab challenge` ne lisait que ce fichier, absent de 229 labs de six
catalogues le 2026-11-19 (blog-roadmap#198). Décision du même jour : il devient
le seul porteur de la situation et de la mission, `scenario.md` quitte le
contrat, et `validate-structure` exige l'un et refuse l'autre.

On interroge la fonction qui choisit le fichier, pas le rendu Rich.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from dsoxlab.models.lab import LabDefinition, ValidationConfig
from dsoxlab.models.runtime import RuntimeConfig, RuntimeType
from dsoxlab.reporting.console import enonce_du_challenge
from dsoxlab.validators.structure import validate_structure


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
        (["challenge/README.md", "challenge/README.fr.md"], "fr", "challenge/README.fr.md"),
        (["challenge/README.md", "challenge/README.fr.md"], "en", "challenge/README.md"),
        # Une traduction absente n'est pas une faute : l'anglais est affiché.
        (["challenge/README.md"], "fr", "challenge/README.md"),
    ],
)
def test_le_fichier_affiche(
    tmp_path: Path, presents: list[str], lang: str, attendu: str
) -> None:
    _poser(tmp_path, *presents)
    assert enonce_du_challenge(_lab(tmp_path), lang) == tmp_path / attendu


def test_un_scenario_restant_n_est_plus_lu(tmp_path: Path) -> None:
    """Un `scenario.md` oublié n'est pas un énoncé : le validateur le refuse."""
    _poser(tmp_path, "README.md", "scenario.md", "scenario.fr.md")
    assert enonce_du_challenge(_lab(tmp_path), "fr") is None


def test_validate_structure_exige_l_enonce_et_refuse_le_scenario(tmp_path: Path) -> None:
    _poser(tmp_path, "lab.yaml", "README.md", "scenario.md",
           "challenge/tests/test_functional.py")
    cles = sorted(i.key for i in validate_structure(_lab(tmp_path)).issues)
    assert cles == ["struct_forbidden_scenario", "struct_missing_file"]

    (tmp_path / "scenario.md").unlink()
    _poser(tmp_path, "challenge/README.md")
    assert validate_structure(_lab(tmp_path)).ok
