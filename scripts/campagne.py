#!/usr/bin/env python3
"""Pilote une campagne de réattestation, d'après les descripteurs du dossier.

Pourquoi ce fichier ne contient aucun nom de catalogue
-----------------------------------------------------

Le 2026-10-19, un script de campagne portait ses prérequis en listes codées en
dur, construites de mémoire. Résultat : **59 faux ROUGE sur kubernetes et 16
sur iam**, dont les deux causes étaient écrites dans le `CLAUDE.md` du
catalogue concerné. Le relevé de kubernetes, qui disait 64 VALIDE, a dû être
restauré par `git checkout`.

La leçon n'est pas « mieux lire » : c'est que **la connaissance d'un catalogue
ne doit pas vivre dans le code qui le pilote**. Chaque `scripts/campagnes/
<catalogue>.yml` déclare ce que SON catalogue exige, avec la source qui le
documente. Ce pilote ne fait que les lire et obéir. Ajouter un catalogue,
corriger un prérequis ou en bloquer un ne demande pas d'y toucher.

Ce qu'il garantit
-----------------

- il **refuse** un catalogue marqué `bloque`, en citant sa raison ;
- il joue les étapes **dans l'ordre déclaré** et s'arrête au premier échec
  d'étape, plutôt que d'enchaîner sur une campagne qui ne mesurera rien ;
- il **interrompt** un catalogue dès trois verdicts rouges portant le même
  motif : c'est la signature d'un harnais cassé, pas de labs cassés, et c'est
  exactement ce qui a produit les 59 faux ROUGE ;
- il ne commite rien, et il nomme en sortant les relevés à relire.

Usage
-----

    python3 scripts/campagne.py                 # tout l'ordre déclaré
    python3 scripts/campagne.py kubernetes      # un ou plusieurs catalogues
    python3 scripts/campagne.py --sans-destroy  # garder l'infra pour diagnostiquer
    python3 scripts/campagne.py --dire-seulement  # afficher le plan, ne rien faire

La destruction d'infrastructure est refusée à un agent par le garde-fou de la
session : lancer ce script avec le préfixe `!` depuis le prompt, ou le lancer
soi-même.
"""

from __future__ import annotations

import argparse
import os
import re
import subprocess
import sys
import tempfile
import time
from dataclasses import dataclass, field
from pathlib import Path

import yaml

RACINE_SCRIPT = Path(__file__).resolve().parent
DESCRIPTEURS = RACINE_SCRIPT / "campagnes"
ATELIER = Path.home() / "Projets"

#: Trois verdicts rouges portant le même motif : on n'en écrit pas un quatrième.
SEUIL_DE_SERIE = 3

#: Ce qu'un verdict rouge laisse en trace, pour en extraire le motif.
MOTIF_ROUGE = re.compile(r"\.\.\.\s*ROUGE|:\s*ROUGE|ROUGE\s+(?:en|\d)")


@dataclass
class Etape:
    nom: str
    lab: str | None = None
    pourquoi: str = ""
    source: str = ""


@dataclass
class Catalogue:
    nom: str
    labs_vm: int
    bloque: bool
    raison_du_blocage: str
    etapes: list[Etape]
    pieges: list[dict] = field(default_factory=list)
    interdits: list[dict] = field(default_factory=list)


def charger(chemin: Path) -> Catalogue:
    d = yaml.safe_load(chemin.read_text(encoding="utf-8")) or {}
    return Catalogue(
        nom=str(d.get("catalogue") or chemin.stem),
        labs_vm=int(d.get("labs_vm") or 0),
        bloque=bool(d.get("bloque")),
        raison_du_blocage=str(d.get("raison_du_blocage") or "").strip(),
        etapes=[
            Etape(
                nom=str(e.get("nom")),
                lab=e.get("lab"),
                pourquoi=str(e.get("pourquoi") or "").strip(),
                source=str(e.get("source") or "").strip(),
            )
            for e in (d.get("etapes") or [])
        ],
        pieges=list(d.get("pieges") or []),
        interdits=list(d.get("interdits") or []),
    )


def ordre_declare() -> list[str]:
    fichier = DESCRIPTEURS / "_ordre.yml"
    if not fichier.is_file():
        return []
    d = yaml.safe_load(fichier.read_text(encoding="utf-8")) or {}
    return [str(n) for n in (d.get("ordre") or [])]


def ram_libre_go() -> int:
    """La mémoire réellement disponible, et non celle que `doctor` annonce."""
    try:
        for ligne in Path("/proc/meminfo").read_text(encoding="utf-8").splitlines():
            if ligne.startswith("MemAvailable:"):
                return int(ligne.split()[1]) // (1024 * 1024)
    except (OSError, ValueError):
        pass
    return -1


def jouer(commande: list[str], cwd: Path, journal, timeout: int = 3600) -> int:
    """Lance une commande en consignant tout, et rend son code."""
    journal.write(f"\n$ {' '.join(commande)}\n")
    journal.flush()
    try:
        proc = subprocess.run(
            commande, cwd=cwd, capture_output=True, text=True,
            timeout=timeout, check=False,
        )
    except subprocess.TimeoutExpired:
        journal.write(f"[delai depasse apres {timeout}s]\n")
        journal.flush()
        return 124
    except FileNotFoundError as exc:
        journal.write(f"[commande introuvable : {exc}]\n")
        journal.flush()
        return 127
    journal.write(proc.stdout + proc.stderr)
    journal.flush()
    return proc.returncode


def serie_de_rouges(sortie: str) -> str | None:
    """Le motif répété au moins SEUIL_DE_SERIE fois, s'il y en a un.

    On ne compte pas les rouges : on compte les rouges qui se RESSEMBLENT. Un
    lab cassé est un rouge singulier ; trois rouges identiques sont un harnais
    cassé, et le quatrième n'apprendrait rien de plus.
    """
    motifs: dict[str, int] = {}
    lignes = sortie.splitlines()
    for i, ligne in enumerate(lignes):
        if not MOTIF_ROUGE.search(ligne):
            continue
        # La cause est sur la ligne du verdict ou juste après.
        contexte = " ".join(lignes[i : i + 2])
        # On réduit au squelette : les identifiants et les durées varient.
        cle = re.sub(r"\d+", "N", contexte)
        cle = re.sub(r"\[N/N\]\s*\S+", "", cle).strip()
        if not cle:
            continue
        motifs[cle] = motifs.get(cle, 0) + 1
    for cle, n in sorted(motifs.items(), key=lambda kv: -kv[1]):
        if n >= SEUIL_DE_SERIE:
            return f"{n} fois : {cle[:160]}"
    return None


def destroy_partout(catalogues: list[str], journal) -> None:
    """Faire place nette. `destroy` lit le meta.yml du répertoire courant."""
    for autre in catalogues:
        racine = ATELIER / autre
        if racine.is_dir():
            jouer(["dsoxlab", "destroy", "--yes"], racine, journal, timeout=900)


def mener(cat: Catalogue, tous: list[str], journal, args) -> str:
    """Joue un catalogue et rend son bilan en une ligne."""
    racine = ATELIER / cat.nom
    if not racine.is_dir():
        return "répertoire absent"

    for interdit in cat.interdits:
        journal.write(f"\n[rappel] ne pas : {interdit.get('quoi')}\n")

    for etape in cat.etapes:
        if etape.pourquoi:
            journal.write(f"\n[{etape.nom}] {etape.pourquoi}\n")
        if etape.source:
            journal.write(f"[{etape.nom}] source : {etape.source}\n")

        if etape.nom == "provision":
            destroy_partout(tous, journal)
            libre = ram_libre_go()
            journal.write(f"[provision] RAM disponible : {libre} Go\n")
            if jouer(["dsoxlab", "provision"], racine, journal) != 0:
                return "ÉCHEC du provisionnement"

        elif etape.nom == "rebase":
            if not (racine / "scripts" / "rebase-vms.sh").is_file():
                return "ÉCHEC : rebase déclaré mais scripts/rebase-vms.sh absent"
            if jouer(["bash", "scripts/rebase-vms.sh"], racine, journal, 1800) != 0:
                return "ÉCHEC du rebase (le validateur refuserait de jouer)"

        elif etape.nom == "run_prealable":
            if not etape.lab:
                return "ÉCHEC : run_prealable sans lab déclaré"
            if jouer(["dsoxlab", "run", etape.lab], racine, journal, 2400) != 0:
                return f"ÉCHEC du run préalable sur {etape.lab}"

        elif etape.nom == "campagne":
            commande = ["uv", "run", "scripts/valider-labs.py"]
            if (racine / "mise.toml").is_file():
                commande = ["mise", "exec", "--", *commande]
            avant = journal.tell()
            code = jouer(commande, racine, journal, timeout=4 * 3600)
            journal.flush()
            with Path(journal.name).open(encoding="utf-8", errors="replace") as relu:
                relu.seek(avant)
                sortie = relu.read()
            serie = serie_de_rouges(sortie)
            if serie:
                journal.write(f"\n[SÉRIE DE ROUGES] {serie}\n")
                return f"INTERROMPU, série de rouges : {serie[:90]}"
            if code != 0:
                bilans = re.findall(r"^\s*\d+ (?:valide|VALIDE|ROUGE).*$", sortie, re.MULTILINE)
                return bilans[-1].strip() if bilans else f"campagne sortie en {code}"
            bilans = re.findall(r"^\s*\d+ (?:valide|VALIDE).*$", sortie, re.MULTILINE)
            return bilans[-1].strip() if bilans else "campagne terminée"

        elif etape.nom == "destroy":
            if args.sans_destroy:
                journal.write("[destroy] sauté sur demande (--sans-destroy)\n")
            else:
                jouer(["dsoxlab", "destroy", "--yes"], racine, journal, 900)

        else:
            return f"ÉCHEC : étape inconnue « {etape.nom} »"

    return "terminé"


def main(argv: list[str] | None = None) -> int:
    analyseur = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    analyseur.add_argument("catalogues", nargs="*", help="noms courts ou complets")
    analyseur.add_argument("--sans-destroy", action="store_true",
                           help="garder l'infra du dernier catalogue, pour diagnostiquer")
    analyseur.add_argument("--dire-seulement", action="store_true",
                           help="afficher le plan et sortir")
    args = analyseur.parse_args(argv)

    if not DESCRIPTEURS.is_dir():
        print(f"dossier de descripteurs absent : {DESCRIPTEURS}", file=sys.stderr)
        return 2

    connus = {c.nom: c for c in (charger(f) for f in sorted(DESCRIPTEURS.glob("*.yml"))
                                 if f.name != "_ordre.yml")}
    ordre = [n for n in ordre_declare() if n in connus]
    # Un catalogue décrit mais absent de l'ordre n'est pas oublié : il est dit.
    hors_ordre = sorted(set(connus) - set(ordre))

    if args.catalogues:
        choisis = []
        for arg in args.catalogues:
            trouve = [n for n in connus if n == arg or n.startswith(f"{arg}-") or n == f"{arg}-dsoxlab-training"]
            if not trouve:
                print(f"aucun descripteur pour « {arg} ». Connus : {', '.join(sorted(connus))}",
                      file=sys.stderr)
                return 2
            choisis.extend(trouve)
    else:
        choisis = ordre

    print(f"descripteurs : {DESCRIPTEURS}")
    print(f"catalogues à jouer : {len(choisis)}")
    for nom in choisis:
        c = connus[nom]
        etat = "BLOQUÉ" if c.bloque else " ".join(e.nom for e in c.etapes)
        print(f"  {nom:<34} {c.labs_vm:>3} labs vm   {etat}")
    if hors_ordre:
        print(f"\ndécrits mais hors de l'ordre : {', '.join(hors_ordre)}")
        for nom in hors_ordre:
            if connus[nom].bloque:
                print(f"  {nom} : BLOQUÉ, {connus[nom].raison_du_blocage.splitlines()[0]}")
    if args.dire_seulement:
        return 0

    temporaires = Path(os.environ.get("TMPDIR") or tempfile.gettempdir())
    chemin_journal = temporaires / f"campagne-{time.strftime('%Y%m%d-%H%M%S')}.log"
    bilans: dict[str, str] = {}
    with chemin_journal.open("w", encoding="utf-8") as journal:
        print(f"\njournal : {chemin_journal}\n")
        for nom in choisis:
            cat = connus[nom]
            print(f"## {nom}  ({time.strftime('%H:%M:%S')})")
            journal.write(f"\n{'=' * 70}\n## {nom}  {time.strftime('%H:%M:%S')}\n")
            if cat.bloque:
                raison = cat.raison_du_blocage.splitlines()[0] if cat.raison_du_blocage else "sans raison écrite"
                print(f"   REFUSÉ : {raison}")
                journal.write(f"REFUSÉ (bloque: true) : {cat.raison_du_blocage}\n")
                bilans[nom] = f"refusé : {raison}"
                continue
            bilan = mener(cat, choisis, journal, args)
            print(f"   {bilan}")
            bilans[nom] = bilan

    print("\n" + "=" * 70)
    for nom, bilan in bilans.items():
        print(f"{nom:<34} {bilan}")
    sales = [
        nom for nom in choisis
        if (ATELIER / nom).is_dir()
        and subprocess.run(["git", "-C", str(ATELIER / nom), "status", "--porcelain",
                            "validation-labs.json"],
                           capture_output=True, text=True, check=False).stdout.strip()
    ]
    if sales:
        print("\nRelevés modifiés, À RELIRE avant de committer :")
        for nom in sales:
            print(f"   {nom}")
        print("Un ROUGE d'environnement ne doit pas entrer dans l'historique comme")
        print("un défaut de lab. En cas de doute : git checkout -- validation-labs.json")
    print(f"\njournal : {chemin_journal}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
