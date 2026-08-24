"""Le garde-fou de publication doit être fiable avant d'être sévère.

`scripts/check-release.py` est le dernier contrôle avant un tag, et un tag
publie sur PyPI, où un numéro consommé ne se réutilise jamais. Un contrôle qui
se trompe y coûte donc plus cher qu'ailleurs, et de deux façons opposées :

- **trop sévère au hasard**, il finit contourné, et c'est alors l'ensemble des
  contrôles qui ne sert plus à rien ;
- **trop bavard sur la mauvaise version**, il rend un verdict qui ne parle pas
  de ce qu'on lui a demandé.

Ce module ferme les deux, chacun sur un défaut réellement observé le
2026-08-24 pendant la publication des 0.1.65 et 0.1.66.
"""

from __future__ import annotations

import importlib.util
import subprocess
from pathlib import Path
from typing import Any

import pytest

RACINE = Path(__file__).resolve().parent.parent


def _module() -> Any:
    """Charge `scripts/check-release.py` (son nom porte un tiret)."""
    chemin = RACINE / "scripts" / "check-release.py"
    spec = importlib.util.spec_from_file_location("check_release", chemin)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def cr() -> Any:
    chemin = RACINE / "scripts" / "check-release.py"
    if not chemin.is_file():
        pytest.skip("script de release absent de ce dépôt")
    return _module()


def _resultat(sortie: str, code: int = 0) -> subprocess.CompletedProcess[str]:
    return subprocess.CompletedProcess(args=["git"], returncode=code,
                                       stdout=sortie, stderr="")


# ── L'arbre de travail : ce que le tag fige, et ce qu'il laisse ─────────────

def test_un_fichier_non_suivi_ne_bloque_pas_le_tag(
    cr: Any, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str],
) -> None:
    """Un fichier hors index n'entre dans aucun commit : il ne peut rien fausser.

    Le cas réel : l'environnement de ce dépôt monte des nœuds `/dev/null` à la
    racine (`.bashrc`, `.gitconfig`, `.idea`…), que `git status --porcelain`
    liste en non suivis. Le contrôle échouait donc selon que ces montages
    étaient visibles au moment de l'appel, c'est-à-dire par intermittence.
    """
    def _git(*args: str) -> subprocess.CompletedProcess[str]:
        if "--untracked-files=no" in args:
            return _resultat("")           # aucun fichier suivi modifié
        return _resultat("?? .bashrc\n?? .idea\n")

    monkeypatch.setattr(cr, "git_resultat", _git)
    r = cr.Rapport()
    cr._verifier_arbre(r)

    assert r.echecs == [], "des fichiers non suivis ne doivent pas bloquer un tag"
    sortie = capsys.readouterr().out
    assert ".bashrc" in sortie, "ils doivent tout de même être nommés"
    assert "git add" in sortie, "et l'oubli possible doit être dit"


def test_un_fichier_suivi_modifie_bloque_toujours(
    cr: Any, monkeypatch: pytest.MonkeyPatch,
) -> None:
    """L'autre sens, et le seul qui compte : le tag figerait un état différent."""
    def _git(*args: str) -> subprocess.CompletedProcess[str]:
        return _resultat(" M src/dsoxlab/cli.py\n")

    monkeypatch.setattr(cr, "git_resultat", _git)
    r = cr.Rapport()
    cr._verifier_arbre(r)

    assert len(r.echecs) == 1


def test_un_git_muet_est_un_echec_pas_un_feu_vert(
    cr: Any, monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Le garde-fou du garde-fou : sortie vide + code non nul ≠ arbre propre."""
    monkeypatch.setattr(cr, "git_resultat", lambda *a: _resultat("", code=128))
    r = cr.Rapport()
    cr._verifier_arbre(r)

    assert len(r.echecs) == 1


# ── --publiee : le contrôle doit parler du tag qu'on lui donne ──────────────

def test_publiee_verifie_la_version_du_tag_demande(
    cr: Any, monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Le dépôt avance ; le tag qu'on vérifie, lui, ne change pas.

    Après le merge d'une version suivante, `--publiee v0.1.65` interrogeait PyPI
    sur la version empaquetée du moment (0.1.66) et annonçait « la version
    0.1.66 est absente de PyPI ». Verdict faux, sur une version bien livrée.
    """
    vues: dict[str, str] = {}

    def _faux_controle(version: str, tag: str) -> int:
        vues["version"] = version
        vues["tag"] = tag
        return 0

    monkeypatch.setattr(cr, "version_empaquetee", lambda: "0.1.66")
    monkeypatch.setattr(cr, "controler_publication", _faux_controle)
    monkeypatch.setattr(cr.sys, "argv", ["check-release.py", "--publiee", "v0.1.65"])

    assert cr.main() == 0
    assert vues["tag"] == "v0.1.65"
    assert vues["version"] == "0.1.65", (
        "la version contrôlée doit venir du tag, pas du pyproject courant"
    )


def test_publiee_sans_argument_prend_la_version_empaquetee(
    cr: Any, monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Sans tag explicite, le cas courant ne change pas : on vérifie ce qu'on vient
    de publier."""
    vues: dict[str, str] = {}

    monkeypatch.setattr(cr, "version_empaquetee", lambda: "0.1.66")
    monkeypatch.setattr(cr, "controler_publication",
                        lambda version, tag: (vues.update(version=version, tag=tag), 0)[1])
    monkeypatch.setattr(cr.sys, "argv", ["check-release.py", "--publiee"])

    assert cr.main() == 0
    assert vues == {"version": "0.1.66", "tag": "v0.1.66"}
