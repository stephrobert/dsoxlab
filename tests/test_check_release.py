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


# ── L'état de la CI : ne pas savoir n'est pas savoir que c'est vert ─────────

def _sans_gh(cr: Any, monkeypatch: pytest.MonkeyPatch, *, erreur: Exception | None = None,
             code: int = 1, sortie: str = "") -> None:
    """Simule un `gh` indisponible, de l'une des trois façons observées."""
    def _run(*args: object, **kwargs: object) -> subprocess.CompletedProcess[str]:
        if erreur is not None:
            raise erreur
        return subprocess.CompletedProcess(args=["gh"], returncode=code,
                                           stdout=sortie, stderr="")
    monkeypatch.setattr(cr.subprocess, "run", _run)
    monkeypatch.setattr(cr, "git", lambda *a: "sha")


def test_gh_muet_fait_attendre_au_lieu_de_conclure(
    cr: Any, monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Le défaut vécu en publiant la 0.1.67.

    Le script a annoncé « Tout est bon » alors que la CI tournait encore, faute
    d'avoir pu joindre `gh`. Ne pas savoir si la CI est verte appelle la même
    décision que savoir qu'elle ne l'est pas : ne pas taguer, PyPI étant
    définitif.
    """
    _sans_gh(cr, monkeypatch)
    r = cr.Rapport()
    cr._verifier_ci(r)

    assert r.attentes, "un état inconnu doit valoir « trop tôt »"
    assert not r.echecs


def test_gh_introuvable_ne_leve_pas(
    cr: Any, monkeypatch: pytest.MonkeyPatch,
) -> None:
    """`check=False` ne couvre que le code de retour, pas l'absence du binaire.

    Un contributeur sans `gh` recevait un FileNotFoundError et perdait tout le
    rapport, y compris les sept contrôles qui, eux, avaient répondu.
    """
    _sans_gh(cr, monkeypatch, erreur=FileNotFoundError(2, "No such file", "gh"))
    r = cr.Rapport()
    cr._verifier_ci(r)

    assert r.attentes
    assert not r.echecs


def test_ci_verifiee_assume_l_affirmation(
    cr: Any, monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Le drapeau matérialise le geste : c'est l'humain qui affirme, et ça se voit."""
    _sans_gh(cr, monkeypatch)
    r = cr.Rapport()
    cr._verifier_ci(r, ci_verifiee=True)

    assert not r.attentes and not r.echecs


def test_une_ci_en_cours_fait_toujours_attendre(
    cr: Any, monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Garde-fou : le comportement d'origine ne doit pas se perdre."""
    _sans_gh(cr, monkeypatch, code=0,
             sortie='[{"name": "CI", "status": "in_progress", "conclusion": null}]')
    r = cr.Rapport()
    cr._verifier_ci(r)

    assert r.attentes and not r.echecs


def test_une_ci_en_echec_reste_un_echec(
    cr: Any, monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Et --ci-verifiee ne doit pas pouvoir la couvrir : gh a répondu, il dit rouge."""
    rouge = '[{"name": "CI", "status": "completed", "conclusion": "failure"}]'
    for drapeau in (False, True):
        _sans_gh(cr, monkeypatch, code=0, sortie=rouge)
        r = cr.Rapport()
        cr._verifier_ci(r, ci_verifiee=drapeau)
        assert r.echecs, f"une CI rouge doit bloquer (ci_verifiee={drapeau})"


# ── Les versions annoncées : celles qu'on a enjambées ───────────────────────

def _index(*versions: str) -> str:
    """Un index simple de PyPI, réduit à ce que le contrôle y cherche."""
    return "\n".join(f"dsoxlab-{v}-py3-none-any.whl" for v in versions)


def test_une_version_annoncee_et_jamais_publiee_bloque(
    cr: Any, monkeypatch: pytest.MonkeyPatch, tmp_path: Path,
) -> None:
    """Le défaut qui s'est produit DEUX fois le 2026-08-24.

    La 0.1.64 puis la 0.1.68 ont été fusionnées sur main, décrites au CHANGELOG,
    et jamais taguées. Rien ne le disait : les autres contrôles regardent si le
    PROCHAIN tag peut être posé, aucun ne demandait si le précédent l'avait été.
    Une version enjambée ne se rattrape pas, la suivante prenant sa place.
    """
    (tmp_path / "CHANGELOG.md").write_text(
        "## [0.1.69] - x\n## [0.1.68] - x\n## [0.1.67] - x\n", encoding="utf-8")
    monkeypatch.setattr(cr, "RACINE", tmp_path)
    monkeypatch.setattr(cr, "_index_simple", lambda: _index("0.1.67"))

    r = cr.Rapport()
    cr._verifier_versions_annoncees(r, "0.1.69")

    assert r.echecs, "une version annoncée et absente de PyPI doit bloquer"


def test_la_version_courante_n_est_pas_reprochee(
    cr: Any, monkeypatch: pytest.MonkeyPatch, tmp_path: Path,
) -> None:
    """Celle qu'on s'apprête à publier manque forcément : c'est le cas normal."""
    (tmp_path / "CHANGELOG.md").write_text(
        "## [0.1.69] - x\n## [0.1.68] - x\n", encoding="utf-8")
    monkeypatch.setattr(cr, "RACINE", tmp_path)
    monkeypatch.setattr(cr, "_index_simple", lambda: _index("0.1.68"))

    r = cr.Rapport()
    cr._verifier_versions_annoncees(r, "0.1.69")

    assert not r.echecs


def test_une_version_exemptee_ne_bloque_pas(
    cr: Any, monkeypatch: pytest.MonkeyPatch, tmp_path: Path,
) -> None:
    """0.1.25 n'ira jamais sur PyPI, et le CHANGELOG dit pourquoi."""
    (tmp_path / "CHANGELOG.md").write_text(
        "## [0.1.26] - x\n## [0.1.25] - x\n", encoding="utf-8")
    monkeypatch.setattr(cr, "RACINE", tmp_path)
    monkeypatch.setattr(cr, "_index_simple", lambda: _index("0.1.26"))

    r = cr.Rapport()
    cr._verifier_versions_annoncees(r, "0.1.27")

    assert not r.echecs
    assert "0.1.25" in cr.VERSIONS_JAMAIS_PUBLIEES


def test_un_changelog_sans_version_est_un_echec(
    cr: Any, monkeypatch: pytest.MonkeyPatch, tmp_path: Path,
) -> None:
    """Le garde-fou du garde-fou : une liste vide vaudrait feu vert à vide."""
    (tmp_path / "CHANGELOG.md").write_text("# Changelog\n\nrien\n", encoding="utf-8")
    monkeypatch.setattr(cr, "RACINE", tmp_path)
    monkeypatch.setattr(cr, "_index_simple", lambda: _index("0.1.68"))

    r = cr.Rapport()
    cr._verifier_versions_annoncees(r, "0.1.69")

    assert r.echecs, "ne rien mesurer ne doit pas valoir « tout est bon »"


def test_index_injoignable_ne_bloque_pas(
    cr: Any, monkeypatch: pytest.MonkeyPatch, tmp_path: Path,
) -> None:
    """Hors ligne, on ne sait pas : on le dit, sans reprocher une absence."""
    (tmp_path / "CHANGELOG.md").write_text("## [0.1.68] - x\n", encoding="utf-8")
    monkeypatch.setattr(cr, "RACINE", tmp_path)
    monkeypatch.setattr(cr, "_index_simple", lambda: None)

    r = cr.Rapport()
    cr._verifier_versions_annoncees(r, "0.1.69")

    assert not r.echecs


def test_les_controles_sont_bien_cables(cr: Any, monkeypatch: pytest.MonkeyPatch) -> None:
    """Un contrôle qui existe mais que personne n'appelle ne garde rien.

    Constaté en éprouvant le précédent : retirer `_verifier_versions_annoncees`
    de la séquence de `main()` ne faisait rougir aucun test, puisque tous
    l'appellent directement. Le contrôle aurait cessé de tourner sans un mot.
    """
    joues: list[str] = []

    for nom in ("_verifier_arbre", "_verifier_branche", "_verifier_tag",
                "_verifier_changelog", "_verifier_lock", "_verifier_pypi",
                "_verifier_versions_annoncees", "_verifier_ci"):
        monkeypatch.setattr(
            cr, nom,
            (lambda n: lambda *a, **k: joues.append(n))(nom),
        )
    monkeypatch.setattr(cr, "version_empaquetee", lambda: "0.1.99")
    monkeypatch.setattr(cr.sys, "argv", ["check-release.py"])

    cr.main()

    manquants = [n for n in ("_verifier_arbre", "_verifier_branche", "_verifier_tag",
                             "_verifier_changelog", "_verifier_lock", "_verifier_pypi",
                             "_verifier_versions_annoncees", "_verifier_ci")
                 if n not in joues]
    assert not manquants, f"contrôles définis mais jamais appelés : {manquants}"
