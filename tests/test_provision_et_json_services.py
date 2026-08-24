"""Deux échecs qui ne se disaient pas (issues #170 et #171).

Le premier : `provision` traitait un délai d'attente dépassé par un simple
avertissement, puis annonçait « ✔ N hôtes provisionnés » et sortait en 0.
L'infrastructure existait, mais elle n'était pas utilisable, et le `run` suivant
échouait en « unreachable » sans lien visible avec la cause. Tout script qui
teste le code de retour était aveugle.

Le second : `check --json` sur un lab déclarant des services faisait précéder
son document de « ℹ Démarrage du service… », si bien que `| jq` échouait. C'est
le défaut corrigé en 0.1.23, revenu par une porte latérale — `_valider` ne
propageait pas `quiet` à `_ensure_services`.

Les deux relèvent de la même règle : la sortie standard porte le document, et
une commande ne conclut pas au succès sur ce qu'elle n'a pas constaté.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import typer

from dsoxlab.models.lab import LabDefinition

_BASE = """\
id: l1-demo
title: Demo lab
level: beginner
skills: [demo]
distros: [any]
doc_url: https://example.org/docs/demo/
"""


def _lab_avec_service(tmp_path: Path) -> LabDefinition:
    chemin = tmp_path / "lab.yaml"
    chemin.write_text(
        _BASE
        + "runtime:\n  type: shell\n  workdir: challenge/work\n"
        + "  services:\n    - name: db\n      image: postgres:16\n",
        encoding="utf-8",
    )
    return LabDefinition.from_yaml(chemin)


# ── #171 : le document, et rien d'autre ─────────────────────────────────────

def test_le_demarrage_des_services_se_tait_en_mode_machine(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str],
) -> None:
    """Le défaut prouvé par exécution : « ℹ Démarrage du service… » précédait le JSON."""
    from dsoxlab.cli import _commun
    from dsoxlab.runtimes import services as svc

    lab = _lab_avec_service(tmp_path)
    # `_ensure_services` importe le module dans son corps : c'est donc le module
    # source qu'il faut patcher, pas un attribut de l'appelant.
    monkeypatch.setattr(svc, "docker_available", lambda: True)
    monkeypatch.setattr(svc, "start",
                        lambda service, repo, **kw: "conteneur")

    _commun._ensure_services(lab, tmp_path, quiet=True)

    lu = capsys.readouterr()
    assert lu.out == "", f"stdout doit rester vide en mode machine : {lu.out!r}"


def test_le_demarrage_des_services_se_dit_en_mode_normal(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str],
) -> None:
    """L'autre bout : sans `--json`, l'apprenant doit voir ce qui démarre.

    Un lab qui met dix secondes à lever ses conteneurs sans rien afficher
    passerait pour figé.
    """
    from dsoxlab.cli import _commun
    from dsoxlab.runtimes import services as svc

    lab = _lab_avec_service(tmp_path)
    # `_ensure_services` importe le module dans son corps : c'est donc le module
    # source qu'il faut patcher, pas un attribut de l'appelant.
    monkeypatch.setattr(svc, "docker_available", lambda: True)
    monkeypatch.setattr(svc, "start",
                        lambda service, repo, **kw: "conteneur")

    _commun._ensure_services(lab, tmp_path, quiet=False)

    assert "db" in capsys.readouterr().out


def test_un_service_en_echec_se_dit_meme_en_mode_machine(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str],
) -> None:
    """`quiet` fait taire le PROGRÈS, jamais les erreurs.

    Elles partent sur stderr, que le document ne traverse pas : un service qui
    refuse de démarrer doit se dire dans les deux modes, sinon `--json` masque
    la seule information qui compte.
    """
    from dsoxlab.cli import _commun
    from dsoxlab.runtimes import services as svc

    lab = _lab_avec_service(tmp_path)
    monkeypatch.setattr(svc, "docker_available", lambda: True)

    def _echoue(service: object, repo: str, **kw: object) -> str:
        raise svc.ServiceError("le conteneur ne démarre pas")

    monkeypatch.setattr(svc, "start", _echoue)

    # `typer.Exit` n'est pas un `SystemExit` : c'est une exception de click,
    # convertie en code de sortie par le runner.
    with pytest.raises(typer.Exit):
        _commun._ensure_services(lab, tmp_path, quiet=True)

    lu = capsys.readouterr()
    assert lu.out == "", "le document ne doit pas être pollué"
    assert "démarre pas" in lu.err or "start" in lu.err.lower(), (
        "l'échec doit rester visible sur stderr"
    )


# ── #170 : un code de sortie pour un délai dépassé ──────────────────────────

def test_le_code_de_sortie_des_hotes_injoignables_est_distinct() -> None:
    """Un code dédié, comme 5 et 6 le sont pour les orphelins.

    Sans lui, `provision` sortait en 0 après avoir renoncé à attendre, et aucun
    script — ni la construction d'une image — ne pouvait s'en apercevoir.
    """
    from dsoxlab.infra.inventory import EXIT_HOTES_INJOIGNABLES
    from dsoxlab.interrupt import EXIT_INTERRUPTED
    from dsoxlab.locking import EXIT_LOCKED

    assert EXIT_HOTES_INJOIGNABLES not in (0, 1, 5, 6, EXIT_LOCKED, EXIT_INTERRUPTED), (
        "le code doit se distinguer de ceux déjà attribués"
    )
