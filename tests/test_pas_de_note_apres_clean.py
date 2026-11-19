"""Après `clean`, un lab n'a plus rien à noter, jusqu'au prochain `run`.

Relevé par Stéphane le 2026-11-19 sur `k8s-installer-kubectl` : le nettoyage
réinstalle le kubectl du socle (en 1.37, dans `/usr/local/bin`, avec sa
complétion), dont les labs suivants ont besoin. C'est aussi ce que le challenge
demande. `dsoxlab clean` puis `dsoxlab check` rendaient donc 83/100 sans aucun
travail. Les tests lisent l'état de la machine et ne peuvent pas savoir qui l'a
posé : c'est le moteur qui refuse de noter un lab nettoyé.

Le refus passe par `check` et `submit`, avant toute exécution des tests : on
l'observe en remplaçant `_run_check`, qui ne doit jamais être appelé.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from typer.testing import CliRunner

from dsoxlab.cli import app, progression
from dsoxlab.services import lab_state

runner = CliRunner()


@pytest.fixture
def notes(catalogue: Path, monkeypatch: pytest.MonkeyPatch) -> list[str]:
    """Les labs dont `check` ou `submit` a vraiment lancé les tests."""
    lances: list[str] = []

    def faux_check(root: Path, lab: Any, target: Any, quiet: bool = False) -> Any:
        lances.append(lab.id)
        raise SystemExit(0)

    monkeypatch.setattr(progression, "_run_check", faux_check)
    return lances


def test_la_marque_vit_de_clean_au_run_suivant(catalogue: Path) -> None:
    from dsoxlab.discovery.scanner import discover_labs

    lab = next(lab for lab in discover_labs(catalogue) if lab.id == "premier")
    assert not lab_state.est_nettoye(catalogue, "premier")
    lab_state.marquer_nettoye(catalogue, "premier")
    assert lab_state.est_nettoye(catalogue, "premier")
    lab_state.enregistrer_depart(catalogue, lab)
    assert not lab_state.est_nettoye(catalogue, "premier")


def test_check_et_submit_refusent_un_lab_nettoye(catalogue: Path, notes: list[str]) -> None:
    resultat = runner.invoke(app, ["clean", "premier", "--yes"])
    assert resultat.exit_code == 0, resultat.output

    for commande in ("check", "submit"):
        resultat = runner.invoke(app, [commande, "premier"])
        assert resultat.exit_code == 2, resultat.output
    assert notes == [], "aucun test ne doit tourner sur un lab nettoyé"


def test_un_lab_jamais_nettoye_reste_bien_notable(catalogue: Path, notes: list[str]) -> None:
    """Un lab lancé avant cette version n'a pas de marque : il se note."""
    runner.invoke(app, ["check", "premier"])
    assert notes == ["premier"]


def test_le_nettoyage_d_un_lab_ne_bloque_pas_les_autres(
    catalogue: Path, notes: list[str]
) -> None:
    runner.invoke(app, ["clean", "premier", "--yes"])
    runner.invoke(app, ["check", "second"])
    assert notes == ["second"]


def test_reset_rend_le_lab_notable(catalogue: Path, notes: list[str]) -> None:
    """`reset` est le geste de fin d'un cours : il doit rendre le lab notable."""
    runner.invoke(app, ["clean", "premier", "--yes"])
    resultat = runner.invoke(app, ["reset", "premier", "--yes"])
    assert resultat.exit_code == 0, resultat.output
    assert not lab_state.est_nettoye(catalogue, "premier")
    runner.invoke(app, ["check", "premier"])
    assert notes == ["premier"]
