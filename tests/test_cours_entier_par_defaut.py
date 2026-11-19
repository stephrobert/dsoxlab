"""`course` affiche tout le cours par défaut, et le pager garde la page lue.

Issue #396, 2026-11-19, en lisant le premier cours Kubernetes fait
d'exercices (11 sections) : `course` n'en servait qu'une à la fois, il fallait
relancer `--next` dix fois, et `q` effaçait ce qu'on venait de lire.

On observe ce que la commande DEMANDE à afficher (le cours entier ou une
section), en remplaçant les deux fonctions d'affichage : un test qui lirait le
rendu Rich mesurerait la mise en page, pas le comportement.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from typer.testing import CliRunner

from dsoxlab.cli import app, parcours

runner = CliRunner()

#: Quatre exercices de taille raisonnable : assez pour que le découpage
#: automatique en tire des sections.
COURS = "# Le premier\n\nChapeau.\n\n" + "".join(
    f"## Exercice {n}\n\n" + "Une ligne de cours.\n" * 10 + "\n" for n in range(1, 5)
)


@pytest.fixture
def affichages(catalogue: Path, monkeypatch: pytest.MonkeyPatch) -> list[str]:
    (catalogue / "labs" / "domaine" / "premier" / "README.md").write_text(COURS, encoding="utf-8")
    vus: list[str] = []
    monkeypatch.setattr(parcours, "print_lab_course", lambda lab, lang="en": vus.append("cours entier"))
    monkeypatch.setattr(
        parcours, "_show_course_section",
        lambda root, lab, manifest, position: vus.append(f"section {position}"),
    )
    monkeypatch.setattr(parcours, "print_course_toc", lambda lab, manifest: vus.append("sommaire"))
    return vus


def test_sans_option_le_cours_est_entier(affichages: list[str]) -> None:
    resultat = runner.invoke(app, ["course", "premier", "--no-pager"])
    assert resultat.exit_code == 0, resultat.output
    assert affichages == ["cours entier"]


def test_all_reste_accepte(affichages: list[str]) -> None:
    resultat = runner.invoke(app, ["course", "premier", "--all", "--no-pager"])
    assert resultat.exit_code == 0, resultat.output
    assert affichages == ["cours entier"]


def test_le_decoupage_reste_disponible_sur_demande(affichages: list[str]) -> None:
    resultat = runner.invoke(app, ["course", "premier", "--section", "2", "--no-pager"])
    assert resultat.exit_code == 0, resultat.output
    assert affichages == ["section 2"]

    # `_show_course_section`, remplacée ici, est ce qui enregistre la position :
    # sans elle, `--next` repart de la première section. Ce qui compte, c'est
    # qu'il serve UNE section, et non le cours entier.
    affichages.clear()
    resultat = runner.invoke(app, ["course", "premier", "--next", "--no-pager"])
    assert resultat.exit_code == 0, resultat.output
    assert affichages == ["section 1"]
