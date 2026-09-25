"""`validate-structure` doit voir les labs que la découverte a perdus (#198).

Le validator itérait sur ``discover_labs()``, donc sur les **survivants**. Un
``lab.yaml`` qui lève au parsing n'y figurait pas : il traversait la validation
sans un mot, et l'auteur lisait « ✔ tous les labs sont valides » sur un catalogue
amputé de ce lab. L'autre moitié du même angle mort : un lab déclaré dans
``meta.yml: sections[].labs[]`` dont aucun fichier n'existe — personne ne le
chargeait, et personne ne disait qu'on l'attendait.

C'est le motif que le lot 0.1.84 a corrigé partout ailleurs : **un contrôle qui
n'a pas pu regarder ne conclut pas au vert.** La documentation auteur prescrivait
en conséquence « `list-labs` d'abord, `validate-structure` ensuite », une règle
qu'un utilisateur ne devrait pas avoir à connaître.

Un cas par cause, comme l'issue le demande : YAML cassé, champ requis manquant,
``schema_version`` trop récent, lab déclaré et absent. Le troisième est là pour
prouver qu'il **ne** se dit **pas** deux fois : il a déjà son contrôle, qui sait
que la réparation est dans la version de l'outil.
"""

from __future__ import annotations

from pathlib import Path

from dsoxlab.validators.contract import (
    validate_labs_chargeables,
    validate_labs_declares,
    validate_schema_versions,
)

_LAB_VALIDE = """\
id: {id}
title: {id}
level: l1
skills: [demo]
distros: [any]
doc_url: https://example.test/docs/{id}/
runtime:
  type: shell
  workdir: challenge/work
"""


def _meta(racine: Path, *, declares: list[str] | None = None) -> None:
    lignes = ["repo:", "  id: catalogue-test", "  category: demo"]
    if declares is not None:
        lignes += ["sections:", "  - id: bloc", "    title: Bloc", "    labs:"]
        lignes += [f"      - {chemin}" for chemin in declares]
    (racine / "meta.yml").write_text("\n".join(lignes) + "\n", encoding="utf-8")


def _lab(racine: Path, lab_id: str, contenu: str | None = None) -> Path:
    dossier = racine / "labs" / "bloc" / lab_id
    dossier.mkdir(parents=True)
    fichier = dossier / "lab.yaml"
    fichier.write_text(
        _LAB_VALIDE.format(id=lab_id) if contenu is None else contenu,
        encoding="utf-8",
    )
    return fichier


# ── un lab.yaml présent que le moteur ne sait pas charger ────────────────────

def test_un_yaml_casse_est_signale(tmp_path: Path) -> None:
    """Le cas le plus courant, et le plus silencieux : une faute de syntaxe."""
    _meta(tmp_path)
    _lab(tmp_path, "sain")
    fautif = _lab(tmp_path, "casse", contenu="id: casse\n  title: [mal indenté\n")

    rapport = validate_labs_chargeables(tmp_path)

    assert not rapport.ok
    assert [issue.path for issue in rapport.issues] == [fautif]
    # La position compte plus que la prose : PyYAML rend six lignes dont deux
    # chemins absolus, et ce que l'auteur cherche, c'est où regarder.
    issue = rapport.issues[0]
    assert issue.key == "lab_yaml_illisible_position"
    assert issue.params["ligne"] == 2
    assert issue.params["colonne"] == 8
    # Une seule ligne de cause : le message entier reste au journal.
    assert "\n" not in issue.params["raison"]


def test_un_champ_requis_manquant_est_signale(tmp_path: Path) -> None:
    """Sans `level`, le parsing lève, et le lab disparaissait de tout."""
    _meta(tmp_path)
    fautif = _lab(
        tmp_path, "sans-level",
        contenu="id: sans-level\ntitle: Sans level\nskills: [demo]\n",
    )

    rapport = validate_labs_chargeables(tmp_path)

    assert not rapport.ok
    assert rapport.issues[0].path == fautif


def test_un_catalogue_sain_ne_dit_rien(tmp_path: Path) -> None:
    """Le contrôle ne doit pas bavarder : un catalogue lisible est silencieux."""
    _meta(tmp_path)
    _lab(tmp_path, "un")
    _lab(tmp_path, "deux")

    assert validate_labs_chargeables(tmp_path).ok


def test_une_version_trop_recente_ne_se_dit_qu_une_fois(tmp_path: Path) -> None:
    """Deux contrôles, deux causes : ne pas les confondre.

    Un `schema_version` que cet outil ne lit pas se répare en mettant l'outil à
    jour, pas en touchant au catalogue. `validate_schema_versions` le dit déjà,
    et le dire une seconde fois sous « le moteur ne sait pas le charger » ferait
    chercher une faute dans le fichier.
    """
    _meta(tmp_path)
    _lab(
        tmp_path, "futur",
        contenu="schema_version: 99\n" + _LAB_VALIDE.format(id="futur"),
    )

    versions = validate_schema_versions(tmp_path)
    chargeables = validate_labs_chargeables(tmp_path)

    assert [issue.key for issue in versions.issues] == ["schema_version_too_new"]
    assert chargeables.ok


# ── un lab déclaré au meta.yml dont le fichier n'existe pas ──────────────────

def test_un_lab_declare_sans_fichier_est_signale(tmp_path: Path) -> None:
    """L'autre moitié de l'angle mort : déclaré, attendu, jamais chargé."""
    _meta(tmp_path, declares=["bloc/present", "bloc/fantome"])
    _lab(tmp_path, "present")

    rapport = validate_labs_declares(tmp_path)

    assert not rapport.ok
    assert len(rapport.issues) == 1
    issue = rapport.issues[0]
    assert issue.params == {"chemin": "bloc/fantome", "section": "bloc"}
    # Le meta.yml porte la déclaration : c'est le fichier qu'on ouvre pour
    # corriger, et pointer un chemin qui n'existe pas n'aiderait personne.
    assert issue.path.name == "meta.yml"


def test_des_labs_tous_presents_ne_disent_rien(tmp_path: Path) -> None:
    _meta(tmp_path, declares=["bloc/un", "bloc/deux"])
    _lab(tmp_path, "un")
    _lab(tmp_path, "deux")

    assert validate_labs_declares(tmp_path).ok


def test_un_catalogue_sans_sections_ne_declare_rien(tmp_path: Path) -> None:
    """Sans `sections`, rien n'est déclaré, donc rien ne peut manquer.

    C'est le cas de `terraform-dsoxlab-training` pour l'infra, et celui de tout
    catalogue naissant : le contrôle ne doit pas inventer une attente.
    """
    _meta(tmp_path)
    _lab(tmp_path, "un")

    assert validate_labs_declares(tmp_path).ok


def test_sans_meta_yml_le_controle_se_tait(tmp_path: Path) -> None:
    """Mode legacy : aucune déclaration n'existe, donc aucune n'est trahie."""
    _lab(tmp_path, "un")

    assert validate_labs_declares(tmp_path).ok
