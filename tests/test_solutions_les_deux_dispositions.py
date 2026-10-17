"""Le contrôle des solutions regardait une seule disposition sur deux.

`validators/content.py` ne lisait que `solution/<chemin du lab>` à la RACINE du
dépôt. Quatre catalogues de la collection rangent leurs corrigés DANS le lab,
`labs/<lab>/solution/`, et le contrôle y passait donc au vert **sans avoir
regardé**. Mesuré avant d'écrire ces tests : 58 fichiers en clair dans
`dev-pour-ops`, 11 dans `python`, 1 dans `containers`, 1 dans
`github-actions`, tous invisibles au validateur.

Un contrôle qui n'a pas pu regarder ne conclut jamais au vert.

Et une déclaration, parce que chez deux de ces quatre le clair est DÉLIBÉRÉ :
le point de départ de chaque lab est la solution du précédent, donc le fichier
doit pouvoir être copié comme fixture. `repo.solutions: plaintext` le dit, et
le contrôle ne les accuse plus.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from dsoxlab.models.repo import RepoMetadata
from dsoxlab.validators.content import validate_solutions_encrypted

_LAB = """\
id: demo
title: Demo
level: l1
skills: [demo]
distros: [any]
doc_url: https://example.test/doc
runtime:
  type: shell
  workdir: challenge/work
"""

_CHIFFRE = "$ANSIBLE_VAULT;1.1;AES256\n3938343461366465\n"
_EN_CLAIR = "- name: la réponse\n  ansible.builtin.debug: {msg: tout est là}\n"


@pytest.fixture
def lab(tmp_path: Path):
    from dsoxlab.models.lab import LabDefinition

    base = tmp_path / "labs" / "demo"
    base.mkdir(parents=True)
    (base / "lab.yaml").write_text(_LAB, encoding="utf-8")
    return LabDefinition.from_yaml(base / "lab.yaml")


def test_une_solution_en_clair_dans_le_lab_est_vue(lab, tmp_path: Path) -> None:
    """La disposition `labs/<lab>/solution/`, qui échappait au contrôle."""
    dans_le_lab = tmp_path / "labs" / "demo" / "solution"
    dans_le_lab.mkdir()
    (dans_le_lab / "solution.yml").write_text(_EN_CLAIR, encoding="utf-8")

    rapport = validate_solutions_encrypted(lab, dans_le_lab)

    assert [i.key for i in rapport.issues] == ["content_solution_plaintext"], (
        "une solution en clair rangée DANS le lab doit être vue : c'est la "
        "disposition de quatre catalogues de la collection"
    )


def test_une_solution_en_clair_a_la_racine_est_toujours_vue(lab, tmp_path: Path) -> None:
    """L'ancienne disposition continue d'être contrôlée."""
    a_la_racine = tmp_path / "solution" / "demo"
    a_la_racine.mkdir(parents=True)
    (a_la_racine / "solution.yml").write_text(_EN_CLAIR, encoding="utf-8")

    rapport = validate_solutions_encrypted(lab, a_la_racine)

    assert [i.key for i in rapport.issues] == ["content_solution_plaintext"]


def test_les_deux_dispositions_sont_lues_dans_le_meme_appel(lab, tmp_path: Path) -> None:
    """Un dépôt peut tenir les deux, et les deux doivent être regardées."""
    dans_le_lab = tmp_path / "labs" / "demo" / "solution"
    dans_le_lab.mkdir()
    (dans_le_lab / "a.yml").write_text(_EN_CLAIR, encoding="utf-8")
    a_la_racine = tmp_path / "solution" / "demo"
    a_la_racine.mkdir(parents=True)
    (a_la_racine / "b.yml").write_text(_EN_CLAIR, encoding="utf-8")

    rapport = validate_solutions_encrypted(lab, dans_le_lab, a_la_racine)

    assert len(rapport.issues) == 2


def test_une_solution_chiffree_ne_dit_rien(lab, tmp_path: Path) -> None:
    """Le cas normal : rien à signaler."""
    dans_le_lab = tmp_path / "labs" / "demo" / "solution"
    dans_le_lab.mkdir()
    (dans_le_lab / "solution.yml").write_text(_CHIFFRE, encoding="utf-8")

    assert validate_solutions_encrypted(lab, dans_le_lab).issues == []


def test_une_racine_absente_nest_pas_une_faute(lab, tmp_path: Path) -> None:
    """Un dépôt sans répertoire de solutions a fait un autre choix."""
    assert validate_solutions_encrypted(
        lab, tmp_path / "nulle-part", tmp_path / "ailleurs",
    ).issues == []


# ── La déclaration, pour les catalogues qui enchaînent leurs labs ───────────


def test_le_defaut_du_contrat_est_le_chiffrement(tmp_path: Path) -> None:
    """Un dépôt qui ne déclare rien reste tenu à ce qu'il était tenu avant."""
    (tmp_path / "meta.yml").write_text(
        "repo:\n  id: demo\n  category: demo\n", encoding="utf-8")

    meta = RepoMetadata.from_yaml(tmp_path / "meta.yml")

    assert meta.solutions == "encrypted"


def test_plaintext_se_declare_explicitement(tmp_path: Path) -> None:
    """Le seul mot qui désarme le contrôle, et il faut l'écrire exactement."""
    (tmp_path / "meta.yml").write_text(
        "repo:\n  id: demo\n  category: demo\n  solutions: plaintext\n",
        encoding="utf-8")

    assert RepoMetadata.from_yaml(tmp_path / "meta.yml").solutions == "plaintext"


@pytest.mark.parametrize("valeur", ["PLAINTEXT", "plain text", "clair", "true",
                                    "plaintex", ""])
def test_une_valeur_inconnue_ne_relache_pas_le_controle(
    tmp_path: Path, valeur: str,
) -> None:
    """Un contrôle ne se relâche pas sur une faute de frappe.

    C'est le sens du défaut qu'on corrige : mieux vaut un contrôle trop sévère
    qu'un contrôle désarmé par un mot mal écrit, parce que le second est
    silencieux.
    """
    (tmp_path / "meta.yml").write_text(
        f"repo:\n  id: demo\n  category: demo\n  solutions: {valeur!r}\n",
        encoding="utf-8")

    assert RepoMetadata.from_yaml(tmp_path / "meta.yml").solutions == "encrypted"
