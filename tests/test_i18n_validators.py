"""Un catalogue mal formé se dit dans la langue de qui le lit (#139).

Les validators et la lecture du contrat étaient la dernière zone à composer ses
phrases en français, dans des champs de dataclasses et des ``ValueError``.
Elles sortaient telles quelles sous ``DSOXLAB_LANG=en``, c'est-à-dire au pire
moment : quand un auteur découvre le contrat et que son catalogue est cassé.

Trois comportements sont tenus ici, un par correction :

1. ``validate-structure`` suit ``DSOXLAB_LANG``, structure, métadonnées et
   contenu compris ;
2. une erreur de lecture du ``meta.yml`` aussi, parce que ce fichier-là
   s'affiche ;
3. un ``lab.yaml`` illisible, lui, **ne s'affiche pas** : sa raison va au
   journal, elle reste technique, et la classe qui la porte le dit.

Et un quatrième contrôle, mécanique celui-là : toute clé employée par les
validators ou par le contrat existe dans **les deux** tables. Une clé écrite
d'un seul côté rendrait la clé elle-même à l'écran.
"""

from __future__ import annotations

import ast
import re
from pathlib import Path

import pytest
from typer.testing import CliRunner

import dsoxlab
from dsoxlab.cli import app
from dsoxlab.discovery.scanner import scan_catalog
from dsoxlab.i18n import set_lang
from dsoxlab.i18n.strings.en import STRINGS as EN
from dsoxlab.i18n.strings.fr import STRINGS as FR
from dsoxlab.models._contract import ContractError, LabYamlError
from dsoxlab.models.lab import LabDefinition
from dsoxlab.models.repo import RepoMetadata

runner = CliRunner()

_ANSI = re.compile(r"\x1b\[[0-9;]*m")

META = """\
repo:
  id: demo-training
  category: demo
"""

LAB_CASSE = """\
id: demo-lab
title: Demo lab
level: beginner
skills: []
distros: [any]
doc_url: ftp://example.org/docs/demo/
lab_type: inconnu
runtime:
  type: shell
  workdir: challenge/work
"""


def _plain(sortie: str) -> str:
    """Sortie sans couleur ni repli de ligne.

    Rich replie ses lignes à la largeur du terminal, et un message coupé en
    deux ne se retrouve plus par un simple ``in``. On compare donc des textes
    dont les blancs sont normalisés, des deux côtés.
    """
    return re.sub(r"\s+", " ", _ANSI.sub("", sortie))


def _morceaux(texte: str) -> list[str]:
    """Ce qu'une traduction écrit en toutes lettres, autour de ses paramètres.

    Chercher le **début** du message ne prouverait rien : un message qui ouvre
    sur son paramètre (``'{field}' must be…``) n'aurait pour début qu'une
    apostrophe, et le test passerait sur n'importe quelle sortie. On exige donc
    la présence de **tous** ses fragments fixes, et on vérifie qu'il y a là
    assez de texte pour que la vérification veuille dire quelque chose.
    """
    morceaux = [re.sub(r"\s+", " ", m).strip() for m in re.split(r"\{[^}]*\}", texte)]
    morceaux = [m for m in morceaux if len(m) >= 4]
    assert sum(len(m) for m in morceaux) > 10, f"trop peu de texte fixe : {texte!r}"
    return morceaux


def _catalogue_casse(racine: Path) -> Path:
    """Un dépôt qui rate tout ce que `validate-structure` sait voir.

    `skills` vide et `lab_type` hors énuméré pour les métadonnées, un
    `scenario.md` absent pour la structure, un lien relatif mort et une
    traduction orpheline pour le contenu.
    """
    (racine / "meta.yml").write_text(META, encoding="utf-8")
    dossier = racine / "labs" / "demo" / "premiers-pas"
    tests = dossier / "challenge" / "tests"
    tests.mkdir(parents=True)
    (dossier / "lab.yaml").write_text(LAB_CASSE, encoding="utf-8")
    (dossier / "README.md").write_text(
        "# Demo\n\nVoir [la suite](./absent.md).\n", encoding="utf-8"
    )
    (dossier / "cours.fr.md").write_text("# Cours\n", encoding="utf-8")
    (tests / "test_functional.py").write_text(
        "def test_ok():\n    assert True\n", encoding="utf-8"
    )
    return dossier


def _valide(racine: Path, langue: str, monkeypatch: pytest.MonkeyPatch) -> str:
    """`dsoxlab validate-structure` joué dans une langue, sortie nettoyée."""
    monkeypatch.setenv("DSOXLAB_LANG", langue)
    set_lang(langue)
    try:
        resultat = runner.invoke(
            app, ["validate-structure", "--lab-home", str(racine)]
        )
    finally:
        set_lang("en")
    return _plain(resultat.output)


# ── 1. validate-structure suit la langue ─────────────────────────────────────

def test_les_trois_familles_de_controles_suivent_la_langue(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Structure, métadonnées et contenu : chacune avait sa phrase en dur."""
    _catalogue_casse(tmp_path)

    anglais = _valide(tmp_path, "en", monkeypatch)
    francais = _valide(tmp_path, "fr", monkeypatch)

    for cle in (
        "struct_missing_file",          # scenario.md absent
        "metadata_list_empty",          # skills: []
        "metadata_lab_type_invalid",    # lab_type: inconnu
        "content_broken_links",         # ./absent.md
        "content_missing_english",      # cours.fr.md orphelin
    ):
        for morceau in _morceaux(EN[cle]):
            assert morceau in anglais, f"{cle} absent de la sortie anglaise :\n{anglais}"
        for morceau in _morceaux(FR[cle]):
            assert morceau in francais, f"{cle} absent de la sortie française :\n{francais}"


def test_aucune_phrase_francaise_ne_traverse_la_sortie_anglaise(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Le défaut d'origine, pris par le seul bout qui compte pour l'auteur."""
    _catalogue_casse(tmp_path)

    anglais = _valide(tmp_path, "en", monkeypatch)

    for temoin in ("Fichier manquant", "est vide", "lien(s) relatif(s)", "Valeur invalide"):
        assert temoin not in anglais, anglais


# ── 2. le meta.yml s'affiche, donc il se traduit ─────────────────────────────

def test_un_champ_mal_type_du_meta_se_dit_dans_la_langue(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`infra.hosts` écrit en mapping : la faute la plus naturelle du contrat."""
    (tmp_path / "meta.yml").write_text(
        META + "infra:\n  hosts:\n    web1.lab: {}\n", encoding="utf-8"
    )
    (tmp_path / "labs").mkdir()

    sorties = {}
    for langue in ("en", "fr"):
        monkeypatch.setenv("DSOXLAB_LANG", langue)
        set_lang(langue)
        try:
            resultat = runner.invoke(app, ["list-labs", "--lab-home", str(tmp_path)])
        finally:
            set_lang("en")
        assert resultat.exit_code == 1
        sorties[langue] = _plain(resultat.output)

    for langue, table in (("en", EN), ("fr", FR)):
        for morceau in _morceaux(table["contract_field_not_mapping_list"]):
            assert morceau in sorties[langue], sorties[langue]
    # Et le chemin du fichier reste devant la phrase : sans lui, l'auteur ne
    # sait pas quel fichier corriger.
    assert "meta.yml" in sorties["en"]


def test_le_modele_ne_porte_aucune_phrase_traduite(tmp_path: Path) -> None:
    """Le patron : des faits dans le modèle, la phrase dans la CLI."""
    (tmp_path / "meta.yml").write_text(
        META + "infra:\n  provider: [kvm, incus]\n  providers: []\n", encoding="utf-8"
    )

    with pytest.raises(ContractError) as capture:
        RepoMetadata.from_yaml(tmp_path / "meta.yml")

    exc = capture.value
    assert exc.key == "contract_field_not_mapping"
    assert exc.params["field"] == "infra.providers"
    assert exc.source == tmp_path / "meta.yml"
    # Le texte technique du journal ne doit contenir aucune phrase traduite.
    assert "doit être" not in str(exc) and "must be" not in str(exc)


# ── 3. un lab.yaml illisible reste interne ───────────────────────────────────

def test_un_lab_yaml_illisible_ne_va_qu_au_journal(tmp_path: Path) -> None:
    """Le tri de #139 : ce que personne n'affiche n'a pas à être traduit."""
    (tmp_path / "meta.yml").write_text(META, encoding="utf-8")
    dossier = tmp_path / "labs" / "demo" / "casse"
    dossier.mkdir(parents=True)
    (dossier / "lab.yaml").write_text("- une liste, pas un mapping\n", encoding="utf-8")

    with pytest.raises(LabYamlError):
        LabDefinition.from_yaml(dossier / "lab.yaml")

    # Le scanner l'absorbe, et retient la raison pour le diagnostic.
    scan = scan_catalog(tmp_path)
    assert scan.labs == []
    assert len(scan.illisibles) == 1
    assert "LabYamlError" in scan.illisibles[0][1]


def test_les_coercions_non_traduites_ne_servent_qu_au_lab_yaml() -> None:
    """Le tri repose sur un fait vérifiable, pas sur une promesse de docstring.

    `as_argv` et `as_argv_list` lèvent une `LabYamlError`, dont le texte n'est
    pas traduit. Le jour où `models/repo.py` s'en servirait, un `meta.yml`
    afficherait du français sous `DSOXLAB_LANG=en`, et le tri serait faux sans
    que rien ne le dise.
    """
    repo_py = (Path(dsoxlab.__file__).parent / "models" / "repo.py").read_text(
        encoding="utf-8"
    )
    assert "as_argv" not in repo_py


def test_l_erreur_interne_reste_un_valueerror(tmp_path: Path) -> None:
    """`discovery/scanner.py` ne rattrape que KeyError, ValueError et YAMLError.

    Changer de classe sans hériter de `ValueError` ferait remonter un traceback
    brut sur une commande sans rapport.
    """
    assert issubclass(LabYamlError, ValueError)
    assert issubclass(ContractError, ValueError)


# ── 4. toute clé employée existe des deux côtés ──────────────────────────────

def _cles_employees() -> set[str]:
    """Les clés i18n que les validators et le contrat passent à la CLI.

    Lues dans la source plutôt que listées à la main : une clé ajoutée sans
    traduction doit faire échouer ce test, pas attendre qu'un auteur la voie
    s'afficher en clair.
    """
    racine = Path(dsoxlab.__file__).parent
    fichiers = sorted((racine / "validators").glob("*.py")) + sorted(
        (racine / "models").glob("*.py")
    )
    cles: set[str] = set()
    for chemin in fichiers:
        arbre = ast.parse(chemin.read_text(encoding="utf-8"))
        for noeud in ast.walk(arbre):
            if not isinstance(noeud, ast.Call):
                continue
            nom = getattr(noeud.func, "id", "") or getattr(noeud.func, "attr", "")
            # `ContractError(source, field, key, …)` : la clé est en 3e position.
            if nom == "ContractError" and len(noeud.args) >= 3:
                argument = noeud.args[2]
                if isinstance(argument, ast.Constant) and isinstance(argument.value, str):
                    cles.add(argument.value)
            for kw in noeud.keywords:
                if (
                    kw.arg == "key"
                    and isinstance(kw.value, ast.Constant)
                    and isinstance(kw.value.value, str)
                ):
                    cles.add(kw.value.value)
            # `MetadataIssue("doc_url", "metadata_doc_url_scheme", {...})`
            if nom == "MetadataIssue" and len(noeud.args) >= 2:
                argument = noeud.args[1]
                if isinstance(argument, ast.Constant) and isinstance(argument.value, str):
                    cles.add(argument.value)
    return cles


def test_chaque_cle_employee_existe_en_anglais_et_en_francais() -> None:
    cles = _cles_employees()
    assert len(cles) > 20, f"lecture des sources trop maigre : {sorted(cles)}"
    assert sorted(cle for cle in cles if cle not in EN) == []
    assert sorted(cle for cle in cles if cle not in FR) == []


def test_les_cles_du_contrat_ne_reclament_pas_le_chemin_du_fichier() -> None:
    """La CLI encadre ces phrases du chemin ; le porter aussi le doublerait."""
    for cle in (cle for cle in _cles_employees() if cle.startswith("contract_")):
        assert "{path}" not in EN[cle] and "{path}" not in FR[cle], cle
