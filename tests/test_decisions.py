"""Les fiches de décision (`docs/decisions/`) gardent leur forme et leurs renvois.

Le code renvoie aux ADR au lieu de porter le raisonnement complet (issue #203) :
« # Voir docs/decisions/0002-…md ». Ce renvoi ne vaut que si la fiche existe.
Un fichier renommé, une fiche fusionnée, et le commentaire pointe dans le vide :
le raisonnement a déménagé, puis disparu, sans que rien ne le dise.

Ce fichier tient trois choses :

- chaque fiche a ses sections fixes et sa jumelle dans l'autre langue ;
- l'index liste chaque fiche, dans les deux langues ;
- chaque renvoi `docs/decisions/<fichier>` écrit dans le dépôt mène à un
  fichier qui existe, et chaque lien relatif d'une fiche aussi.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

RACINE = Path(__file__).resolve().parent.parent
DECISIONS = RACINE / "docs" / "decisions"

#: Une fiche : quatre chiffres, un tiret, un nom en minuscules.
_FICHE = re.compile(r"^(\d{4})-[a-z0-9-]+\.md$")

#: Un renvoi écrit n'importe où dans le dépôt. Le nom doit être complet : un
#: gabarit comme « 0002-…md » (avec une ellipse) n'est pas un renvoi.
_RENVOI = re.compile(r"docs/decisions/(\d{4}-[a-z0-9-]+(?:\.fr)?\.md)")

#: Un lien Markdown relatif dans une fiche : `](./x.md)` ou `](../x.md)`.
_LIEN = re.compile(r"\]\((\.{1,2}/[^)#\s]+)(?:#[^)]*)?\)")

SECTIONS = {
    "en": ("**Status:**", "**Date:**", "## Context", "## Decision",
           "## Consequences", "## What would reverse it"),
    "fr": ("**Statut :**", "**Date :**", "## Contexte", "## Décision",
           "## Conséquences", "## Ce qui l'inverserait"),
}

#: Où un renvoi peut s'écrire. Le CHANGELOG en fait partie : il peut citer une
#: fiche, et la citation doit rester vraie.
_EXTENSIONS = {".py", ".md", ".toml", ".yml", ".yaml", ".tf", ".tmpl", ".sh"}
_RACINES_DE_RECHERCHE = ("src", "tests", "tests_e2e", "scripts", "docs", "fuzz",
                         "packer", ".github")


def _fiches_anglaises() -> list[Path]:
    return sorted(p for p in DECISIONS.glob("*.md")
                  if _FICHE.match(p.name) and not p.name.endswith(".fr.md"))


def _fiches() -> list[Path]:
    return sorted(p for p in DECISIONS.glob("*.md") if p.name != "README.md"
                  and p.name != "README.fr.md")


def _jumelle(fiche: Path) -> Path:
    return fiche.with_name(fiche.name.removesuffix(".md") + ".fr.md")


def _fichiers_du_depot() -> list[Path]:
    fichiers = [p for p in RACINE.glob("*") if p.is_file() and p.suffix in _EXTENSIONS]
    for nom in _RACINES_DE_RECHERCHE:
        base = RACINE / nom
        if base.is_dir():
            fichiers += [p for p in base.rglob("*")
                         if p.is_file() and p.suffix in _EXTENSIONS
                         and "__pycache__" not in p.parts]
    return sorted(fichiers)


def renvois_casses(fichiers: list[Path], decisions: Path) -> list[str]:
    """Chaque renvoi `docs/decisions/<fichier>` qui ne mène à aucun fichier."""
    casses: list[str] = []
    for fichier in fichiers:
        try:
            texte = fichier.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        for nom in _RENVOI.findall(texte):
            if not (decisions / nom).is_file():
                casses.append(f"{fichier.name}: docs/decisions/{nom}")
    return casses


def test_le_repertoire_porte_des_fiches() -> None:
    """Un contrôle qui ne trouve rien à contrôler ne doit pas conclure au vert."""
    assert len(_fiches_anglaises()) >= 14, "docs/decisions/ a perdu des fiches"


def test_chaque_fiche_a_sa_jumelle() -> None:
    """Une fiche traduite d'un seul côté se dégrade en silence."""
    noms = {p.name for p in _fiches()}
    orphelines = sorted(
        p.name for p in _fiches()
        if (p.name.endswith(".fr.md") and p.name.removesuffix(".fr.md") + ".md" not in noms)
        or (not p.name.endswith(".fr.md") and not _jumelle(p).is_file())
    )
    assert orphelines == [], f"fiches sans jumelle : {orphelines}"


def test_chaque_fiche_porte_un_nom_conforme() -> None:
    mal_nommees = sorted(
        p.name for p in _fiches()
        if not _FICHE.match(p.name.replace(".fr.md", ".md"))
    )
    assert mal_nommees == [], f"noms hors format NNNN-nom.md : {mal_nommees}"


def test_les_numeros_sont_uniques_et_contigus() -> None:
    numeros = [int(p.name[:4]) for p in _fiches_anglaises()]
    assert numeros == list(range(1, len(numeros) + 1)), (
        f"numéros en double ou avec un trou : {numeros}"
    )


@pytest.mark.parametrize("langue", ["en", "fr"])
def test_chaque_fiche_a_ses_sections(langue: str) -> None:
    """Le format est fixe : un lecteur sait où chercher ce qui l'inverserait."""
    manques: list[str] = []
    for fiche in _fiches_anglaises():
        chemin = fiche if langue == "en" else _jumelle(fiche)
        if not chemin.is_file():
            continue
        texte = chemin.read_text(encoding="utf-8")
        absentes = [s for s in SECTIONS[langue] if s not in texte]
        if absentes:
            manques.append(f"{chemin.name}: {absentes}")
    assert manques == [], "sections manquantes :\n" + "\n".join(manques)


@pytest.mark.parametrize("index", ["README.md", "README.fr.md"])
def test_l_index_liste_chaque_fiche(index: str) -> None:
    """Une fiche que l'index ne cite pas n'est pas lue."""
    texte = (DECISIONS / index).read_text(encoding="utf-8")
    absentes = []
    for fiche in _fiches_anglaises():
        cible = fiche.name if index == "README.md" else _jumelle(fiche).name
        if f"(./{cible})" not in texte:
            absentes.append(cible)
    assert absentes == [], f"{index} ne cite pas : {absentes}"


def test_chaque_renvoi_du_depot_mene_a_une_fiche() -> None:
    """Le cœur du sujet : un `# Voir docs/decisions/…` qui pointe dans le vide."""
    casses = renvois_casses(_fichiers_du_depot(), DECISIONS)
    assert casses == [], (
        "renvois vers une fiche absente :\n" + "\n".join(casses)
        + "\nRenomme le renvoi, ou rétablis la fiche."
    )


def test_le_code_renvoie_effectivement_aux_fiches() -> None:
    """Sans aucun renvoi, le contrôle précédent passerait à vide."""
    fichiers = _fichiers_du_depot()
    cites = {nom for f in fichiers if f.suffix in {".py", ".toml"}
             for nom in _RENVOI.findall(f.read_text(encoding="utf-8"))}
    assert len(cites) >= 5, f"trop peu de renvois depuis le code : {sorted(cites)}"


def test_les_liens_relatifs_des_fiches_menent_quelque_part() -> None:
    casses = []
    for fiche in sorted(DECISIONS.glob("*.md")):
        for cible in _LIEN.findall(fiche.read_text(encoding="utf-8")):
            if not (fiche.parent / cible).resolve().is_file():
                casses.append(f"{fiche.name}: {cible}")
    assert casses == [], "liens morts :\n" + "\n".join(casses)


def test_le_detecteur_voit_un_renvoi_casse(tmp_path: Path) -> None:
    """Le contrôle doit savoir refuser : on lui montre un renvoi faux.

    Le nom est assemblé à l'exécution pour que ce fichier-ci ne porte lui-même
    aucun renvoi cassé que le contrôle du dépôt relèverait.
    """
    decisions = tmp_path / "docs" / "decisions"
    decisions.mkdir(parents=True)
    present = "0001-" + "existe.md"
    absent = "9999-" + "nexiste-pas.md"
    (decisions / present).write_text("# fiche\n", encoding="utf-8")
    source = tmp_path / "module.py"
    prefixe = "docs/" + "decisions/"
    source.write_text(
        f"# Voir {prefixe}{present}\n# Voir {prefixe}{absent}\n",
        encoding="utf-8",
    )

    casses = renvois_casses([source], decisions)

    assert casses == [f"module.py: {prefixe}{absent}"]
