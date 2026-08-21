"""Ce que la suite unitaire ne peut pas voir : la distribution elle-même.

Un point d'entrée mal déclaré, un fichier de données oublié dans la roue, un
paquet installé en « editable » qui masque le défaut : rien de tout cela
n'apparaît quand les tests importent le paquet depuis `src/`. Ces contrôles
portent donc sur l'archive construite et sur l'environnement où elle a été
installée, avant même de lancer la moindre commande.

Pour vérifier qu'ils mordent : exclure `src/dsoxlab/templates/demo` de la cible
`wheel` dans `pyproject.toml` fait rougir le premier test, puis le parcours
complet, qui n'a soudain plus de catalogue à installer.
"""

from __future__ import annotations

import zipfile
from pathlib import Path

from conftest import DEPOT, Installation, Poste

#: Ce que la roue doit porter en plus du code. Aucun de ces fichiers n'est
#: importable : ce sont des données lues par `importlib.resources`, donc
#: exactement la catégorie qu'un empaquetage rate en silence.
DONNEES_ATTENDUES = (
    # Le marqueur PEP 561, sans lequel les dépôts de labs perdent le typage.
    "dsoxlab/py.typed",
    # Le catalogue de démonstration : le premier lab que voit un utilisateur.
    "dsoxlab/templates/demo/meta.yml",
    # Sa traduction française. Le catalogue packagé est l'exemple de référence
    # du mécanisme `meta.<langue>.yml` : absent de la roue, il l'enseignerait
    # sans le montrer, et une session française lirait des titres anglais.
    "dsoxlab/templates/demo/meta.fr.yml",
    "dsoxlab/templates/demo/labs/demo/premiers-pas/lab.yaml",
    "dsoxlab/templates/demo/labs/demo/premiers-pas/challenge/hints.yaml",
    "dsoxlab/templates/demo/labs/demo/premiers-pas/challenge/tests/test_functional.py",
    # L'infra packagée : un dépôt de labs ne fournit ni Terraform ni cloud-init.
    "dsoxlab/templates/terraform/kvm/main.tf",
    "dsoxlab/templates/cloud-init/almalinux.yaml.tmpl",
)


def _contenu(roue: Path) -> list[str]:
    with zipfile.ZipFile(roue) as archive:
        return archive.namelist()


def _fichier_de_la_roue(roue: Path, suffixe: str) -> str:
    """Le contenu texte du premier membre dont le nom finit par *suffixe*."""
    with zipfile.ZipFile(roue) as archive:
        for nom in archive.namelist():
            if nom.endswith(suffixe):
                return archive.read(nom).decode("utf-8")
    raise AssertionError(f"{suffixe} absent de la roue {roue.name}")


def test_la_roue_embarque_les_fichiers_de_donnees(installation: Installation) -> None:
    """Le code seul ne suffit pas : sans ces fichiers, l'outil ne sert à rien."""
    presents = set(_contenu(installation.roue))
    manquants = [attendu for attendu in DONNEES_ATTENDUES if attendu not in presents]

    assert not manquants, (
        f"la roue {installation.roue.name} ne porte pas ses données : {manquants}"
    )


def test_le_point_d_entree_console_est_declare(installation: Installation) -> None:
    """`dsoxlab` doit exister comme commande, pas seulement comme module."""
    declaration = _fichier_de_la_roue(installation.roue, ".dist-info/entry_points.txt")

    # Espaces retirés : le format tolère « nom = cible » comme « nom=cible »,
    # et ce test porte sur la déclaration, pas sur sa mise en page.
    compacte = "".join(declaration.split())

    assert "[console_scripts]" in declaration, declaration
    assert "dsoxlab=dsoxlab.cli:main" in compacte, declaration


def test_l_outil_teste_est_bien_la_roue_installee(installation: Installation) -> None:
    """La garantie sans laquelle tout le reste perd son intérêt.

    Trois faits, chacun vérifiable : le binaire est celui du venv éphémère, le
    paquet y est posé en dur (pas un lien vers `src/`), et rien dans ce venv ne
    ramène l'arborescence source sur le chemin d'import.
    """
    assert installation.binaire.is_file(), "aucun script console installé"
    assert installation.venv in installation.binaire.parents

    pose = installation.site_packages / "dsoxlab"
    assert (pose / "cli.py").is_file(), "le paquet n'est pas installé en dur"
    assert (pose / "templates" / "demo" / "meta.yml").is_file(), (
        "les données de la roue ne sont pas arrivées dans site-packages"
    )

    # Une installation editable pose un `.pth` ou un module `__editable__…`
    # qui ajoute `src/` au sys.path. Il n'y en a pas ici, et c'est la
    # différence entre tester l'empaquetage et le contourner.
    renvois = [
        chemin
        for chemin in installation.site_packages.glob("*.pth")
        if str(DEPOT) in chemin.read_text(encoding="utf-8")
    ]
    editables = list(installation.site_packages.glob("__editable__*"))
    assert not renvois, f"un .pth ramène le dépôt sur le sys.path : {renvois}"
    assert not editables, f"installation editable détectée : {editables}"


def test_la_version_annoncee_est_celle_de_la_roue(
    poste: Poste, installation: Installation
) -> None:
    """Le programme installé dit la version qu'il porte, pas une autre."""
    version = installation.roue.name.split("-")[1]
    resultat = poste.lance("--version")

    assert resultat.returncode == 0, resultat.stderr
    assert version in resultat.stdout, (version, resultat.stdout)


def test_l_aide_annonce_les_commandes_du_parcours(poste: Poste) -> None:
    """`--help` est la première chose que lit un inconnu : elle doit répondre."""
    resultat = poste.lance("--help")

    assert resultat.returncode == 0, resultat.stderr
    for commande in ("demo", "list-labs", "run", "check", "scores"):
        assert commande in resultat.stdout, f"{commande} absente de l'aide"


def test_une_commande_inconnue_sort_en_erreur(poste: Poste) -> None:
    """Contrôle du harnais autant que de l'outil.

    Si le lanceur rendait toujours 0, toutes les assertions de code de retour
    de cette suite seraient décoratives. Celle-ci le prouve du contraire.
    """
    resultat = poste.lance("commande-qui-n-existe-pas")

    assert resultat.returncode != 0
