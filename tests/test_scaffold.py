"""Créer un squelette conforme au contrat (issue #88).

Écrire un catalogue supposait de retenir le contrat, ou de copier un dépôt
existant. Les deux chemins produisent les mêmes erreurs, et la sanction est
muette : un `lab.yaml` qui lève au parsing n'est jamais examiné par
`validate-structure`, si bien qu'un débutant obtient un catalogue qui « passe la
validation » et n'affiche aucun lab.

Ce module éprouve donc les deux bouts, et pas seulement la présence des
fichiers :

- le squelette est **découvert** (donc son YAML se charge vraiment) ;
- il passe `validate-structure` **sans retouche** ;
- il est conforme aux **schémas publiés**, ce qui garantit qu'il produit du v1
  et non une variante ;
- et son test **échoue**, parce qu'un squelette vert d'emblée apprendrait la
  mauvaise habitude.

Le premier point n'est pas théorique : la première version de ce générateur
écrivait `description: À remplir : ce que…`, dont le second deux-points casse le
YAML. Le lab disparaissait, et `validate-structure` annonçait pourtant « tous
les labs sont valides ».
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest
import yaml

from dsoxlab.discovery.scanner import discover_labs
from dsoxlab.services import scaffold
from dsoxlab.validators.structure import validate_structure

RACINE = Path(__file__).resolve().parent.parent


def _catalogue(tmp_path: Path, identifiant: str = "essai") -> Path:
    return scaffold.creer_catalogue(identifiant, tmp_path).racine


# ── Le catalogue ────────────────────────────────────────────────────────────

def test_un_catalogue_neuf_porte_ce_que_le_contrat_exige(tmp_path: Path) -> None:
    racine = _catalogue(tmp_path)

    assert (racine / "meta.yml").is_file()
    assert (racine / "labs").is_dir()
    assert (racine / ".gitignore").is_file()
    # `instructor bootstrap` y pose la clé : le répertoire doit exister.
    assert (racine / "ssh").is_dir()


def test_le_meta_produit_se_charge_vraiment(tmp_path: Path) -> None:
    """Un meta.yml qui ne se charge pas rend le catalogue muet."""
    racine = _catalogue(tmp_path, "mon-domaine")
    document = yaml.safe_load((racine / "meta.yml").read_text(encoding="utf-8"))

    assert document["repo"]["id"] == "mon-domaine"
    assert document["repo"]["category"] == "mon-domaine"


def test_un_catalogue_n_ecrase_jamais_un_repertoire(tmp_path: Path) -> None:
    """Ce répertoire porte peut-être du travail : on ne passe pas dessus."""
    _catalogue(tmp_path)

    with pytest.raises(scaffold.ScaffoldError) as exc:
        _catalogue(tmp_path)
    assert "essai" in str(exc.value)


# ── Le lab ──────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("runtime", ["shell", "vm"])
def test_un_lab_neuf_est_decouvert(tmp_path: Path, runtime: str) -> None:
    """Le critère qui compte : découvert, donc son YAML se charge.

    Vérifier la présence des fichiers ne suffirait pas — c'est exactement ce
    qui laissait passer un `lab.yaml` cassé.
    """
    racine = _catalogue(tmp_path)
    scaffold.creer_lab("mon-lab", racine, runtime=runtime)

    labs = discover_labs(racine)

    assert [lab.id for lab in labs] == ["mon-lab"]
    assert labs[0].runtime.type.value == runtime


@pytest.mark.parametrize("runtime", ["shell", "vm"])
def test_un_lab_neuf_passe_la_validation_sans_retouche(
    tmp_path: Path, runtime: str,
) -> None:
    racine = _catalogue(tmp_path)
    scaffold.creer_lab("mon-lab", racine, runtime=runtime)

    rapport = validate_structure(discover_labs(racine)[0])

    assert not rapport.issues, [i.key for i in rapport.issues]


def test_le_squelette_shell_declare_son_workdir(tmp_path: Path) -> None:
    racine = _catalogue(tmp_path)
    scaffold.creer_lab("mon-lab", racine, runtime="shell")

    lab = discover_labs(racine)[0]

    assert lab.runtime.workdir
    assert (lab.path / lab.runtime.workdir).is_dir()


def test_le_squelette_vm_livre_ses_deux_playbooks(tmp_path: Path) -> None:
    """Le contrat les exige, et leur absence refuse le lab."""
    racine = _catalogue(tmp_path)
    creation = scaffold.creer_lab("mon-lab", racine, runtime="vm")

    assert (creation.racine / "setup.yaml").is_file()
    assert (creation.racine / "cleanup.yaml").is_file()
    assert discover_labs(racine)[0].runtime.targets


def test_les_playbooks_produits_se_chargent(tmp_path: Path) -> None:
    """Un playbook au YAML cassé n'échouerait qu'au premier `run`."""
    racine = _catalogue(tmp_path)
    creation = scaffold.creer_lab("mon-lab", racine, runtime="vm")

    for nom in ("setup.yaml", "cleanup.yaml"):
        document = yaml.safe_load((creation.racine / nom).read_text(encoding="utf-8"))
        assert isinstance(document, list) and document[0]["hosts"] == "lab_target"


# ── Le test généré : il doit échouer ────────────────────────────────────────

def test_le_test_genere_echoue_tant_qu_il_n_est_pas_ecrit(tmp_path: Path) -> None:
    """Un squelette vert d'emblée apprendrait la mauvaise habitude.

    Et un test `skip` ne vaut pas mieux : il ne dit ni que le travail reste à
    faire, ni qu'il est fait. Un test rouge dit la première chose, qui est
    celle dont l'auteur a besoin.
    """
    racine = _catalogue(tmp_path)
    creation = scaffold.creer_lab("mon-lab", racine, runtime="shell")
    tests = creation.racine / "challenge" / "tests"

    resultat = subprocess.run(
        [sys.executable, "-m", "pytest", str(tests), "-q"],
        capture_output=True, text=True, check=False, timeout=120,
    )

    assert resultat.returncode != 0, "le test généré doit échouer, pas passer"
    assert "skip" not in resultat.stdout.lower(), (
        "un test sauté ne dit pas que le travail reste à faire"
    )


# ── Conformité aux schémas publiés ──────────────────────────────────────────

@pytest.mark.parametrize("runtime", ["shell", "vm"])
def test_le_squelette_est_conforme_au_schema_publie(
    tmp_path: Path, runtime: str,
) -> None:
    """Le générateur doit produire du v1, pas une variante.

    Le contrat est gelé et ses schémas sont publiés : les ignorer laisserait le
    générateur diverger sans que rien ne le dise.
    """
    jsonschema = pytest.importorskip("jsonschema")

    racine = _catalogue(tmp_path)
    creation = scaffold.creer_lab("mon-lab", racine, runtime=runtime)

    for chemin, schema in ((racine / "meta.yml", "meta"),
                           (creation.racine / "lab.yaml", "lab")):
        document = yaml.safe_load(chemin.read_text(encoding="utf-8"))
        definition = json.loads(
            (RACINE / "schemas" / f"{schema}.schema.json").read_text(encoding="utf-8")
        )
        jsonschema.validate(document, definition)


# ── Les refus ───────────────────────────────────────────────────────────────

def test_un_lab_hors_catalogue_est_refuse(tmp_path: Path) -> None:
    """Sans meta.yml, ce n'est pas un catalogue : le lab n'y serait jamais vu."""
    with pytest.raises(scaffold.ScaffoldError) as exc:
        scaffold.creer_lab("mon-lab", tmp_path, runtime="shell")
    assert "meta.yml" in str(exc.value)


def test_un_runtime_inconnu_est_refuse(tmp_path: Path) -> None:
    racine = _catalogue(tmp_path)
    with pytest.raises(scaffold.ScaffoldError) as exc:
        scaffold.creer_lab("mon-lab", racine, runtime="podman")
    assert "podman" in str(exc.value)


@pytest.mark.parametrize("mauvais", ["../evade", "/absolu", "Avec Majuscule", ""])
def test_un_identifiant_ne_peut_pas_sortir_du_repertoire(
    tmp_path: Path, mauvais: str,
) -> None:
    """Un identifiant sert de nom de répertoire : il ne remonte rien."""
    with pytest.raises(scaffold.ScaffoldError):
        scaffold.creer_catalogue(mauvais, tmp_path)


def test_le_generateur_ne_cite_aucun_nom_de_domaine() -> None:
    """L'invariant du projet : le squelette est une structure, pas un contenu.

    `ansible` en est exclu, et la distinction n'est pas une facilité : le
    contrat **impose** que `setup.yaml` et `cleanup.yaml` soient des playbooks
    Ansible, joués par `ansible-runner`. C'est le format du contrat, au même
    titre que YAML, pas un domaine enseigné. Ce qui est proscrit, c'est la
    connaissance d'un domaine — un `if category == "linux"`, un scénario tout
    fait, une compétence pré-remplie.
    """
    source = Path(scaffold.__file__).read_text(encoding="utf-8").lower()
    for domaine in ("linux", "kubernetes", "terraform", "docker", "rhcsa"):
        assert domaine not in source, f"« {domaine} » est cité dans scaffold.py"

    # Et pour Ansible : il n'apparaît que comme module de playbook, jamais
    # comme sujet.
    for ligne in source.splitlines():
        if "ansible" in ligne:
            assert "ansible.builtin" in ligne, (
                f"« ansible » cité hors d'un module de playbook : {ligne.strip()}"
            )


# ── L'inscription au meta.yml : la section annoncée est celle écrite ─────────
#
# Ajouté le 2026-10-19 après un défaut mesuré sur bdd-dsoxlab-training :
# `_inscrire_dans_une_section` lisait le nom de la PREMIÈRE section, puis
# cherchait `labs: []` dans TOUT le reste du fichier. Sur un catalogue à
# plusieurs sections dont une vide, elle annonçait donc une section et écrivait
# dans une autre.
#
# Ce n'est pas un défaut de rangement, c'est un message qui mentait, et la
# position dont il parlait est l'ordre pédagogique dont `next` se sert.

_META_DEUX_SECTIONS = """schema_version: 1
repo:
  id: deux-sections
  category: exemple

sections:
  - id: premiere
    title: "Celle qui doit recevoir"
    labs:
      - deja-la
  - id: seconde
    title: "Celle qui ne doit rien recevoir"
    labs: []
"""

_META_PREMIERE_VIDE = """schema_version: 1
repo:
  id: premiere-vide
  category: exemple

sections:
  - id: premiere
    title: "Vide, et elle doit recevoir"
    labs: []
  - id: seconde
    title: "Vide aussi, et elle ne doit rien recevoir"
    labs: []
"""


def _inscrire(tmp_path: Path, contenu: str) -> tuple[str | None, dict]:
    """Joue l'inscription et rend la section annoncée, et le meta.yml relu."""
    from dsoxlab.services.scaffold import _inscrire_dans_une_section

    meta = tmp_path / "meta.yml"
    meta.write_text(contenu, encoding="utf-8")
    annoncee = _inscrire_dans_une_section(meta, "nouveau-lab")
    return annoncee, yaml.safe_load(meta.read_text(encoding="utf-8"))


def test_une_section_vide_plus_bas_ne_detourne_pas_l_inscription(
    tmp_path: Path,
) -> None:
    """Le lab va dans la première section, celle dont le nom est rendu.

    C'est le défaut exact : la seconde section portait `labs: []`, et le lab y
    partait alors que la fonction annonçait la première.
    """
    annoncee, document = _inscrire(tmp_path, _META_DEUX_SECTIONS)
    sections = {s["id"]: s["labs"] for s in document["sections"]}

    assert annoncee == "premiere"
    assert sections["premiere"] == ["deja-la", "nouveau-lab"], (
        "le lab n'a pas été ajouté à la fin de la première section"
    )
    assert sections["seconde"] in ([], None), (
        "le lab est parti dans la seconde section, que rien ne désignait"
    )


def test_la_section_annoncee_est_toujours_celle_qui_recoit(tmp_path: Path) -> None:
    """L'invariant, et il vaut pour les deux formes de première section.

    Qu'elle porte déjà des labs ou qu'elle soit vide, la section rendue est
    celle où le lab a été écrit. Un appelant qui affiche cette valeur ne peut
    donc plus mentir.
    """
    for contenu in (_META_DEUX_SECTIONS, _META_PREMIERE_VIDE):
        annoncee, document = _inscrire(tmp_path, contenu)
        recues = [
            s["id"] for s in document["sections"] if "nouveau-lab" in (s["labs"] or [])
        ]
        assert recues == [annoncee], (
            f"section annoncée {annoncee!r}, sections ayant reçu le lab {recues!r}"
        )


def test_une_premiere_section_vide_recoit_le_lab(tmp_path: Path) -> None:
    """Le cas que `new catalog` produit : toutes les listes sont vides."""
    annoncee, document = _inscrire(tmp_path, _META_PREMIERE_VIDE)
    sections = {s["id"]: s["labs"] for s in document["sections"]}

    assert annoncee == "premiere"
    assert sections["premiere"] == ["nouveau-lab"]
    assert sections["seconde"] in ([], None)
