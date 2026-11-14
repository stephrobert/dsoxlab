"""La table des catalogues se mesure sur les dépôts publiés, jamais à la main.

Le 2026-11-14, le README annonçait 64 labs pour Kubernetes quand le dépôt publié
en portait 111, et ignorait huit catalogues publics : les chiffres étaient
écrits dans le manifeste. Ces tests jouent le générateur contre une API GitHub
simulée : aucun réseau.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path
from typing import Any

import pytest
import yaml

RACINE = Path(__file__).resolve().parents[1]


def _generateur() -> Any:
    spec = importlib.util.spec_from_file_location("gen_catalogues", RACINE / "scripts" / "gen-catalogues.py")
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def gen() -> Any:
    return _generateur()


def _api_simulee(gen: Any, depots: dict[str, dict[str, Any]], arbres: dict[str, Any]) -> Any:
    def api(chemin: str, jeton: str | None) -> Any:
        if chemin.startswith("/users/"):
            return list(depots.values()) if chemin.endswith("&page=1") else []
        if "/git/trees/" in chemin:
            nom = chemin.split("/")[3]
            arbre = arbres[nom]
            if isinstance(arbre, Exception):
                raise arbre
            return arbre
        return depots[chemin.split("/")[3]]
    return api


def _depot(nom: str, **champs: Any) -> dict[str, Any]:
    return {"name": nom, "default_branch": "main", "private": False, "archived": False,
            "fork": False, "size": 10, **champs}


def _arbre(*chemins: str, tronque: bool = False) -> dict[str, Any]:
    return {"truncated": tronque, "tree": [{"path": c, "type": "blob"} for c in chemins]}


ENTREE = {"id": "a", "depot": "https://github.com/proprio/cat-a", "description_en": "A", "description_fr": "A"}


def test_le_manifeste_ne_porte_plus_aucun_chiffre() -> None:
    donnees = yaml.safe_load((RACINE / "src/dsoxlab/templates/catalogues.yml").read_text(encoding="utf-8"))
    assert all("labs" not in c for c in donnees["catalogues"])


def test_seuls_les_lab_yaml_sous_labs_comptent(gen: Any, monkeypatch: pytest.MonkeyPatch) -> None:
    arbres = {"cat-a": _arbre("labs/un/lab.yaml", "labs/deux/sous/lab.yaml", "lab.yaml",
                              "fixtures/labs/x/lab.yaml.bak", "labs/trois/lab.fr.yaml", "meta.yml")}
    monkeypatch.setattr(gen, "_api", _api_simulee(gen, {"cat-a": _depot("cat-a")}, arbres))
    comptes, ecarts = gen._mesurer_le_manifeste([ENTREE], None)
    assert comptes == {ENTREE["depot"]: 2} and ecarts == []


def test_un_arbre_tronque_ne_conclut_pas(gen: Any, monkeypatch: pytest.MonkeyPatch) -> None:
    arbres = {"cat-a": _arbre("labs/un/lab.yaml", tronque=True)}
    monkeypatch.setattr(gen, "_api", _api_simulee(gen, {"cat-a": _depot("cat-a")}, arbres))
    with pytest.raises(gen.NonMesurable):
        gen._mesurer_le_manifeste([ENTREE], None)


def test_un_depot_vide_publie_zero_lab(gen: Any, monkeypatch: pytest.MonkeyPatch) -> None:
    arbres = {"cat-a": gen.NonMesurable("/repos/proprio/cat-a/git/trees/main?recursive=1 : HTTP 409")}
    monkeypatch.setattr(gen, "_api", _api_simulee(gen, {"cat-a": _depot("cat-a")}, arbres))
    comptes, _ = gen._mesurer_le_manifeste([ENTREE], None)
    assert comptes == {ENTREE["depot"]: 0}


def test_un_depot_prive_du_manifeste_est_refuse(gen: Any, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(gen, "_api", _api_simulee(gen, {"cat-a": _depot("cat-a", private=True)}, {}))
    comptes, ecarts = gen._mesurer_le_manifeste([ENTREE], None)
    assert comptes == {} and any("PRIVÉ" in e for e in ecarts)


def test_un_depot_public_avec_des_labs_hors_manifeste_est_nomme(gen: Any, monkeypatch: pytest.MonkeyPatch) -> None:
    depots = {"cat-a": _depot("cat-a"), "cat-b": _depot("cat-b"), "outil": _depot("outil"),
              "brouillon": _depot("brouillon", private=True)}
    arbres = {"cat-b": _arbre("meta.yml", "labs/x/lab.yaml"), "outil": _arbre("README.md"),
              "brouillon": _arbre("meta.yml", "labs/y/lab.yaml")}
    monkeypatch.setattr(gen, "_api", _api_simulee(gen, depots, arbres))
    assert gen._oublies([ENTREE], None) == ["cat-b (1 labs publiés)"]


def test_la_table_trie_par_nombre_et_ecarte_les_catalogues_sans_lab(gen: Any) -> None:
    entrees = [ENTREE, {**ENTREE, "depot": "https://github.com/proprio/cat-b", "description_en": "B"},
               {**ENTREE, "depot": "https://github.com/proprio/cat-c", "description_en": "C"}]
    comptes = {entrees[0]["depot"]: 3, entrees[1]["depot"]: 9, entrees[2]["depot"]: 0}
    table = gen._table("en", entrees, comptes)
    lignes = [ligne for ligne in table.splitlines() if ligne.startswith("| [`")]
    assert [ligne.split("`")[1] for ligne in lignes] == ["cat-b", "cat-a"]
    assert "_12 labs across 2 catalogs" in table


# ── draft: true (#369) ───────────────────────────────────────────────────────

BROUILLON = {**ENTREE, "id": "b", "depot": "https://github.com/proprio/cat-b", "draft": True}


def test_une_entree_publiee_sans_lab_est_un_ecart(gen: Any, monkeypatch: pytest.MonkeyPatch) -> None:
    """Le défaut de la 0.9.2 : `catalog list` proposait un catalogue vide."""
    arbres = {"cat-a": _arbre("meta.yml", "README.md")}
    monkeypatch.setattr(gen, "_api", _api_simulee(gen, {"cat-a": _depot("cat-a")}, arbres))
    comptes, ecarts = gen._mesurer_le_manifeste([ENTREE], None)
    assert comptes == {ENTREE["depot"]: 0}
    assert len(ecarts) == 1 and "draft: true" in ecarts[0] and "cat-a" in ecarts[0]


def test_une_entree_draft_sans_lab_n_est_pas_un_ecart(gen: Any, monkeypatch: pytest.MonkeyPatch) -> None:
    arbres = {"cat-b": _arbre("meta.yml")}
    monkeypatch.setattr(gen, "_api", _api_simulee(gen, {"cat-b": _depot("cat-b")}, arbres))
    comptes, ecarts = gen._mesurer_le_manifeste([BROUILLON], None)
    assert comptes == {BROUILLON["depot"]: 0} and ecarts == []


def test_une_entree_draft_est_mesuree_hors_de_la_table(gen: Any) -> None:
    """Même avec des labs publiés, un brouillon n'entre pas dans la table."""
    comptes = {ENTREE["depot"]: 3, BROUILLON["depot"]: 6}
    table = gen._table("fr", [ENTREE, BROUILLON], comptes)
    assert "cat-b" not in table
    assert "_3 labs dans 1 catalogues" in table


def test_un_depot_draft_n_est_pas_un_oubli(gen: Any, monkeypatch: pytest.MonkeyPatch) -> None:
    """Un dépôt public au manifeste en brouillon n'est pas « absent du manifeste »."""
    depots = {"cat-a": _depot("cat-a"), "cat-b": _depot("cat-b")}
    arbres = {"cat-b": _arbre("meta.yml", "labs/x/lab.yaml")}
    monkeypatch.setattr(gen, "_api", _api_simulee(gen, depots, arbres))
    assert gen._oublies([ENTREE, BROUILLON], None) == []


def test_main_sort_en_1_sur_une_entree_publiee_vide(
    gen: Any, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    """De bout en bout : le message dit de passer l'entrée en brouillon ou de la retirer."""
    for nom in gen.CIBLES:
        (tmp_path / nom).write_text(f"{gen.DEBUT}\n{gen.FIN}\n", encoding="utf-8")
    monkeypatch.setattr(gen, "RACINE", tmp_path)
    monkeypatch.setattr(gen, "_manifeste", lambda: [ENTREE, BROUILLON])
    monkeypatch.setattr(gen, "_jeton", lambda: None)
    depots = {"cat-a": _depot("cat-a"), "cat-b": _depot("cat-b")}
    arbres = {"cat-a": _arbre("meta.yml"), "cat-b": _arbre("meta.yml")}
    monkeypatch.setattr(gen, "_api", _api_simulee(gen, depots, arbres))
    monkeypatch.setattr("sys.argv", ["gen-catalogues.py"])

    assert gen.main() == 1
    erreurs = capsys.readouterr().err
    assert "cat-a" in erreurs and "draft: true" in erreurs
    assert "cat-b" not in erreurs
