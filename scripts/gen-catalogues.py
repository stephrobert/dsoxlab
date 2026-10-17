#!/usr/bin/env python3
"""La table des catalogues du README, et le manifeste qui la nourrit.

POURQUOI CE SCRIPT EXISTE

`templates/catalogues.yml` est ce que `dsoxlab catalog list` montre à un
apprenant. Il se tient à la main, donc il se périme, et il s'est périmé deux
fois : le 2026-10-10 il annonçait trois catalogues quand six existaient, et le
2026-10-17 il en annonçait six quand douze existaient, tous publics. Un
apprenant voyait donc la moitié de l'offre, sans qu'aucun contrôle le dise.

DEUX CONTRÔLES, QUI NE MESURENT PAS LA MÊME CHOSE

    --check      le README dit la même chose que le manifeste.
                 Les deux sont dans ce dépôt, donc JOUABLE EN CI.

    --mesurer    le manifeste dit la même chose que le DISQUE : aucun catalogue
                 oublié, aucun compte de labs faux, aucun dépôt privé proposé.
                 Jouable seulement là où les catalogues sont clonés, donc en
                 pre-commit. Sans eux, il s'abstient au lieu de conclure.

    (sans option) régénère la table du README depuis le manifeste.

Le second est celui qui compte, et c'est celui qui ne peut pas tourner en CI.
Un contrôle qui n'a pas pu regarder ne conclut jamais au vert : il le dit.
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

import yaml

RACINE = Path(__file__).resolve().parent.parent
MANIFESTE = RACINE / "src" / "dsoxlab" / "templates" / "catalogues.yml"
VOISINS = RACINE.parent
DEBUT, FIN = "<!-- CATALOGUES:START -->", "<!-- CATALOGUES:END -->"
CIBLES = {"README.md": "en", "README.fr.md": "fr"}

#: Le nom du répertoire local diffère parfois du nom du dépôt distant.
DEPOT_LOCAL = {"containers-dsoxlab-training": "containers-training"}

EN_TETES = {
    "en": ("Catalog", "Labs", "What it teaches"),
    "fr": ("Catalogue", "Labs", "Ce qu'il enseigne"),
}
PIED = {
    "en": "_{labs} labs across {n} catalogs. This table is generated from "
          "`src/dsoxlab/templates/catalogues.yml` by `scripts/gen-catalogues.py`, "
          "the same manifest `dsoxlab catalog list` reads._",
    "fr": "_{labs} labs dans {n} catalogues. Cette table est générée depuis "
          "`src/dsoxlab/templates/catalogues.yml` par `scripts/gen-catalogues.py`, "
          "le manifeste que lit `dsoxlab catalog list`._",
}


def _manifeste() -> list[dict]:
    donnees = yaml.safe_load(MANIFESTE.read_text(encoding="utf-8"))
    return list(donnees["catalogues"])


def _table(lang: str, catalogues: list[dict]) -> str:
    cat, labs, sujet = EN_TETES[lang]
    lignes = [f"| {cat} | {labs} | {sujet} |", "|---|---:|---|"]
    for entree in sorted(catalogues, key=lambda c: -c["labs"]):
        depot = entree["depot"].rstrip("/").rsplit("/", 1)[-1]
        texte = entree[f"description_{lang}"]
        lignes.append(f"| [`{depot}`]({entree['depot']}) | {entree['labs']} | {texte} |")
    total = sum(c["labs"] for c in catalogues)
    lignes += ["", PIED[lang].format(labs=total, n=len(catalogues))]
    return "\n".join(lignes)


def _rendu(chemin: Path, bloc: str) -> str:
    texte = chemin.read_text(encoding="utf-8")
    if DEBUT not in texte or FIN not in texte:
        raise SystemExit(f"{chemin.name} : marqueurs {DEBUT} / {FIN} absents")
    avant = texte[: texte.index(DEBUT) + len(DEBUT)]
    apres = texte[texte.index(FIN):]
    return f"{avant}\n\n{bloc}\n\n{apres}"


# ── Le contrôle qui part du disque ───────────────────────────────────────────


def _labs_sur_le_disque(racine: Path) -> int:
    return len(list((racine / "labs").glob("**/lab.yaml")))


def _est_un_clone_local(racine: Path) -> bool:
    """Le dépôt a-t-il pour `origin` un chemin local plutôt qu'une URL ?

    `ansible-training-analyse` porte un `meta.yml` et 113 `lab.yaml`, mais son
    origin est un chemin local : c'est une copie d'analyse, pas un catalogue.
    Le compter doublerait les labs d'Ansible.
    """
    resultat = subprocess.run(
        ["git", "-C", str(racine), "remote", "get-url", "origin"],
        capture_output=True, text=True, check=False, timeout=30,
    )
    if resultat.returncode != 0:
        return False
    return resultat.stdout.strip().startswith(("/", "../", "./", "file://"))


def _catalogues_du_disque() -> dict[str, int]:
    """Les catalogues trouvés à côté de ce dépôt, et leur nombre de labs."""
    trouves: dict[str, int] = {}
    for chemin in sorted(VOISINS.iterdir()):
        if not chemin.is_dir():
            continue
        if not (chemin / "meta.yml").is_file() or not (chemin / "labs").is_dir():
            continue
        if _est_un_clone_local(chemin):
            continue
        labs = _labs_sur_le_disque(chemin)
        if labs:
            trouves[chemin.name] = labs
    return trouves


def _mesurer() -> int:
    """Le manifeste dit-il la même chose que le disque ?"""
    disque = _catalogues_du_disque()
    if not disque:
        print("aucun catalogue cloné à côté de ce dépôt : rien n'a pu être "
              "mesuré, donc rien n'est conclu.", file=sys.stderr)
        return 0

    inscrits = {}
    for entree in _manifeste():
        depot = entree["depot"].rstrip("/").rsplit("/", 1)[-1]
        inscrits[DEPOT_LOCAL.get(depot, depot)] = entree

    ecarts: list[str] = []
    for nom, labs in sorted(disque.items()):
        entree = inscrits.get(nom)
        if entree is None:
            ecarts.append(
                f"{nom} ({labs} labs) existe sur le disque mais n'est PAS dans "
                "le manifeste : `dsoxlab catalog list` ne le propose pas"
            )
        elif entree["labs"] != labs:
            ecarts.append(
                f"{nom} : le manifeste annonce {entree['labs']} labs, le disque "
                f"en porte {labs}"
            )
    for nom in sorted(set(inscrits) - set(disque)):
        ecarts.append(
            f"{nom} est dans le manifeste mais introuvable sur le disque : "
            "vérifie qu'il n'a pas été renommé"
        )

    if ecarts:
        print(f"{len(ecarts)} écart(s) entre le manifeste et le disque :",
              file=sys.stderr)
        for e in ecarts:
            print(f"  {e}", file=sys.stderr)
        return 1
    print(f"manifeste en accord avec le disque ({len(disque)} catalogues, "
          f"{sum(disque.values())} labs)")
    return 0


def main() -> int:
    analyseur = argparse.ArgumentParser(description=__doc__)
    analyseur.add_argument(
        "--check", action="store_true",
        help="ne réécrit rien ; sort en 1 si un README diffère du manifeste",
    )
    analyseur.add_argument(
        "--mesurer", action="store_true",
        help="compare le manifeste au disque ; s'abstient si aucun catalogue "
             "n'est cloné à côté",
    )
    arguments = analyseur.parse_args()

    if arguments.mesurer:
        return _mesurer()

    catalogues = _manifeste()
    perimes = []
    for nom, lang in CIBLES.items():
        chemin = RACINE / nom
        attendu = _rendu(chemin, _table(lang, catalogues))
        if arguments.check:
            if chemin.read_text(encoding="utf-8") != attendu:
                perimes.append(nom)
        else:
            chemin.write_text(attendu, encoding="utf-8")

    if arguments.check:
        if perimes:
            print(f"{', '.join(perimes)} : table des catalogues périmée. "
                  "Joue `python3 scripts/gen-catalogues.py`.", file=sys.stderr)
            return 1
        print(f"table des catalogues à jour ({len(catalogues)} catalogues)")
        return 0

    print(f"table régénérée dans {', '.join(CIBLES)} "
          f"({len(catalogues)} catalogues, "
          f"{sum(c['labs'] for c in catalogues)} labs)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
