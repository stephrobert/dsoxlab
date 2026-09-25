"""Les conteneurs qu'un service lance lui-même, et que personne ne retirait.

Un service qui reçoit le socket Docker en `run_args` crée ses propres conteneurs.
dsoxlab ne les a pas lancés, donc il ne les voyait pas : ils survivaient à
`clean` comme à l'arrêt du service, et retenaient leurs ports publiés.

Ce que cela coûtait (issue #239) : la création suivante échouait sur « Bind for
0.0.0.0:2201 failed: port is already allocated », à un endroit dont rien ne
remontait au lab. L'instance existait dans l'API mais n'atteignait jamais l'état
`running`, la solution de référence ne trouvait rien, et le lab paraissait cassé
sans raison. Trois conteneurs tournaient encore depuis 15 et 23 heures.

Deux points de conception sont testés ici plus que le nettoyage lui-même, parce
que ce sont eux qui peuvent détruire du travail : on ne retire **jamais** les
engendrés d'un conteneur réutilisé, et on épargne **toujours** les conteneurs de
dsoxlab.
"""

from __future__ import annotations

from typing import Any

import pytest

from dsoxlab.models.runtime import Service
from dsoxlab.runtimes import services as svc


class _Res:
    """Ce que `run_command` rend, réduit à ce que le code lit."""

    def __init__(self, ok: bool = True, stdout: str = "", stderr: str = "") -> None:
        self.ok = ok
        self.stdout = stdout
        self.stderr = stderr


def _mouchard(
    monkeypatch: pytest.MonkeyPatch, *, listes: str = "", liste_ok: bool = True
) -> list[list[str]]:
    """Enregistre les commandes docker jouées, et simule ce que `ps` rend."""
    jouees: list[list[str]] = []

    def _faux(cmd: list[str], **_kw: Any) -> _Res:
        jouees.append(cmd)
        if cmd[:2] == ["docker", "ps"]:
            return _Res(ok=liste_ok, stdout=listes, stderr="" if liste_ok else "boom")
        return _Res(True)

    monkeypatch.setattr(svc, "run_command", _faux)
    monkeypatch.setattr(svc.time, "sleep", lambda _s: None)
    return jouees


def _retires(jouees: list[list[str]]) -> list[str]:
    return [c[-1] for c in jouees if c[:3] == ["docker", "rm", "-f"]]


# ── le nettoyage lui-même ─────────────────────────────────────────────────────

def test_les_engendres_sont_retires(monkeypatch: pytest.MonkeyPatch) -> None:
    jouees = _mouchard(
        monkeypatch, listes="floci-ec2-i-aaa\nfloci-ec2-i-bbb\n"
    )
    service = Service(name="cloud", image="x", spawns=["floci-ec2-"])

    retires = svc.retirer_engendres(service)

    assert retires == ["floci-ec2-i-aaa", "floci-ec2-i-bbb"]
    assert _retires(jouees) == ["floci-ec2-i-aaa", "floci-ec2-i-bbb"]


def test_le_fragment_est_passe_tel_quel_a_docker(monkeypatch: pytest.MonkeyPatch) -> None:
    """C'est une sous-chaîne, pas un glob : le contrat le dit, le code s'y tient."""
    jouees = _mouchard(monkeypatch)
    svc.retirer_engendres(Service(name="cloud", image="x", spawns=["floci-ec2-"]))

    ps = next(c for c in jouees if c[:2] == ["docker", "ps"])
    assert "name=floci-ec2-" in ps
    assert "-a" in ps  # y compris les conteneurs arrêtés, qui retiennent leur port


def test_sans_spawns_aucune_commande_n_est_jouee(monkeypatch: pytest.MonkeyPatch) -> None:
    jouees = _mouchard(monkeypatch)

    assert svc.retirer_engendres(Service(name="db", image="postgres:16")) == []
    assert jouees == []


# ── les deux garde-fous, qui comptent plus que le nettoyage ───────────────────

def test_les_conteneurs_de_dsoxlab_sont_toujours_epargnes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Un fragment trop large ferait retirer par un service le conteneur d'un autre.

    `docker ps --filter name=` fait un match de sous-chaîne : un `spawns: ["d"]`
    ramènerait tout. Les conteneurs de services sont nommés `dsoxlab-<repo>-<nom>`,
    et ce préfixe les met hors d'atteinte.
    """
    jouees = _mouchard(
        monkeypatch,
        listes="dsoxlab-terraform-training-cloud\nfloci-ec2-i-aaa\ndsoxlab-autre-db\n",
    )

    retires = svc.retirer_engendres(Service(name="cloud", image="x", spawns=["-"]))

    assert retires == ["floci-ec2-i-aaa"]
    assert not any(n.startswith("dsoxlab-") for n in _retires(jouees))


def test_un_fragment_vide_est_ignore(monkeypatch: pytest.MonkeyPatch) -> None:
    """Il désignerait tous les conteneurs de la machine."""
    jouees = _mouchard(monkeypatch, listes="peu-importe\n")

    assert svc.retirer_engendres(Service(name="c", image="x", spawns=["", "   "])) == []
    assert jouees == []


def test_un_docker_qui_ne_repond_pas_ne_leve_pas(monkeypatch: pytest.MonkeyPatch) -> None:
    """Un nettoyage qui échoue ne doit pas empêcher le lab de tourner."""
    _mouchard(monkeypatch, listes="", liste_ok=False)

    assert svc.retirer_engendres(Service(name="c", image="x", spawns=["floci-"])) == []


# ── quand le nettoyage a lieu, et quand il n'a surtout pas lieu ───────────────

def test_un_conteneur_reutilise_garde_ses_engendres(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Le point le plus important de tout ce module.

    Si le conteneur du service tourne déjà avec la même configuration, ce qu'il a
    engendré depuis est le **travail en cours** de l'apprenant : les instances
    qu'il vient de créer. Les retirer là détruirait ce qu'il est en train de
    faire, et le contournement posé en `post_start` par les catalogues avait
    précisément ce défaut.
    """
    service = Service(name="cloud", image="x", spawns=["floci-ec2-"])
    jouees = _mouchard(monkeypatch, listes="floci-ec2-i-aaa\n")
    monkeypatch.setattr(svc, "_is_running", lambda _n: True)
    monkeypatch.setattr(
        svc, "_running_fingerprint", lambda _n: svc._config_fingerprint(service)
    )

    svc.start(service, "repo")

    assert _retires(jouees) == []


def test_un_conteneur_recree_perd_ses_engendres(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Le service repart de zéro : ce qu'il avait engendré n'est rattaché à rien."""
    jouees = _mouchard(monkeypatch, listes="floci-ec2-i-aaa\n")
    monkeypatch.setattr(svc, "_is_running", lambda _n: False)
    monkeypatch.setattr(svc, "_exists", lambda _n: False)
    monkeypatch.setattr(svc, "_wait_ready", lambda _s, _n: None)

    svc.start(Service(name="cloud", image="x", spawns=["floci-ec2-"]), "repo")

    assert "floci-ec2-i-aaa" in _retires(jouees)


def test_stop_retire_les_engendres_avec_le_service(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    jouees = _mouchard(monkeypatch, listes="floci-ec2-i-aaa\n")
    monkeypatch.setattr(svc, "_exists", lambda _n: True)

    assert svc.stop(Service(name="cloud", image="x", spawns=["floci-ec2-"]), "repo")

    retires = _retires(jouees)
    assert "floci-ec2-i-aaa" in retires
    assert "dsoxlab-repo-cloud" in retires


def test_stop_retire_les_engendres_meme_sans_service_debout(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """C'est tout le problème : les engendrés survivent au service.

    Un `clean` après une session interrompue trouve le service parti et ses
    enfants encore là.
    """
    jouees = _mouchard(monkeypatch, listes="floci-ec2-i-aaa\n")
    monkeypatch.setattr(svc, "_exists", lambda _n: False)

    assert not svc.stop(Service(name="cloud", image="x", spawns=["floci-ec2-"]), "repo")
    assert _retires(jouees) == ["floci-ec2-i-aaa"]


# ── le contrat ────────────────────────────────────────────────────────────────

def test_spawns_se_lit_dans_le_lab_yaml(tmp_path: Any) -> None:
    from dsoxlab.models.lab import LabDefinition

    chemin = tmp_path / "lab.yaml"
    chemin.write_text(
        "id: demo\ntitle: Demo\nlevel: l1\nskills: [x]\ndistros: [debian13]\n"
        "doc_url: https://example.test/g\n"
        "runtime:\n  type: shell\n  workdir: challenge/work\n  services:\n"
        "    - name: cloud\n      image: floci/floci:1.5.27\n"
        "      spawns:\n        - floci-ec2-\n",
        encoding="utf-8",
    )

    lab = LabDefinition.from_yaml(chemin)

    assert lab.runtime.services[0].spawns == ["floci-ec2-"]


def test_spawns_absent_donne_une_liste_vide(tmp_path: Any) -> None:
    from dsoxlab.models.lab import LabDefinition

    chemin = tmp_path / "lab.yaml"
    chemin.write_text(
        "id: demo\ntitle: Demo\nlevel: l1\nskills: [x]\ndistros: [debian13]\n"
        "doc_url: https://example.test/g\n"
        "runtime:\n  type: shell\n  workdir: challenge/work\n  services:\n"
        "    - name: db\n      image: postgres:16\n",
        encoding="utf-8",
    )

    assert LabDefinition.from_yaml(chemin).runtime.services[0].spawns == []
