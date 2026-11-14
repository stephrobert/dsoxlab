"""Une phrase de la doc du moteur recopiée dans un catalogue, et devenue fausse (#201).

L'inventaire du 2026-11-14 a trouvé 50 fichiers faux dans 21 catalogues. Ce
contrôle cherche des phrases connues pour être fausses, pas des pages qui
« redécrivent » le moteur : il ne doit jamais crier sur une phrase juste.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from dsoxlab.services.scaffold import creer_catalogue
from dsoxlab.validators.doc_moteur import validate_doc_moteur

PHRASES_FAUSSES = {
    "list_labs_avant": "Run `list-labs` **before** `validate-structure`: the validator iterates "
                       "over the labs already loaded.",
    "status_joignabilite": "```bash\ndsoxlab status                 # vérifie qu'elles répondent\n```",
    "runtime_host": "Every referenced lab exists, every `runtime.host` points to a declared host.",
    "fixtures_a_plat": "fixtures: [acces.log]   # copiés à plat dans le workdir",
}


def _cles(root: Path) -> set[str]:
    return {a.key for a in validate_doc_moteur(root).issues}


@pytest.mark.parametrize(("ident", "phrase"), PHRASES_FAUSSES.items())
def test_chaque_phrase_perimee_est_signalee(tmp_path: Path, ident: str, phrase: str) -> None:
    (tmp_path / "README.md").write_text(f"# Catalogue\n\n{phrase}\n", encoding="utf-8")
    assert _cles(tmp_path) == {f"doc_perimee_{ident}"}


def test_une_phrase_coupee_par_un_retour_a_la_ligne_est_vue(tmp_path: Path) -> None:
    (tmp_path / "CONTRIBUTING.fr.md").write_text(
        "Joue `list-labs` **avant**\n`validate-structure` : le validateur itère sur les\nlabs déjà chargés.\n",
        encoding="utf-8",
    )
    assert _cles(tmp_path) == {"doc_perimee_list_labs_avant"}


def test_une_phrase_juste_n_est_jamais_signalee(tmp_path: Path) -> None:
    # Le faux positif que la première version du motif commettait, mesuré le
    # 2026-11-14 sur une fiche du catalogue iam qui dit le VRAI.
    (tmp_path / "NOTES.md").write_text(
        "**`runtime.host` n'existe pas.** Le FQDN vit dans `runtime.targets[].host`.\n", encoding="utf-8")
    assert _cles(tmp_path) == set()


def test_ni_labs_ni_solution_ni_changelog_ne_sont_lus(tmp_path: Path) -> None:
    phrase = PHRASES_FAUSSES["runtime_host"]
    for rel in ("labs/un/README.md", "solution/un/notes.md", "CHANGELOG.md", "CHANGELOG.fr.md"):
        (tmp_path / rel).parent.mkdir(parents=True, exist_ok=True)
        (tmp_path / rel).write_text(phrase, encoding="utf-8")
    assert _cles(tmp_path) == set()


def test_dans_un_depot_git_seuls_les_fichiers_versionnes_comptent(tmp_path: Path) -> None:
    (tmp_path / "README.md").write_text("# Propre\n", encoding="utf-8")
    (tmp_path / "BROUILLON.md").write_text(PHRASES_FAUSSES["runtime_host"], encoding="utf-8")
    subprocess.run(["git", "init", "-q", str(tmp_path)], check=True)
    subprocess.run(["git", "-C", str(tmp_path), "add", "README.md"], check=True)
    assert _cles(tmp_path) == set()


def test_un_catalogue_neuf_ne_porte_aucune_phrase_perimee(tmp_path: Path) -> None:
    creer_catalogue("neuf", tmp_path)
    assert _cles(tmp_path / "neuf") == set()
