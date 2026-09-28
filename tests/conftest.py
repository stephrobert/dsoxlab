"""Réglages communs à toute la suite unitaire.

Un test unitaire ne doit mesurer que le code, jamais la machine qui l'exécute ni
le réseau du moment. `test_doctor.py` porte déjà cette règle pour terraform,
ansible et les prérequis matériels — « sans cela, ces tests mesurent la machine
qui les exécute : ils passaient en local et échouaient sur un runner CI ».

Le contrôle d'accès sortant ajouté en 0.1.81 a rouvert la brèche, et plus
largement : il ouvrait de **vraies connexions**. Six fichiers de tests
appelaient `collect_checks` sans le savoir, chacun payant jusqu'à trois délais
d'attente et rendant un verdict différent selon que le réseau répondait ou non.
Les mêmes tests passaient sur un runner GitHub et échouaient derrière un
pare-feu — c'est-à-dire qu'ils ne mesuraient plus ce qu'ils prétendaient.
"""

from __future__ import annotations

from pathlib import Path

import pytest


@pytest.fixture(autouse=True)
def _aucun_acces_reseau(monkeypatch: pytest.MonkeyPatch) -> None:
    """Neutralise l'unique sonde réseau de `doctor`, pour toute la suite.

    On neutralise `_joignable`, pas `socket.create_connection` : ce dernier sert
    aussi à `runtimes/services.py` pour attendre qu'un conteneur écoute, et le
    rendre toujours vrai ferait passer des tests de services qui ne prouveraient
    plus rien.

    Un test qui veut éprouver le contrôle lui-même repatche `_joignable` par
    dessus — c'est ce que fait `test_cloud_init_degrade.py`, et le monkeypatch
    le plus récent l'emporte.
    """
    from dsoxlab.services import doctor

    monkeypatch.setattr(doctor, "_joignable", lambda hote: True)


# ── un catalogue d'essai, partagé par toute la suite ────────────────────────
#
# Il vivait dans `test_json_output.py`, où il a été écrit ; trois fichiers en
# ont besoin depuis. Le dupliquer aurait produit trois catalogues qui dérivent,
# et le premier défaut de contrat aurait été trouvé dans un seul des trois.

_META = """\
repo:
  id: catalogue-essai
  category: domaine
sections:
  - id: domaine
    title: Domaine
    labs:
      - domaine/premier
      - domaine/second
"""

_LAB = """\
id: {ident}
title: {titre}
level: l1
skills: [une-competence]
distros: [alma10]
doc_url: https://exemple.test/guide
runtime:
  type: shell
  workdir: challenge/work
"""


def _poser_lab(racine: Path, ident: str, titre: str) -> Path:
    """Un lab conforme au contrat, réduit à ce que les validators exigent."""
    lab = racine / "labs" / "domaine" / ident
    (lab / "challenge" / "tests").mkdir(parents=True)
    (lab / "lab.yaml").write_text(
        _LAB.format(ident=ident, titre=titre), encoding="utf-8"
    )
    (lab / "README.md").write_text(f"# {titre}\n", encoding="utf-8")
    (lab / "scenario.md").write_text("Faites la chose.\n", encoding="utf-8")
    (lab / "challenge" / "tests" / "test_functional.py").write_text(
        "def test_la_chose_est_faite() -> None:\n    assert True\n", encoding="utf-8"
    )
    return lab


@pytest.fixture
def catalogue(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Un catalogue minimal, conforme, et sans le moindre chemin personnel.

    ``LAB_HOME`` le désigne : c'est aussi ce que lit ``--lab-home``, donc les
    commandes le trouvent sans qu'aucun test ne dépende du répertoire courant.
    Les répertoires XDG partent dans le ``tmp_path``, faute de quoi cette suite
    écrirait un journal dans le répertoire personnel de qui la lance.
    """
    racine = tmp_path / "catalogue"
    racine.mkdir()
    (racine / "meta.yml").write_text(_META, encoding="utf-8")
    _poser_lab(racine, "premier", "Le premier")
    _poser_lab(racine, "second", "Le second")

    monkeypatch.setenv("LAB_HOME", str(racine))
    monkeypatch.setenv("DSOXLAB_LANG", "en")
    for variable in ("XDG_STATE_HOME", "XDG_CACHE_HOME", "XDG_DATA_HOME"):
        monkeypatch.setenv(variable, str(tmp_path / variable.lower()))
    return racine
