"""`new catalog` produit un catalogue conforme sans retouche, pas une graine.

Il écrivait DEUX fichiers, `meta.yml` et `.gitignore`. Tout le reste — README,
gouvernance, outillage, intégration continue — était donc bâti à la main douze
fois, et douze fois différemment. Mesuré à la racine des douze catalogues avant
d'écrire ces tests :

    invariant (12/12) : .gitignore, LICENSE, README.md, README.fr.md,
                        conftest.py, labs/, meta.yml, pyproject.toml, scripts/
    les deux derniers : 14 et 19 entrées, contre 28 à 43 pour les dix autres

Et sur les README, 1 931 octets sans un seul titre de niveau 2 d'un côté,
33 000 de l'autre.

Ces tests ne vérifient pas que les fichiers EXISTENT : ils vérifient que ce qui
est produit se tient. Contrôler la présence d'un fichier ne prouve pas qu'il
fonctionne, et c'est la règle du dépôt.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest
import yaml

from dsoxlab.services.scaffold import creer_catalogue, creer_lab

#: Les quatorze sections de la structure de référence, dans l'ordre. Elle n'est
#: pas inventée : c'est celle que `terraform`, `linux` et `devsecops`
#: portaient déjà, à un titre près.
SECTIONS_EN = [
    "What it is", "Requirements", "Install", "Your first lab",
    "Keeping it up to date", "How it works", "The declarative contract",
    "The lab lifecycle", "Runtimes", "The validation model",
    "Scoring, hints, progress", "Catalog", "Contributing", "License",
]
SECTIONS_FR = [
    "Ce que c'est", "Prérequis", "Installation", "Votre premier lab",
    "Garder à jour", "Comment ça marche", "Le contrat déclaratif",
    "Le cycle de vie d'un lab", "Les runtimes", "Le modèle de validation",
    "Score, indices, avancement", "Catalogue", "Contribuer", "Licence",
]


@pytest.fixture
def catalogue(tmp_path: Path) -> Path:
    """Un catalogue neuf, tel que `dsoxlab new catalog` le produit."""
    creer_catalogue("demo", tmp_path)
    return tmp_path / "demo"


def _titres(chemin: Path) -> list[str]:
    return re.findall(r"^#{2,4} +(.+)$", chemin.read_text(encoding="utf-8"),
                      re.MULTILINE)


# ── Le socle ────────────────────────────────────────────────────────────────


def test_l_invariant_des_douze_catalogues_est_produit(catalogue: Path) -> None:
    """Les neuf entrées que les douze catalogues portent tous.

    Mesuré sur le disque avant d'écrire ce test, et non choisi : c'est
    l'intersection des douze.
    """
    for relatif in (".gitignore", "LICENSE", "README.md", "README.fr.md",
                    "conftest.py", "meta.yml", "pyproject.toml"):
        assert (catalogue / relatif).is_file(), f"{relatif} manque"
    assert (catalogue / "labs").is_dir()


def test_les_deux_readme_portent_les_quatorze_sections(catalogue: Path) -> None:
    """La structure de référence, dans les deux langues.

    C'est l'écart que ce socle ferme : quatre des douze catalogues n'avaient
    aucun titre de niveau 2, donc zéro de ces quatorze sections.
    """
    for nom, attendues in (("README.md", SECTIONS_EN),
                           ("README.fr.md", SECTIONS_FR)):
        titres = _titres(catalogue / nom)
        manquantes = [
            section for section in attendues
            if not any(section.lower() in t.lower() for t in titres)
        ]
        assert not manquantes, f"{nom} : sections manquantes {manquantes}"


def test_le_readme_ne_porte_aucun_tiret_cadratin(catalogue: Path) -> None:
    """La règle d'écriture l'interdit en français, et le socle la tient.

    Un catalogue en portait 9 dans son README français, dont 6 produits par
    son propre générateur de table.
    """
    assert "—" not in (catalogue / "README.fr.md").read_text(encoding="utf-8")


def test_le_conftest_porte_le_helper_bilingue(catalogue: Path) -> None:
    """`message(en=…, fr=…)` doit vivre DANS le catalogue, pas dans dsoxlab.

    Un test de lab doit rester jouable par un simple `pytest`, sans l'outil
    installé : c'est le test de non-couplage. Un `from dsoxlab… import` en tête
    d'un fichier de tests le casserait.
    """
    source = (catalogue / "conftest.py").read_text(encoding="utf-8")

    assert "def message(en: str, fr: str) -> str:" in source
    assert "DSOXLAB_LANG" in source
    assert "import dsoxlab" not in source, (
        "le conftest d'un catalogue ne doit jamais importer dsoxlab : un lab "
        "doit rester jouable par un simple pytest"
    )


def test_le_helper_bilingue_fonctionne(catalogue: Path,
                                       monkeypatch: pytest.MonkeyPatch) -> None:
    """Vérifier n'est pas parser : on EXÉCUTE le helper produit."""
    espace: dict[str, object] = {}
    source = (catalogue / "conftest.py").read_text(encoding="utf-8")
    exec(compile(source, str(catalogue / "conftest.py"), "exec"), espace)  # noqa: S102
    message = espace["message"]

    monkeypatch.setenv("DSOXLAB_LANG", "fr")
    assert message(en="missing", fr="absent") == "absent"  # type: ignore[operator]
    monkeypatch.setenv("DSOXLAB_LANG", "en")
    assert message(en="missing", fr="absent") == "missing"  # type: ignore[operator]
    monkeypatch.delenv("DSOXLAB_LANG")
    assert message(en="missing", fr="absent") == "missing", (  # type: ignore[operator]
        "l'anglais est le défaut, comme partout dans l'outil"
    )


def test_la_licence_est_le_texte_nu(catalogue: Path) -> None:
    """GitHub ne reconnaît une licence qu'à son texte officiel SANS en-tête.

    Un paragraphe d'attribution ajouté au-dessus rend le fichier
    méconnaissable, le dépôt est rapporté en `NOASSERTION`, et le contrôle
    License de Scorecard tombe de 10 à 9.
    """
    texte = (catalogue / "LICENSE").read_text(encoding="utf-8")

    assert texte.startswith("Attribution 4.0 International"), (
        "la licence doit commencer par son texte officiel, sans en-tête"
    )
    assert "Copyright (c)" not in texte.split("\n", 3)[0]


def test_le_workflow_et_les_hooks_sont_bien_formes(catalogue: Path) -> None:
    """Un YAML produit cassé serait découvert au premier push, pas avant."""
    for relatif in (".github/workflows/ci.yml", ".pre-commit-config.yaml",
                    "meta.yml", "meta.fr.yml"):
        chemin = catalogue / relatif
        assert chemin.is_file(), f"{relatif} manque"
        yaml.safe_load(chemin.read_text(encoding="utf-8"))


def test_les_actions_du_workflow_sont_epinglees_par_sha(catalogue: Path) -> None:
    """Un tag est déplaçable, un SHA non.

    C'est la règle de ce projet, et un catalogue produit par l'outil ne doit
    pas démarrer en la violant.
    """
    source = (catalogue / ".github" / "workflows" / "ci.yml").read_text(
        encoding="utf-8")
    utilisations = re.findall(r"uses: +(\S+)", source)

    assert utilisations, "le workflow produit n'utilise aucune action"
    for action in utilisations:
        reference = action.split("@", 1)[-1]
        assert re.fullmatch(r"[0-9a-f]{40}", reference), (
            f"{action} n'est pas épinglée par un SHA de 40 caractères"
        )


# ── Les garde-fous produits ─────────────────────────────────────────────────


def test_les_garde_fous_passent_sur_un_catalogue_neuf(catalogue: Path) -> None:
    """Un squelette dont la suite est rouge d'emblée apprend à ignorer le rouge.

    Le garde-fou « aucun lab n'a disparu en silence » échouait sur un
    catalogue neuf, qui n'a légitimement aucun lab. Il skippe désormais, et
    n'échoue que si `labs/` porte des répertoires sans `lab.yaml` lisible.
    """
    resultat = pytest.main([
        str(catalogue / "tests"), "-q", "--no-header",
        "-p", "no:cacheprovider",
    ])

    assert resultat == 0, "les garde-fous produits doivent passer sans retouche"


# ── `new lab` ───────────────────────────────────────────────────────────────


def test_un_lab_cree_est_bilingue(catalogue: Path) -> None:
    """La règle du projet veut tout ce qui s'affiche en deux langues.

    Un lab créé par l'outil n'avait aucune version française : il était donc
    immédiatement non conforme, et `validators/content.py` le signalait.
    """
    creer_lab("premier", catalogue, runtime="shell")
    base = catalogue / "labs" / "premier"

    for nom in ("README.md", "README.fr.md", "scenario.md", "scenario.fr.md",
                "lab.yaml", "lab.fr.yaml"):
        assert (base / nom).is_file(), f"{nom} manque"


def test_le_fichier_sans_suffixe_est_en_anglais(catalogue: Path) -> None:
    """La convention réserve le fichier sans suffixe à l'anglais.

    Les gabarits étaient écrits en FRANÇAIS dans `README.md` et `scenario.md` :
    un auteur qui remplissait les blancs produisait un catalogue dont l'anglais
    était du français.
    """
    creer_lab("premier", catalogue, runtime="shell")
    base = catalogue / "labs" / "premier"

    assert "TO FILL IN" in (base / "README.md").read_text(encoding="utf-8")
    assert "À remplir" in (base / "README.fr.md").read_text(encoding="utf-8")
    assert "TO FILL IN" in (base / "scenario.md").read_text(encoding="utf-8")
    assert "À remplir" in (base / "scenario.fr.md").read_text(encoding="utf-8")


def test_un_lab_cree_entre_dans_une_section(catalogue: Path) -> None:
    """Sans section, le lab reste jouable mais n'a aucun ordre pédagogique.

    `discovery/scanner.py` dérive `bloc` et `bloc_order` de la position du lab
    dans `meta.yml: sections[].labs[]`, et `dsoxlab next` s'en sert.
    """
    creation = creer_lab("premier", catalogue, runtime="shell")

    assert creation.section == "premiers-pas"
    meta = yaml.safe_load((catalogue / "meta.yml").read_text(encoding="utf-8"))
    declares = [
        chemin
        for section in meta["sections"]
        for chemin in (section.get("labs") or [])
    ]
    assert declares == ["premier"]


def test_l_ordre_de_creation_est_l_ordre_pedagogique(catalogue: Path) -> None:
    """Un lab créé en second doit venir en second.

    L'insertion ajoutait en TÊTE de la liste, donc les labs sortaient dans
    l'ordre inverse de leur création. Mesuré sur un catalogue neuf : `premier`
    sortait en position 2 et `second` en position 1.
    """
    creer_lab("premier", catalogue, runtime="shell")
    creer_lab("second", catalogue, runtime="shell")

    meta = yaml.safe_load((catalogue / "meta.yml").read_text(encoding="utf-8"))
    declares = [
        chemin
        for section in meta["sections"]
        for chemin in (section.get("labs") or [])
    ]
    assert declares == ["premier", "second"]


def test_le_meta_garde_ses_commentaires(catalogue: Path) -> None:
    """L'inscription se fait par texte, pas par un aller-retour YAML.

    Un `safe_load` suivi d'un `dump` perdrait tous les commentaires du
    `meta.yml`, et ce fichier est à moitié fait de commentaires qui expliquent
    le contrat. Les effacer pour ajouter une ligne serait un mauvais échange.
    """
    avant = (catalogue / "meta.yml").read_text(encoding="utf-8")
    nombre_avant = avant.count("#")

    creer_lab("premier", catalogue, runtime="shell")

    apres = (catalogue / "meta.yml").read_text(encoding="utf-8")
    assert apres.count("#") == nombre_avant, (
        "l'inscription du lab a effacé des commentaires du meta.yml"
    )
