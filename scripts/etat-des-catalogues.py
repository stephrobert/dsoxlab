#!/usr/bin/env python3
"""L'état réel des catalogues de labs, découverts sur le disque.

Pourquoi ce script existe
-------------------------

Le 2026-10-16, une campagne de traduction a été menée sur « les six
catalogues » : c'est le nombre que le tableau de `CLAUDE.md` annonçait. Le
disque en portait quinze, dont six avec des labs jamais examinés, soit 901
messages restés en français. Aucun contrôle ne l'a dit, et pour une raison
qui vaut d'être écrite : tous partaient de la liste ÉCRITE.

Ce script part du disque. Il ne prend aucun argument de catalogue, et c'est
délibéré : un argument avec une valeur par défaut est exactement le mécanisme
qui a fait oublier neuf dépôts. On ne peut pas oublier de nommer ce qu'on ne
nomme pas.

Ce qu'il mesure, et pourquoi
----------------------------

Pour chaque catalogue : ses labs, ses fichiers de tests, et l'état des
messages que l'apprenant lit quand un test échoue. Cette dernière colonne est
celle qu'aucun outil ne donnait : `dsoxlab instructor audit` la donne pour UN
catalogue, celui du répertoire courant, ce qui laisse à l'humain le soin de
penser à tous les autres.

Usage :
    python3 scripts/etat-des-catalogues.py            # le tableau
    python3 scripts/etat-des-catalogues.py --strict    # sort en 1 s'il reste
"""

from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass
from pathlib import Path

RACINE_DU_TOOL = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RACINE_DU_TOOL / "src"))

from dsoxlab.discovery.scanner import discover_labs  # noqa: E402
from dsoxlab.services.audit_pedagogique import analyser_assertions  # noqa: E402

#: Où les catalogues sont clonés sur cette machine. Un seul endroit, et le
#: motif est volontairement large : `*training` attrape aussi bien
#: `ansible-training` que `iam-dsoxlab-training`, et un nom futur qui ne
#: suivrait aucune de ces deux conventions se verra à la ligne « labs: 0 ».
ATELIER = Path.home() / "Projets"
MOTIF = "*training"


@dataclass(frozen=True)
class Etat:
    """Ce qu'on peut dire d'un catalogue sans rien supposer."""

    nom: str
    labs: int
    fichiers: int
    total: int
    bilingues: int
    indirects: int
    monolingues: int
    muets: int
    illisibles: int
    helper: bool
    #: Les appels au helper qui lèveraient au lieu d'afficher le message.
    #: Mesuré, parce que la forme ne prouve rien : un catalogue a affiché
    #: 93/93 bilingues alors que ses 93 messages rendaient un NameError.
    injoignables: int

    @property
    def reste(self) -> int:
        """Ce qu'il reste à faire : ni les indirects, ni les bilingues."""
        return self.monolingues + self.muets

    @property
    def verdict(self) -> str:
        if self.illisibles:
            return f"{self.illisibles} fichier(s) illisible(s)"
        if not self.total:
            return "aucune assertion"
        if self.injoignables:
            return f"{self.injoignables} message(s) qui lèvent"
        if self.reste:
            return f"reste {self.reste}"
        return "complet"


def mesurer(racine: Path) -> Etat:
    tests = sorted(racine.glob("labs/**/challenge/tests/*.py"))
    total = bilingues = indirects = monolingues = muets = illisibles = 0
    injoignables = 0
    for fichier in tests:
        mesure = analyser_assertions(
            fichier.read_text(encoding="utf-8", errors="replace")
        )
        if mesure.illisible:
            illisibles += 1
            continue
        total += mesure.total
        bilingues += mesure.bilingues
        indirects += mesure.indirects
        monolingues += mesure.monolingues
        muets += mesure.sans_message
        injoignables += mesure.helper_injoignable
    conftest = racine / "conftest.py"
    return Etat(
        nom=racine.name,
        labs=len(discover_labs(racine)),
        fichiers=len(tests),
        total=total,
        bilingues=bilingues,
        indirects=indirects,
        monolingues=monolingues,
        muets=muets,
        illisibles=illisibles,
        injoignables=injoignables,
        # Le helper `message(en=…, fr=…)` vit dans le conftest du catalogue,
        # pas dans dsoxlab : un lab doit rester jouable par un simple pytest.
        helper=conftest.is_file()
        and "def message(en" in conftest.read_text(encoding="utf-8", errors="replace"),
    )


def catalogues() -> list[Path]:
    """Tous les catalogues du disque, sans en nommer aucun."""
    return [
        chemin
        for chemin in sorted(ATELIER.glob(MOTIF))
        if chemin.is_dir() and (chemin / "meta.yml").is_file()
    ]


def main() -> int:
    analyse = argparse.ArgumentParser(description=__doc__)
    analyse.add_argument(
        "--strict",
        action="store_true",
        help=(
            "sort en 1 s'il reste un message à traduire, une assertion muette, "
            "ou un message bilingue qui lèverait au lieu de s'afficher"
        ),
    )
    options = analyse.parse_args()

    etats = [mesurer(chemin) for chemin in catalogues()]
    if not etats:
        print(f"Aucun catalogue sous {ATELIER}/{MOTIF}.")
        return 1

    largeur = max(len(e.nom) for e in etats)
    print(
        f"{'catalogue':<{largeur}}  labs  tests  bilingues  indir.  reste  "
        "lèvent  helper"
    )
    print("─" * (largeur + 54))
    for etat in sorted(etats, key=lambda e: (-e.injoignables, -e.reste, e.nom)):
        helper = "oui" if etat.helper else "NON"
        print(
            f"{etat.nom:<{largeur}}  {etat.labs:>4}  {etat.fichiers:>5}  "
            f"{etat.bilingues:>4}/{etat.total:<4}  {etat.indirects:>6}  "
            f"{etat.reste:>5}  {etat.injoignables:>6}  {helper:>6}"
        )

    labs = sum(e.labs for e in etats)
    total = sum(e.total for e in etats)
    bilingues = sum(e.bilingues for e in etats)
    reste = sum(e.reste for e in etats)
    injoignables = sum(e.injoignables for e in etats)
    part = f"{100 * bilingues // total} %" if total else "aucune"
    print("─" * (largeur + 54))
    print(
        f"{len(etats)} catalogues, {labs} labs, {total} assertions, "
        f"{bilingues} bilingues ({part}), {reste} à reprendre, "
        f"{injoignables} qui lèvent"
    )

    sans_helper = [e.nom for e in etats if e.total and not e.helper]
    if sans_helper:
        print(
            f"\nSans le helper `message(en=…, fr=…)` dans leur conftest : "
            f"{', '.join(sans_helper)}"
        )
    illisibles = [e.nom for e in etats if e.illisibles]
    if illisibles:
        print(f"Fichiers de tests illisibles : {', '.join(illisibles)}")

    return 1 if options.strict and (reste or injoignables) else 0


if __name__ == "__main__":
    raise SystemExit(main())
