"""La documentation d'auteur dit ce que le moteur fait (relecture du 2026-11-14).

Quatre écarts relevés en écrivant le volet auteur de la formation, chacun tenu
ici par ce qu'il compare : le code d'un côté, le texte de l'autre.
"""

from __future__ import annotations

import json
from pathlib import Path

from dsoxlab.i18n.strings import en, fr
from dsoxlab.services import scaffold_socle

RACINE = Path(__file__).resolve().parents[1]


def test_le_contrat_documente_chaque_champ_de_learning_sync() -> None:
    schema = json.loads((RACINE / "schemas" / "meta.schema.json").read_text(encoding="utf-8"))
    champs = schema["properties"]["learning"]["properties"]["sync"]["properties"]
    for page in ("contract-v1.md", "contract-v1.fr.md"):
        texte = (RACINE / "docs" / page).read_text(encoding="utf-8")
        absents = [c for c in champs if f"`{c}`" not in texte]
        assert not absents, f"{page} ne documente pas learning.sync : {absents}"


def test_le_contributing_genere_ne_dit_plus_de_lancer_list_labs_d_abord() -> None:
    # Caduc depuis la 0.1.97 : validate-structure voit les labs qu'il ne charge pas.
    for texte in (scaffold_socle.CONTRIBUTING_EN, scaffold_socle.CONTRIBUTING_FR):
        assert "list-labs" not in texte, "le CONTRIBUTING généré conseille encore list-labs d'abord"


def test_l_aide_de_new_catalog_nomme_le_conftest_qu_il_ecrit() -> None:
    assert "conftest.py" in scaffold_socle.fichiers_du_socle("essai")
    for chaines in (en.STRINGS, fr.STRINGS):
        aide = chaines["cmd_new_catalog_help"]
        assert "conftest.py" in aide, f"l'aide de new catalog ne nomme pas conftest.py : {aide!r}"


def test_la_doc_auteur_ne_dit_plus_que_new_catalog_n_ecrit_aucun_conftest() -> None:
    for page, phrase in (("catalog-author.md", "writes none"), ("catalog-author.fr.md", "n'en écrit aucun")):
        assert phrase not in (RACINE / "docs" / page).read_text(encoding="utf-8"), page
