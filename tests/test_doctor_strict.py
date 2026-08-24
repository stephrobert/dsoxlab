"""`doctor` devient utilisable comme portail, sans cesser d'être un diagnostic (#176).

`cli/diagnostic.py` sortait en 0 quel que soit l'état des contrôles, y compris
« requis ». Le choix était assumé en commentaire, et il se défend pour un usage
interactif : un diagnostic n'est pas un échec. Mais il rendait `doctor`
inutilisable comme **portail automatisé** — un script devait analyser le JSON
pour savoir si quelque chose manquait.

`--strict` traduit le diagnostic en code de sortie, et **deux** codes plutôt
qu'un : `9` quand un requis a échoué, `10` quand un requis n'a pas pu être
mesuré. Les deux appellent des gestes différents — réparer, ou refaire la
mesure — et surtout, un environnement dont une sonde n'a pas abouti n'est pas
validé pour autant. C'est exactement ce qu'une construction d'image ne doit pas
confondre avec un succès.

Le comportement par défaut ne bouge pas : c'est la moitié du contrat.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from typer.testing import CliRunner

from dsoxlab.cli import app
from dsoxlab.services.doctor import (
    EXIT_DOCTOR_INDETERMINE,
    EXIT_DOCTOR_REQUIS_KO,
    STATE_UNKNOWN,
    Check,
    DoctorReport,
)

runner = CliRunner()


def _depot(tmp_path: Path) -> Path:
    (tmp_path / "labs").mkdir(exist_ok=True)
    (tmp_path / "meta.yml").write_text("repo:\n  id: essai\n  category: essai\n",
                                       encoding="utf-8")
    return tmp_path


def _check(key: str, *, ok: bool, state: str = "") -> Check:
    """`state` est dérivé de `ok` ; seul `forced_state` le contraint."""
    return Check(key=key, label=key, ok=ok, detail="",
                 forced_state=state or None)


def _rapport(*checks: Check) -> DoctorReport:
    rapport = DoctorReport()
    rapport.required.extend(checks)
    return rapport


def _imposer(monkeypatch: pytest.MonkeyPatch, rapport: DoctorReport) -> None:
    """Fixe le diagnostic, pour ne pas dépendre de la machine qui joue les tests."""
    from dsoxlab.cli import diagnostic

    monkeypatch.setattr(diagnostic, "collect_checks", lambda root, meta: rapport)


# ── Les deux codes, un par situation ────────────────────────────────────────

def test_un_requis_en_echec_sort_en_neuf(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    _imposer(monkeypatch, _rapport(_check("python", ok=True),
                                   _check("terraform", ok=False)))

    resultat = runner.invoke(app, ["doctor", "--strict",
                                   "--lab-home", str(_depot(tmp_path))])

    assert resultat.exit_code == EXIT_DOCTOR_REQUIS_KO


def test_un_requis_non_mesure_sort_en_dix(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Une sonde qui n'a rien pu établir ne vaut pas un feu vert.

    C'est la moitié du travail : sans ce code, un script conclurait « tout va
    bien » sur une mesure qui n'a pas eu lieu.
    """
    _imposer(monkeypatch, _rapport(_check("python", ok=True),
                                   _check("libvirt_pool", ok=False,
                                          state=STATE_UNKNOWN)))

    resultat = runner.invoke(app, ["doctor", "--strict",
                                   "--lab-home", str(_depot(tmp_path))])

    assert resultat.exit_code == EXIT_DOCTOR_INDETERMINE


def test_l_echec_etabli_l_emporte_sur_l_indetermine(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Une certitude est plus forte qu'une ignorance."""
    _imposer(monkeypatch, _rapport(_check("terraform", ok=False),
                                   _check("libvirt_pool", ok=False,
                                          state=STATE_UNKNOWN)))

    resultat = runner.invoke(app, ["doctor", "--strict",
                                   "--lab-home", str(_depot(tmp_path))])

    assert resultat.exit_code == EXIT_DOCTOR_REQUIS_KO


def test_un_environnement_sain_sort_en_zero(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    _imposer(monkeypatch, _rapport(_check("python", ok=True),
                                   _check("pytest", ok=True)))

    resultat = runner.invoke(app, ["doctor", "--strict",
                                   "--lab-home", str(_depot(tmp_path))])

    assert resultat.exit_code == 0


def test_un_informatif_en_echec_ne_fait_pas_echouer(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    """`ok` ne porte que sur `required`, et `--strict` non plus.

    Un hyperviseur que ce catalogue n'utilisera jamais n'a pas à faire échouer
    un portail. C'est l'invariant d'agnosticisme, appliqué au code de sortie.
    """
    rapport = _rapport(_check("python", ok=True))
    rapport.optional.append(_check("incus", ok=False))
    _imposer(monkeypatch, rapport)

    resultat = runner.invoke(app, ["doctor", "--strict",
                                   "--lab-home", str(_depot(tmp_path))])

    assert resultat.exit_code == 0


# ── Le défaut ne bouge pas : c'est l'autre moitié du contrat ───────────────

def test_sans_l_option_le_code_reste_zero(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Un diagnostic n'est pas un échec, et c'est un choix, pas un oubli."""
    _imposer(monkeypatch, _rapport(_check("terraform", ok=False)))

    resultat = runner.invoke(app, ["doctor", "--lab-home", str(_depot(tmp_path))])

    assert resultat.exit_code == 0


def test_sans_l_option_le_json_sort_en_zero_aussi(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    """`--json` change la forme, jamais le verdict ni le code."""
    _imposer(monkeypatch, _rapport(_check("terraform", ok=False)))

    resultat = runner.invoke(app, ["doctor", "--json",
                                   "--lab-home", str(_depot(tmp_path))])

    assert resultat.exit_code == 0


# ── Les deux options se combinent, et l'ordre compte ───────────────────────

def test_le_document_json_est_rendu_avant_le_code(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Un appelant qui reçoit 9 doit encore pouvoir lire ce qui n'allait pas.

    Sortir avant d'écrire le document le priverait de la seule information qui
    lui permet d'agir.
    """
    import json

    _imposer(monkeypatch, _rapport(_check("python", ok=True),
                                   _check("terraform", ok=False)))

    resultat = runner.invoke(app, ["doctor", "--strict", "--json",
                                   "--lab-home", str(_depot(tmp_path))])

    assert resultat.exit_code == EXIT_DOCTOR_REQUIS_KO
    document = json.loads(resultat.stdout)
    assert document["ok"] is False
    assert [c["key"] for c in document["required"] if not c["ok"]] == ["terraform"]


def test_les_deux_codes_ne_collisionnent_avec_aucun_autre() -> None:
    """Le projet donne un code dédié à chaque chemin d'échec : ils sont uniques."""
    from dsoxlab.infra.inventory import EXIT_HOTES_INJOIGNABLES
    from dsoxlab.interrupt import EXIT_INTERRUPTED
    from dsoxlab.locking import EXIT_LOCKED

    pris = {0, 1, 2, 5, 6, EXIT_LOCKED, EXIT_HOTES_INJOIGNABLES, EXIT_INTERRUPTED}

    assert EXIT_DOCTOR_REQUIS_KO not in pris
    assert EXIT_DOCTOR_INDETERMINE not in pris
    assert EXIT_DOCTOR_REQUIS_KO != EXIT_DOCTOR_INDETERMINE
