"""La traduction d'un `course.yaml` se pose-t-elle sur les bonnes sections ?

Aucun des six catalogues ne déclare de `course.yaml` à ce jour, donc ce chemin
n'est exercé par rien d'autre que ces tests. C'est exactement le genre de code
qui se casse sans bruit le jour où un auteur s'en sert pour la première fois.

L'invariant qui compte est l'appariement **par `id`** : un `course.fr.yaml`
qui ne traduit que deux sections sur six resterait aligné par hasard si on
appariait par position, puis se décalerait au premier ajout, en mettant le
titre d'une section sur une autre.
"""

from __future__ import annotations

from pathlib import Path

from dsoxlab.models.course import CourseManifest

COURS = """\
title: Working with files
sections:
  - id: navigation
    title: Moving around
    file: course/01-navigation.md
  - id: permissions
    title: Permissions
    file: course/02-permissions.md
  - id: liens
    title: Links
    file: course/03-links.md
"""


def _poser(racine: Path, fr: str | None = None) -> Path:
    (racine / "course.yaml").write_text(COURS, encoding="utf-8")
    if fr is not None:
        (racine / "course.fr.yaml").write_text(fr, encoding="utf-8")
    return racine


def test_sans_course_yaml_il_n_y_a_pas_de_manifeste(tmp_path: Path) -> None:
    """Le cas des 374 labs d'aujourd'hui : `course` retombe sur le cours
    entier, ce qui n'est pas une erreur."""
    assert CourseManifest.load(tmp_path) is None


def test_en_anglais_la_traduction_est_ignoree(tmp_path: Path) -> None:
    fr = "title: Travailler avec les fichiers\n"
    manifeste = CourseManifest.load(_poser(tmp_path, fr), lang="en")

    assert manifeste is not None
    assert manifeste.title == "Working with files"


def test_la_traduction_se_pose_par_id_et_non_par_position(tmp_path: Path) -> None:
    """La section traduite est la troisième du fichier français et la deuxième
    de l'original : par position, le titre atterrirait sur « Permissions »."""
    fr = """\
title: Travailler avec les fichiers
sections:
  - id: liens
    title: Les liens
"""
    manifeste = CourseManifest.load(_poser(tmp_path, fr), lang="fr")

    assert manifeste is not None
    assert manifeste.title == "Travailler avec les fichiers"
    titres = {s.id: s.title for s in manifeste.sections}
    assert titres == {
        "navigation": "Moving around",
        "permissions": "Permissions",
        "liens": "Les liens",
    }


def test_une_section_inconnue_de_l_original_est_sans_effet(tmp_path: Path) -> None:
    """Une traduction en avance sur l'original ne doit rien ajouter ni lever :
    c'est l'original qui décide de la liste des sections."""
    fr = "sections:\n  - id: inexistante\n    title: Fantôme\n"
    manifeste = CourseManifest.load(_poser(tmp_path, fr), lang="fr")

    assert manifeste is not None
    assert [s.id for s in manifeste.sections] == ["navigation", "permissions", "liens"]


def test_un_fichier_peut_etre_surcharge(tmp_path: Path) -> None:
    """Un cours traduit peut vivre dans un autre fichier que l'anglais."""
    fr = "sections:\n  - id: navigation\n    file: course/01-navigation.fr.md\n"
    manifeste = CourseManifest.load(_poser(tmp_path, fr), lang="fr")

    assert manifeste is not None
    assert manifeste.sections[0].file == "course/01-navigation.fr.md"
    assert manifeste.sections[0].title == "Moving around", (
        "un champ absent de la traduction garde la valeur de l'original"
    )


def test_une_traduction_absente_laisse_l_original(tmp_path: Path) -> None:
    manifeste = CourseManifest.load(_poser(tmp_path), lang="fr")

    assert manifeste is not None
    assert manifeste.title == "Working with files"


def test_un_champ_hors_contrat_est_ignore(tmp_path: Path) -> None:
    """Comme pour `lab.fr.yaml` et `meta.fr.yml` : seuls `title` et `file` se
    surchargent, le reste d'une traduction n'est jamais lu."""
    fr = "sections:\n  - id: navigation\n    title: Se déplacer\n    duree: 10m\n"
    manifeste = CourseManifest.load(_poser(tmp_path, fr), lang="fr")

    assert manifeste is not None
    assert manifeste.sections[0].title == "Se déplacer"
    assert not hasattr(manifeste.sections[0], "duree")
