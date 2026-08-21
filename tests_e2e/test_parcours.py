"""Le parcours que promet le README, joué en entier par sous-processus.

Installation, catalogue, premier lab, note. C'est le chemin qu'emprunte un
inconnu, et c'était le seul que personne ne rejouait. Tout passe par le binaire
installé : la suite ne connaît de dsoxlab que ce qu'il imprime et ce qu'il
laisse sur le disque.

**La suite doit pouvoir échouer**, sinon elle ne mesure rien. Deux leviers le
prouvent, et ils sont ici, pas dans un commentaire : le même lab rend 100 une
fois résolu et strictement moins quand il ne l'est pas, et un indice pris coûte
des points au barème. Modifier le lab de démonstration sans toucher à ses tests
fait rougir cette suite, ce qui est exactement le but.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from pathlib import Path
from typing import Any

from conftest import LAB_DEMO, Poste


def _document(sortie: str) -> Any:
    """Le JSON de la sortie standard, refusé s'il traîne quoi que ce soit.

    `json.loads` lève sur un flux qui commence par un message d'ambiance ou qui
    se termine par une barre de progression : c'est le contrat de `--json`, et
    c'est un défaut déjà vu trois fois en écrivant la CLI.
    """
    return json.loads(sortie)


def _lab_annonce(poste: Poste, catalogue: Path) -> dict[str, Any]:
    """Le lab tel que la CLI le décrit, pas tel que le contrat le raconte."""
    resultat = poste.lance("list-labs", "--json", cwd=catalogue)
    assert resultat.returncode == 0, resultat.stderr

    document = _document(resultat.stdout)
    assert document["count"] == 1, document
    return dict(document["labs"][0])


def _workdir(lab: dict[str, Any]) -> Path:
    """Le répertoire de travail annoncé par la CLI, jamais recopié à la main."""
    return Path(lab["path"]) / lab["runtime"]["workdir"]


def _note(sortie: str) -> str:
    """La ligne de score, ramenée à sa forme comparable.

    Le panneau Rich rend « Score:       100 / 100 pts ». On ne compare donc pas
    la mise en page, seulement les deux nombres.
    """
    return " ".join(sortie.split())


# ── ce que l'outil fait quand il n'a rien ─────────────────────────────────────

def test_hors_catalogue_l_outil_le_dit_sans_planter(poste: Poste) -> None:
    """Lancé n'importe où, dsoxlab répond au lieu de laisser croire au vide."""
    resultat = poste.lance("list-labs", cwd=poste.neutre)

    assert resultat.returncode == 0, resultat.stderr
    assert "No labs found" in resultat.stdout, resultat.stdout


# ── le parcours complet ───────────────────────────────────────────────────────

def test_de_l_installation_au_100_sur_100(
    poste: Poste, catalogue: Path, resoudre: Callable[[Path], None]
) -> None:
    """Installer, voir le catalogue, jouer le lab, le résoudre, être noté.

    Le `check` final se passe d'argument : c'est `run` qui a mémorisé le lab
    actif, et cette mémoire fait partie du parcours promis.
    """
    liste = poste.lance("list-labs", cwd=catalogue)
    assert liste.returncode == 0, liste.stderr
    assert LAB_DEMO in liste.stdout, liste.stdout

    lancement = poste.lance("run", LAB_DEMO, cwd=catalogue)
    assert lancement.returncode == 0, lancement.stderr or lancement.stdout

    workdir = _workdir(_lab_annonce(poste, catalogue))
    assert workdir.is_dir(), f"run n'a pas créé le répertoire de travail {workdir}"

    resoudre(workdir)

    verdict = poste.lance("check", cwd=catalogue)
    assert verdict.returncode == 0, verdict.stdout[-2000:]
    assert "100 / 100" in _note(verdict.stdout), verdict.stdout[-2000:]

    scores = poste.lance("scores", cwd=catalogue)
    assert scores.returncode == 0, scores.stderr
    assert "100/100" in _note(scores.stdout), scores.stdout


def test_le_meme_lab_non_resolu_ne_vaut_pas_100(poste: Poste, catalogue: Path) -> None:
    """L'autre moitié de la preuve : sans travail, pas de note.

    Sans ce test, un `check` qui rendrait 100 quoi qu'il arrive passerait la
    suite au vert. C'est le contrôle qui rend le précédent crédible.
    """
    lancement = poste.lance("run", LAB_DEMO, cwd=catalogue)
    assert lancement.returncode == 0, lancement.stderr or lancement.stdout

    verdict = poste.lance("check", LAB_DEMO, cwd=catalogue)

    assert verdict.returncode == 1, "un lab non résolu doit sortir en erreur"
    note = _note(verdict.stdout)
    assert "0 / 100" in note, verdict.stdout[-2000:]
    assert "100 / 100" not in note, verdict.stdout[-2000:]


def test_un_indice_pris_coute_des_points(
    poste: Poste, catalogue: Path, resoudre: Callable[[Path], None]
) -> None:
    """Le barème est vivant : un lab parfait ne vaut pas toujours 100.

    L'unique indice du lab de démonstration coûte 20 points. Le travail est
    juste, les trois tests passent, et la note descend quand même : c'est ce
    que le scoring promet, et rien d'autre ne le vérifie de bout en bout.
    """
    assert poste.lance("run", LAB_DEMO, cwd=catalogue).returncode == 0

    indice = poste.lance("hint", LAB_DEMO, cwd=catalogue)
    assert indice.returncode == 0, indice.stderr

    resoudre(_workdir(_lab_annonce(poste, catalogue)))
    verdict = poste.lance("check", LAB_DEMO, cwd=catalogue)

    assert verdict.returncode == 0, verdict.stdout[-2000:]
    assert "80 / 100" in _note(verdict.stdout), verdict.stdout[-2000:]


# ── le contrat de la sortie machine ───────────────────────────────────────────

def test_la_sortie_json_se_lit_sans_reste(
    poste: Poste, catalogue: Path, resoudre: Callable[[Path], None]
) -> None:
    """Une intégration lit ce flux : un mot de trop et il n'est plus lisible.

    Le cas du `check` en échec est celui qui casse le plus facilement : un lab
    qui passe n'emprunte jamais la branche qui imprime la sortie de pytest.
    """
    lab = _lab_annonce(poste, catalogue)
    assert lab["id"] == LAB_DEMO, lab
    assert lab["runtime"]["type"] == "shell", "le parcours doit tenir sans hyperviseur"

    assert poste.lance("run", LAB_DEMO, cwd=catalogue).returncode == 0

    echec = poste.lance("check", LAB_DEMO, "--json", cwd=catalogue)
    assert echec.returncode == 1, echec.stdout[-2000:]
    document = _document(echec.stdout)
    assert document["check"]["ok"] is False
    assert document["check"]["score"] == 0, document["check"]

    resoudre(_workdir(lab))

    reussite = poste.lance("check", LAB_DEMO, "--json", cwd=catalogue)
    assert reussite.returncode == 0, reussite.stdout[-2000:]
    document = _document(reussite.stdout)
    assert document["check"] == {
        **document["check"],
        "ok": True,
        "passed": 3,
        "total": 3,
        "score": 100,
        "max_score": 100,
    }


# ── le catalogue packagé tient le contrat qu'il enseigne ──────────────────────

def test_le_catalogue_package_passe_son_validateur(poste: Poste, catalogue: Path) -> None:
    """Le premier lab que voit un utilisateur ne peut pas violer le contrat.

    Le contrôle est joué par le binaire installé sur le catalogue qu'il vient
    de poser : c'est l'outil qui se juge lui-même, sans dépôt tiers.
    """
    resultat = poste.lance("validate-structure", cwd=catalogue)

    assert resultat.returncode == 0, resultat.stdout[-2000:]
