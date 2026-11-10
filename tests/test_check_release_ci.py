"""Zéro run de CI ne vaut pas une CI verte (`scripts/check-release.py`).

Le défaut, mesuré le 2026-11-10 juste avant de poser le tag `v0.8.2` : lancé
depuis une branche non fusionnée, où la CI ne tourne jamais, le script
annonçait **« ✔ CI verte sur ce commit »**. `gh run list --commit <sha>` rendait
pourtant `[]`.

La cause est une chaîne qui paraît vide et ne l'est pas : une liste JSON vide
s'écrit `"[]"`, donc `sortie.stdout.strip()` est non vide, aucune des branches
« état inconnu » ne s'ouvre, et `eprouvants`, `echoues` et `en_cours` sont tous
vides. Le script tombait alors dans le `else` final, celui du vert.

C'est la faute que ce dépôt refuse partout ailleurs : `doctor` a un code de
sortie à lui, `10`, pour « n'a pas pu être mesuré », précisément pour ne jamais
peindre en vert ce qu'il ignore. Ici le verdict décide d'un **tag**, et une
version publiée sur PyPI ne se reprend pas.

Ce module juge **dans les deux sens** : zéro run doit faire attendre, et un run
vert doit toujours conclure au vert. Sans ce second contrôle, le premier
passerait sur un script qui ne conclut plus jamais.

    pytest tests/test_check_release_ci.py -v
"""

from __future__ import annotations

import importlib.util
import json
import subprocess
from pathlib import Path
from typing import Any

import pytest

RACINE = Path(__file__).resolve().parent.parent
SCRIPT = RACINE / "scripts" / "check-release.py"


@pytest.fixture(scope="module")
def module() -> Any:
    """Charge `check-release.py` malgré son tiret, qui interdit l'import."""
    spec = importlib.util.spec_from_file_location("check_release", SCRIPT)
    assert spec and spec.loader, f"{SCRIPT} n'est pas chargeable."
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_le_module_se_charge(module: Any) -> None:
    """Le garde-fou : sans `_verifier_ci`, tout ce fichier mesurerait sa panne."""
    assert hasattr(module, "_verifier_ci")
    assert hasattr(module, "Rapport")


def _rapport_avec(module: Any, runs: list[dict[str, Any]], monkeypatch: pytest.MonkeyPatch) -> Any:
    """Joue `_verifier_ci` avec la sortie de `gh` qu'on lui impose."""
    def _faux_run(args: list[str], **kw: Any) -> subprocess.CompletedProcess[str]:
        return subprocess.CompletedProcess(args, 0, json.dumps(runs), "")

    monkeypatch.setattr(module.subprocess, "run", _faux_run)
    monkeypatch.setattr(module, "git", lambda *a: "0" * 40)
    rapport = module.Rapport()
    module._verifier_ci(rapport)
    return rapport


#: `Rapport` IMPRIME ses succès et ne retient que ce qui bloque ou interroge :
#: `echecs`, `attentes` et `notes`. On juge donc sur ces trois listes, et non
#: sur la sortie affichée — un test qui lit un rendu mesure le rendu, pas le
#: comportement, et il casse au premier changement de libellé.
def _verdict(rapport: Any) -> str:
    if rapport.echecs:
        return "ROUGE"
    if rapport.attentes:
        return "ATTENDRE"
    return "VERT"


def test_zero_run_ne_vaut_pas_une_ci_verte(module: Any, monkeypatch: pytest.MonkeyPatch) -> None:
    """Le défaut d'origine : aucun run, et le script concluait au vert."""
    rapport = _rapport_avec(module, [], monkeypatch)

    assert _verdict(rapport) == "ATTENDRE", (
        "zéro run doit faire ATTENDRE, jamais conclure au vert : le verdict "
        "décide d'un tag, et une version publiée sur PyPI ne se reprend pas.\n"
        f"echecs={rapport.echecs} attentes={rapport.attentes} notes={rapport.notes}"
    )
    assert any("Aucun run" in str(a) for a in rapport.attentes), (
        "l'attente doit NOMMER la cause : « aucun run sur ce commit ». Un "
        "« état inconnu » générique n'enverrait pas fusionner d'abord.\n"
        f"attentes={rapport.attentes}"
    )


def test_un_run_vert_conclut_toujours_au_vert(module: Any, monkeypatch: pytest.MonkeyPatch) -> None:
    """Le contre-témoin, sans lequel le test précédent ne mesure rien.

    Si `_verifier_ci` n'arrivait plus jamais à conclure, le contrôle du zéro run
    passerait pour une raison étrangère au défaut : un script qui attend
    toujours.
    """
    rapport = _rapport_avec(
        module,
        [{"name": "CI", "status": "completed", "conclusion": "success", "event": "push"}],
        monkeypatch,
    )
    assert _verdict(rapport) == "VERT", (
        "un run vert doit toujours conclure au vert.\n"
        f"echecs={rapport.echecs} attentes={rapport.attentes}"
    )


def test_un_run_en_echec_reste_rouge(module: Any, monkeypatch: pytest.MonkeyPatch) -> None:
    """Second contre-témoin : le nouveau repli n'absorbe pas les vrais échecs."""
    rapport = _rapport_avec(
        module,
        [{"name": "CI", "status": "completed", "conclusion": "failure", "event": "push"}],
        monkeypatch,
    )
    assert _verdict(rapport) == "ROUGE", (
        "un run en échec doit rester un échec.\n"
        f"echecs={rapport.echecs} attentes={rapport.attentes}"
    )


def test_un_run_encore_en_cours_fait_attendre(module: Any, monkeypatch: pytest.MonkeyPatch) -> None:
    """Et le cas intermédiaire, qui doit rester distinct du zéro run."""
    rapport = _rapport_avec(
        module,
        [{"name": "CI", "status": "in_progress", "conclusion": None, "event": "push"}],
        monkeypatch,
    )
    assert _verdict(rapport) == "ATTENDRE"
    assert not any("Aucun run" in str(a) for a in rapport.attentes), (
        "un run EN COURS n'est pas un run ABSENT : les deux attendent, mais "
        "pour des raisons opposées, et le message doit les distinguer."
    )
