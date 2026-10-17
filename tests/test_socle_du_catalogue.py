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
from dsoxlab.services.scaffold_socle import version_du_moteur

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


def _liste_bash(script: str, nom: str) -> list[str]:
    """Les éléments d'un tableau bash déclaré sur une ou plusieurs lignes."""
    trouve = re.search(rf"^\s*{nom}=\((.*?)\)\s*$", script, re.MULTILINE | re.DOTALL)
    assert trouve is not None, f"le tableau {nom} est absent du workflow"
    return trouve.group(1).split()


def _script_du_bundle(catalogue: Path) -> str:
    workflow = yaml.safe_load(
        (catalogue / ".github" / "workflows" / "release.yml").read_text(encoding="utf-8")
    )
    for job in workflow["jobs"].values():
        for step in job.get("steps") or []:
            if step.get("id") == "bundle":
                return str(step["run"])
    raise AssertionError("aucun step `bundle` dans release.yml")


def test_la_chaine_de_release_est_produite(catalogue: Path) -> None:
    """Un catalogue neuf peut publier, sinon il faut tout recopier à la main.

    Mesuré le 2026-10-17 : `new catalog` ne produisait que `ci.yml`, et quatre
    catalogues ont dû recevoir leur chaîne de publication par copie depuis un
    dépôt frère. Un tag posé sur un dépôt sans `release.yml` ne publie rien, et
    ne le dit pas.
    """
    for chemin in (
        ".github/workflows/release.yml",
        ".github/workflows/attester.yml",
        "RELEASING.md",
        "RELEASING.fr.md",
    ):
        assert (catalogue / chemin).is_file(), f"{chemin} manque au socle"

    workflow = yaml.safe_load(
        (catalogue / ".github" / "workflows" / "release.yml").read_text(encoding="utf-8")
    )
    # Le déclencheur est un tag : c'est ce qui fait qu'on republie en DÉPLAÇANT
    # le tag, et non en relançant un run.
    assert workflow[True]["push"]["tags"] == ["v*"], "le workflow ne part pas sur un tag"
    # L'attestation est appelée, pas recopiée dans le job de build : c'est la
    # frontière qu'exige SLSA Build Level 3.
    appels = [
        str(job.get("uses", ""))
        for job in workflow["jobs"].values()
        if job.get("uses")
    ]
    assert any("attester.yml" in appel for appel in appels), (
        "release.yml n'appelle pas attester.yml : la provenance serait signée "
        "par le processus qui construit l'archive, soit le niveau 2 et non 3."
    )


def test_le_bundle_n_exige_que_ce_que_le_socle_produit(catalogue: Path) -> None:
    """LE CLIQUET. Chaque chemin REQUIS du bundle existe dans un catalogue neuf.

    C'est la faute exacte qui a fait qu'un premier tag n'a rien publié : le
    workflow copié réclamait `meta.fr.yml` et `curriculums.yml`, absents du
    dépôt cible, et `tar` sortait en 2 sous `set -euo pipefail`. Le message
    « Cannot stat » se perdait au milieu d'un job de build.

    Sans ce test, la dette revient au premier chemin ajouté au bundle sans être
    ajouté au socle.
    """
    script = _script_du_bundle(catalogue)
    absents = [
        chemin for chemin in _liste_bash(script, "REQUIS")
        if not (catalogue / chemin).exists()
    ]
    assert not absents, (
        f"le bundle exige {absents}, qu'un catalogue neuf ne porte pas. "
        "Soit le socle doit les produire, soit ils sont FACULTATIFS."
    )


def test_le_bundle_refuse_un_requis_manquant_en_le_nommant(catalogue: Path) -> None:
    """Un REQUIS absent doit arrêter la publication, et dire lequel.

    Un bundle tolérant publierait une archive amputée, ce qui est pire : elle a
    l'air d'une release. On vérifie donc les deux moitiés du contrat, le refus
    ET le message.
    """
    script = _script_du_bundle(catalogue)
    assert 'printf ' in script and "Release impossible" in script, (
        "le bundle ne nomme pas le chemin manquant"
    )
    assert "exit 1" in script, "le bundle ne s'arrête pas sur un REQUIS absent"
    # Et les facultatifs sont bien testés avant d'être ajoutés.
    for chemin in _liste_bash(script, "FACULTATIFS"):
        assert chemin not in _liste_bash(script, "REQUIS"), (
            f"{chemin} est à la fois requis et facultatif"
        )
    assert '[ -e "$chemin" ] && A_EMPAQUETER+=("$chemin")' in script, (
        "un facultatif est ajouté sans être testé"
    )


#: Les fichiers du socle qui EXÉCUTENT le moteur, par opposition à ceux qui
#: disent à un apprenant de l'installer.
_EXECUTABLES = (".github/workflows/ci.yml", ".pre-commit-config.yaml")

#: Un appel nu : le moteur invoqué sans contrainte de version. `uvx dsoxlab`,
#: `uv tool install dsoxlab` et `entry: dsoxlab` en sont, et chacun prend une
#: version que personne n'a déclarée.
_APPEL_NU = re.compile(
    r"(?:uvx|uv tool install)\s+(?:'dsoxlab'|dsoxlab)(?![>=\w.-])"
    r"|entry:\s+dsoxlab\b"
)


def _lignes_de_code(texte: str) -> list[str]:
    """Les lignes qui ne sont pas des commentaires.

    Un commentaire qui CITE `uvx dsoxlab` pour expliquer pourquoi on ne
    l'emploie pas ne doit pas faire rougir le test : sinon la justification
    devient impossible à écrire.
    """
    return [ligne for ligne in texte.splitlines()
            if not ligne.lstrip().startswith("#")]


def test_le_socle_ne_lance_jamais_le_moteur_sans_borne(catalogue: Path) -> None:
    """LE CLIQUET. Aucun appel au moteur n'est nu dans ce qui s'exécute.

    Mesuré le 2026-10-17 sur sept catalogues fraîchement créés : leur CI
    portait `uv tool install dsoxlab` et leur pre-commit
    `entry: dsoxlab validate-structure`. Le second est le pire, car il emploie
    le moteur du PATH, c'est-à-dire ce qui traîne sur la machine du
    contributeur.

    Les douze catalogues établis venaient d'être alignés le même jour sur une
    borne commune. Sans ce test, tout catalogue neuf naît avec la dette qu'on
    vient de solder.
    """
    nus: list[str] = []
    for relatif in _EXECUTABLES:
        chemin = catalogue / relatif
        assert chemin.is_file(), f"{relatif} manque au socle"
        for rang, ligne in enumerate(_lignes_de_code(chemin.read_text("utf-8")), 1):
            if _APPEL_NU.search(ligne):
                nus.append(f"{relatif}:{rang} → {ligne.strip()}")
    assert not nus, (
        "le socle lance le moteur sans borne de version :\n  "
        + "\n  ".join(nus)
        + "\n\nUne version non déclarée est « ce que PyPI publie aujourd'hui », "
        "ou pire, ce qui traîne sur la machine."
    )


def test_la_borne_du_socle_est_la_version_qui_ecrit(catalogue: Path) -> None:
    """La borne vaut la version du moteur, pas une valeur figée au gabarit.

    Un catalogue produit par une version suppose au moins cette version : c'est
    la seule borne affirmable sans analyser son contenu. Une valeur écrite en
    dur dans le gabarit se périmerait au premier contrat qui gagne un champ,
    et c'est exactement le défaut qu'on corrige.
    """
    attendue = version_du_moteur()
    bornes: set[str] = set()
    for relatif in _EXECUTABLES:
        texte = (catalogue / relatif).read_text(encoding="utf-8")
        for ligne in _lignes_de_code(texte):
            bornes |= set(re.findall(r"dsoxlab>=([0-9][0-9.]*)", ligne))
    assert bornes, "aucune borne trouvée dans ce qui s'exécute"
    assert bornes == {attendue}, (
        f"les bornes valent {sorted(bornes)}, attendu {attendue} : la version "
        "qui écrit le catalogue."
    )
