"""L'invitation au premier ``push``, une fois par machine (brief gamification, lot A).

Après la première tentative enregistrée (``check`` ou ``submit``), la CLI dit à
l'apprenant comment retrouver son résultat sur le site, sans rien envoyer. Ces
tests tiennent les conditions convenues avec la session du site le
2026-11-16 : une seule fois, tentative mesurée, catalogue qui déclare un
portail, terminal seulement, jamais avec ``--json``, aucun réseau, ligne
``login`` absente quand une session de ce portail existe, et un code de sortie
qui ne bouge pas.
"""

from __future__ import annotations

import socket
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest
from typer.testing import CliRunner

from dsoxlab.cli import app
from dsoxlab.services import invitation_push
from dsoxlab.services.lab_service import CheckResult

_LAB = """\
id: lab-a
title: Demo lab
level: beginner
skills: [demo]
distros: [any]
doc_url: https://example.org/docs/demo/
runtime:
  type: shell
  workdir: challenge/work
"""

_META = """\
repo:
  id: depot-demo
  category: demo
"""

_SYNC = """\
learning:
  sync:
    protocol: "learner-sync/1"
    api: "https://api.example.org"
    issuer: "https://issuer.example.org/pool"
    oauth_domain: "https://connexion.example.org"
    client_id: "abc123"
    callback_url: "https://www.example.org/auth/cli/"
"""


@pytest.fixture(autouse=True)
def _poste_isole(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Rien ne touche l'état de la machine qui joue les tests."""
    import dsoxlab.i18n as i18n

    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "state"))
    monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path / "cache"))
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "data"))
    monkeypatch.setenv("DSOXLAB_LANG", "en")
    monkeypatch.setenv("DSOXLAB_NO_UPDATE_CHECK", "1")
    monkeypatch.delenv("LAB_HOME", raising=False)
    monkeypatch.setattr(i18n, "_strings", None)


@pytest.fixture
def sans_reseau(monkeypatch: pytest.MonkeyPatch) -> None:
    """Toute ouverture de socket fait échouer le test : l'invitation n'envoie rien."""

    def interdit(*_a: object, **_k: object) -> None:
        raise AssertionError("l'invitation a tenté d'ouvrir une connexion réseau")

    monkeypatch.setattr(socket, "socket", interdit)
    monkeypatch.setattr(socket, "create_connection", interdit)


def _catalogue(racine: Path, *, portail: bool = True) -> Path:
    lab = racine / "labs" / "demo" / "lab-a"
    (lab / "challenge" / "tests").mkdir(parents=True)
    (racine / "meta.yml").write_text(_META + (_SYNC if portail else ""), encoding="utf-8")
    (lab / "lab.yaml").write_text(_LAB, encoding="utf-8")
    (lab / "README.md").write_text("# lab-a\n", encoding="utf-8")
    (lab / "challenge" / "README.md").write_text("challenge\n", encoding="utf-8")
    (lab / "challenge" / "tests" / "test_functional.py").write_text(
        "def test_ok():\n    assert True\n", encoding="utf-8"
    )
    return racine


def _jouer(racine: Path, monkeypatch: pytest.MonkeyPatch, commande: str, resultat: CheckResult,
           *, terminal: bool = True, options: list[str] | None = None) -> Any:
    from dsoxlab.cli import progression

    score = 100 if resultat.ok else 40
    monkeypatch.setattr(progression, "_run_check", lambda *a, **k: (resultat, score, 100))
    monkeypatch.setattr(invitation_push, "terminal", lambda: terminal)
    return CliRunner().invoke(
        app, [commande, "lab-a", "--lab-home", str(racine), *(options or [])]
    )


REUSSI = CheckResult(True, "", 5, 5)
RATE = CheckResult(False, "", 2, 5)
INVITATION = "No result is sent without your action."


# ── Le service, sans CLI ─────────────────────────────────────────────────────


def test_le_service_invite_sur_un_catalogue_avec_portail(
    tmp_path: Path, sans_reseau: None
) -> None:
    racine = _catalogue(tmp_path / "c")
    assert invitation_push.a_proposer(racine, mesuree=True, terminal=True) == (
        invitation_push.Invitation(avec_login=True)
    )


@pytest.mark.parametrize(("mesuree", "terminal"), [(False, True), (True, False)])
def test_ni_tentative_non_mesuree_ni_hors_terminal(
    tmp_path: Path, mesuree: bool, terminal: bool
) -> None:
    racine = _catalogue(tmp_path / "c")
    assert invitation_push.a_proposer(racine, mesuree=mesuree, terminal=terminal) is None


def test_rien_pour_un_catalogue_qui_n_a_pas_de_portail(tmp_path: Path, sans_reseau: None) -> None:
    racine = _catalogue(tmp_path / "c", portail=False)
    assert invitation_push.a_proposer(racine, mesuree=True, terminal=True) is None


def test_rien_quand_le_marqueur_existe(tmp_path: Path) -> None:
    racine = _catalogue(tmp_path / "c")
    invitation_push.marquer_comme_affichee("0.0.0")
    assert invitation_push.chemin_du_marqueur().is_file()
    assert str(invitation_push.chemin_du_marqueur()).startswith(str(tmp_path / "state"))
    assert invitation_push.a_proposer(racine, mesuree=True, terminal=True) is None


def test_pas_de_ligne_login_quand_une_session_de_ce_portail_existe(
    tmp_path: Path, sans_reseau: None
) -> None:
    from dsoxlab.sync import jetons

    racine = _catalogue(tmp_path / "c")
    jetons.ecrire(jetons.Session(
        emetteur="https://issuer.example.org/pool", acces="a",
        expire_le=datetime.now(UTC) - timedelta(hours=1),  # expirée : rien n'est rafraîchi
        rafraichissement="r", api="https://api.example.org",
        domaine="https://connexion.example.org", client_id="abc123",
    ))
    assert invitation_push.a_proposer(racine, mesuree=True, terminal=True) == (
        invitation_push.Invitation(avec_login=False)
    )


def test_une_session_d_un_autre_portail_garde_la_ligne_login(
    tmp_path: Path, sans_reseau: None
) -> None:
    from dsoxlab.sync import jetons

    racine = _catalogue(tmp_path / "c")
    jetons.ecrire(jetons.Session(
        emetteur="https://issuer.example.org/pool", acces="a",
        expire_le=datetime.now(UTC) + timedelta(hours=1), rafraichissement="r",
        api="https://autre-api.example.org", domaine="https://connexion.example.org",
        client_id="abc123",
    ))
    invitation = invitation_push.a_proposer(racine, mesuree=True, terminal=True)
    assert invitation is not None and invitation.avec_login


# ── La CLI : check et submit ─────────────────────────────────────────────────


@pytest.mark.parametrize(("resultat", "code"), [(REUSSI, 0), (RATE, 1)])
def test_check_invite_une_seule_fois_sans_changer_le_code_de_sortie(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, sans_reseau: None,
    resultat: CheckResult, code: int,
) -> None:
    racine = _catalogue(tmp_path / "c")
    premier = _jouer(racine, monkeypatch, "check", resultat)
    second = _jouer(racine, monkeypatch, "check", resultat)
    assert premier.exit_code == code and second.exit_code == code
    assert premier.output.count(INVITATION) == 1, premier.output
    assert "dsoxlab push --dry-run" in premier.output
    assert "dsoxlab login" in premier.output
    assert INVITATION not in second.output


def test_check_json_n_invite_jamais(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, sans_reseau: None
) -> None:
    racine = _catalogue(tmp_path / "c")
    sortie = _jouer(racine, monkeypatch, "check", REUSSI, options=["--json"])
    assert INVITATION not in sortie.output
    assert not invitation_push.chemin_du_marqueur().exists()


def test_hors_terminal_rien_n_est_affiche_ni_consomme(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, sans_reseau: None
) -> None:
    racine = _catalogue(tmp_path / "c")
    sortie = _jouer(racine, monkeypatch, "check", REUSSI, terminal=False)
    assert INVITATION not in sortie.output
    assert not invitation_push.chemin_du_marqueur().exists()


def test_submit_invite_apres_le_lien_de_remise_et_check_ne_reinvite_pas(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, sans_reseau: None
) -> None:
    racine = _catalogue(tmp_path / "c")
    soumis = _jouer(racine, monkeypatch, "submit", REUSSI)
    assert soumis.exit_code == 0
    assert soumis.output.count(INVITATION) == 1, soumis.output
    assert INVITATION not in _jouer(racine, monkeypatch, "check", REUSSI).output


def test_une_tentative_non_mesuree_n_invite_pas(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, sans_reseau: None
) -> None:
    racine = _catalogue(tmp_path / "c")
    sortie = _jouer(racine, monkeypatch, "check", CheckResult(True, "", 0, 0))
    assert INVITATION not in sortie.output
    assert not invitation_push.chemin_du_marqueur().exists()


def test_les_cles_existent_en_anglais_et_en_francais() -> None:
    from dsoxlab.i18n.strings import en, fr

    cles = ("push_invite_saved", "push_invite_where", "push_invite_cmd_login",
            "push_invite_cmd_push", "push_invite_dry_run", "push_invite_nothing_sent")
    for cle in cles:
        assert cle in en.STRINGS and cle in fr.STRINGS, cle
    assert "My learning" in en.STRINGS["push_invite_where"]
    assert "Mon apprentissage" in fr.STRINGS["push_invite_where"]
    assert fr.STRINGS["push_invite_nothing_sent"] == "Aucun résultat n'est envoyé sans votre action."
