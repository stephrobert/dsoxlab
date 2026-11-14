"""``validate-structure`` nomme chaque défaut, pas seulement sa conclusion (issue #335).

Mesuré sur un catalogue réel : deux ``doc_url`` en 404 sous ``--check-urls``
faisaient sortir la commande en 1 avec la seule ligne « Some labs have structure
or metadata issues. ». Le détail n'existait que dans ``--json``, et le journal
de CI d'un catalogue ne donnait aucune piste.

Le réseau n'est pas joué : ``check_doc_urls`` est simulé.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from typer.testing import CliRunner

from dsoxlab.cli import app
from dsoxlab.services.scaffold import creer_catalogue, creer_lab
from dsoxlab.validators import content
from dsoxlab.validators.content import ContentIssue

runner = CliRunner()

_URL = "https://example.test/docs/une/page/assez/longue/pour/depasser/quatre-vingts/colonnes/"


@pytest.fixture
def catalogue(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setenv("HOME", str(tmp_path / "maison"))
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "etat"))
    monkeypatch.setenv("DSOXLAB_LANG", "en")
    monkeypatch.setenv("DSOXLAB_NO_UPDATE_CHECK", "1")
    racine = creer_catalogue("detail", tmp_path).racine
    creer_lab("lab-fautif", racine, runtime="shell")
    creer_lab("lab-sain", racine, runtime="shell")
    return racine


def test_le_catalogue_du_banc_est_conforme(catalogue: Path) -> None:
    """Sans lui, le test suivant pourrait réussir pour une autre anomalie."""
    resultat = runner.invoke(app, ["validate-structure", "--lab-home", str(catalogue)])
    assert resultat.exit_code == 0, resultat.output


def test_une_doc_url_en_404_est_nommee_avec_son_lab_et_le_decompte(
    catalogue: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def _faux(labs: object, **_k: object) -> list[tuple[str, str, ContentIssue]]:
        souci = ContentIssue(
            catalogue / "labs" / "lab-fautif" / "lab.yaml",
            "content_doc_url_status", {"code": 404},
        )
        return [("lab-fautif", _URL, souci)]

    monkeypatch.setattr(content, "check_doc_urls", _faux)
    resultat = runner.invoke(
        app, ["validate-structure", "--check-urls", "--lab-home", str(catalogue)]
    )
    assert resultat.exit_code == 1, resultat.output
    lignes = resultat.output.splitlines()
    fautive = [ligne for ligne in lignes if "lab-fautif" in ligne]
    assert fautive, resultat.output
    # Sur UNE ligne, URL entière : c'est en CI, à 80 colonnes, qu'on la lit.
    assert "HTTP 404" in fautive[0] and _URL in fautive[0], resultat.output
    assert "1 lab(s) out of 2" in resultat.output
