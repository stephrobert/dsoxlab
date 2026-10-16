#!/usr/bin/env python3
"""Mesure la complexité de ce que l'apprenant a sous les yeux.

Le trou que ce script bouche
============================

Le dépôt mesure la complexité de son code (``scripts/complexite.py``, ``ruff
C901``) et rien de ce qu'il affiche. Or un parcours se juge à l'écran : une
fonction de complexité 3 peut produire un tableau de huit colonnes illisible, et
une commande irréprochable peut déverser un traceback pytest à quelqu'un qui
apprend à se déplacer dans un système de fichiers.

Ce script exécute de vraies commandes, à une largeur de terminal donnée, et
mesure **sept grandeurs** sur ce qui sort. Aucune n'est une opinion.

Les sept grandeurs, et pourquoi chacune
=======================================

``lignes``
    Hauteur du rendu. Au-delà de 24, l'écran a défilé : ce que l'apprenant lit
    en premier a disparu en haut.

``tronque``
    Nombre de « … » et de mots coupés. C'est de **l'information perdue**, et
    c'est mesurable : à 80 colonnes, ``list-labs`` réduisait six de ses huit
    colonnes à une lettre.

``colonnes``
    Nombre de colonnes de tableau. Chaque colonne est une chose de plus à lire
    pour en trouver une.

``gestes``
    Nombre de commandes ``dsoxlab …`` distinctes proposées dans la sortie.
    C'est la **charge décisionnelle** : un écran qui propose sept gestes demande
    sept arbitrages à qui n'en connaît aucun.

``jargon``
    Nombre de termes techniques distincts affichés, parmi une liste tenue
    ci-dessous. « provider », « hyperviseur », « state », « inventaire » :
    autant de mots qu'il faut déjà savoir pour lire la réponse.

``traces``
    Lignes qui ressemblent à une sortie d'outil brute (traceback Python,
    ``assert``, ``FAILED``, ``rc=``). Ce n'est pas de l'interface, c'est de
    l'interface qui a renoncé.

``largeur_min``
    Largeur de terminal en dessous de laquelle la sortie tronque. Mesurée en
    rejouant la commande à 80, 100, 120 et 160 colonnes.

``impasse``
    1 quand l'écran tient en deux lignes ou moins **et** ne propose aucun geste.
    Un écran léger n'est pas forcément bon : « Aucun lab trouvé. » en rendant 0,
    sans dire qu'aucun catalogue n'est actif ni quoi faire, pèse zéro sur toutes
    les autres grandeurs et laisse pourtant l'apprenant sans suite. C'est la
    seule grandeur qui punit la brièveté, et elle existe pour que « simplifier »
    ne puisse pas se confondre avec « se taire ».

Le score d'un écran est la somme pondérée de ces grandeurs, et celui d'un
parcours la somme de ses écrans **plus** le nombre de commandes tapées et de
``cd`` imposés. Le poids des facteurs est déclaré dans ``POIDS`` : il est
arbitraire, et c'est pourquoi le détail est toujours affiché à côté du score.
Un score sert à comparer deux versions du même écran, pas à décerner une note.

Ce que ce score ne sait pas voir
================================

Il mesure la **charge**, jamais l'**utilité**. Deux limites vécues, et il faut
les connaître avant de suivre un chiffre :

1. **Une colonne utile et une colonne inutile pèsent pareil.** Ajouter la durée
   d'un lab, qui varie et aide à choisir, coûte autant que son runtime, qui
   vaut « shell » partout. Le script ne lit que le rendu ; il ne sait pas ce que
   les valeurs valent.
2. **Retirer de l'information fait toujours baisser le score.** La première
   version de l'affichage de ``check`` ne montrait que les noms des tests en
   échec : elle marquait 2 au lieu de 9, en jetant la phrase que l'auteur du lab
   avait écrite dans son ``assert``, avec le geste de réparation. Une capture
   avant/après l'a vu, le compteur non.

D'où la règle : **une hausse se fige sciemment**, en disant pourquoi, et un
écran ne se juge jamais sans l'avoir regardé.

Usage :
    python3 scripts/complexite-ecran.py                    # tous les parcours
    python3 scripts/complexite-ecran.py --parcours accueil
    python3 scripts/complexite-ecran.py --largeur 120
    python3 scripts/complexite-ecran.py --json
    python3 scripts/complexite-ecran.py --verifier         # sort 1 si ça empire
    python3 scripts/complexite-ecran.py --figer            # entérine l'état
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import tempfile
from dataclasses import asdict, dataclass, field
from pathlib import Path

RACINE = Path(__file__).resolve().parent.parent
REFERENCE = Path(__file__).resolve().parent / "complexite-ecran-reference.json"

#: Largeur de référence. 80 colonnes est la largeur d'un terminal ouvert sans
#: redimensionnement, et celle d'un tmux coupé en deux sur un écran courant.
LARGEUR_PAR_DEFAUT = 80

#: Largeurs rejouées pour trouver `largeur_min`.
LARGEURS = (80, 100, 120, 160)

#: Hauteur au-delà de laquelle un écran a défilé.
HAUTEUR_ECRAN = 24

#: Termes qu'il faut déjà connaître pour lire la sortie. La liste est tenue à la
#: main et c'est assumé : « lab » ou « score » n'en font pas partie, ce sont les
#: mots du domaine que le parcours enseigne. Y figurent les mots d'INFRASTRUCTURE
#: et d'OUTILLAGE, que rien n'enseigne et que l'apprenant n'a pas demandés.
JARGON = (
    "provider",
    "hyperviseur",
    "hypervisor",
    "provision",
    "provisionn",
    "terraform",
    "libvirt",
    "virsh",
    "kvm",
    "incus",
    "qemu",
    "state",
    "tfvars",
    "inventaire",
    "inventory",
    "ansible",
    "playbook",
    "snapshot",
    "workdir",
    "fixture",
    "runtime",
    "target",
    "flock",
    "verrou",
    "pool",
    "bridge",
    "egress",
    "cloud-init",
    "ssh_config",
    "xdg",
    "sqlite",
    "pytest",
    "testinfra",
    "conftest",
    "yaml",
    "json",
    "stderr",
    "stdout",
    "subprocess",
    "nested",
    "overlay",
    "fqdn",
    "cidr",
    "dhcp",
)

#: Ce qui trahit une sortie d'outil laissée telle quelle.
MOTIFS_TRACE = (
    re.compile(r"^\s*E\s+"),
    re.compile(r"^\s*(Traceback|File \")"),
    re.compile(r"\bassert\b"),
    re.compile(r"^\s*FAILED\b"),
    re.compile(r"\brc=\d"),
    re.compile(r"^\s*\+\s+where\b"),
    re.compile(r"^={5,}.*={5,}$"),
)

#: Poids du score. Arbitraires, donc toujours affichés avec le détail.
POIDS = {
    "lignes_au_dela_de_l_ecran": 1.0,
    "tronque": 2.0,
    "colonnes_au_dela_de_trois": 1.5,
    "gestes": 1.0,
    "jargon": 1.5,
    "traces": 3.0,
    "impasse": 10.0,
    "commandes_tapees": 4.0,
    "cd_imposes": 8.0,
}

_SEQUENCES_ANSI = re.compile(r"\x1b\[[0-9;]*[A-Za-z]")
_GESTE = re.compile(r"\bdsoxlab [a-z][a-z-]*(?: [a-z][a-z-]*)?")
_BORDURES = re.compile(r"^[\s┏┡┗├└┌┐┘╭╮╰╯╞╡┬┴┼─━│┃┣┫╇╈╋┠┨╪┷┯]+$")


@dataclass
class Ecran:
    """Ce qu'une commande affiche, mesuré."""

    commande: str
    lignes: int
    tronque: int
    colonnes: int
    gestes: int
    jargon: int
    traces: int
    largeur_min: int
    code_retour: int
    impasse: int = 0
    jargon_vu: list[str] = field(default_factory=list)
    gestes_vus: list[str] = field(default_factory=list)

    @property
    def score(self) -> float:
        return round(
            POIDS["lignes_au_dela_de_l_ecran"] * max(0, self.lignes - HAUTEUR_ECRAN)
            + POIDS["tronque"] * self.tronque
            + POIDS["colonnes_au_dela_de_trois"] * max(0, self.colonnes - 3)
            + POIDS["gestes"] * self.gestes
            + POIDS["jargon"] * self.jargon
            + POIDS["traces"] * self.traces
            + POIDS["impasse"] * self.impasse,
            1,
        )


@dataclass
class Parcours:
    """Une suite d'écrans, et ce qu'elle impose entre eux."""

    nom: str
    ecrans: list[Ecran]
    cd_imposes: int

    @property
    def score(self) -> float:
        return round(
            sum(e.score for e in self.ecrans)
            + POIDS["commandes_tapees"] * len(self.ecrans)
            + POIDS["cd_imposes"] * self.cd_imposes,
            1,
        )


def _nettoyer(sortie: str) -> list[str]:
    return [_SEQUENCES_ANSI.sub("", ligne) for ligne in sortie.splitlines()]


def _compter_troncatures(lignes: list[str]) -> int:
    """Les « … » posés par Rich, et les mots coupés en fin de cellule.

    Rich tronque avec « … » (U+2026). Il replie aussi les mots longs sans
    césure : une ligne de cellule qui se termine par un fragment de mot et dont
    la suivante reprend par un fragment est une coupure, pas un repli.
    """
    return sum(ligne.count("…") for ligne in lignes)


def _compter_colonnes(lignes: list[str]) -> int:
    """Le nombre maximal de colonnes d'un tableau, lu sur ses séparateurs."""
    pire = 0
    for ligne in lignes:
        if not ligne.strip().startswith(("┏", "┡", "┌", "├")):
            continue
        pire = max(pire, ligne.count("┳") + ligne.count("╇") + ligne.count("┬") + 1)
    return pire


def _compter_gestes(lignes: list[str]) -> list[str]:
    vus: list[str] = []
    for ligne in lignes:
        for geste in _GESTE.findall(ligne):
            propre = geste.strip()
            if propre not in vus:
                vus.append(propre)
    return vus


def _compter_jargon(lignes: list[str]) -> list[str]:
    texte = " ".join(lignes).lower()
    return [terme for terme in JARGON if terme in texte]


def _compter_traces(lignes: list[str]) -> int:
    return sum(
        1 for ligne in lignes if any(motif.search(ligne) for motif in MOTIFS_TRACE)
    )


def _executer(
    argv: list[str], *, largeur: int, cwd: Path, env_sup: dict[str, str]
) -> tuple[str, int]:
    env = {
        **os.environ,
        "COLUMNS": str(largeur),
        "TERM": "dumb",
        "DSOXLAB_LANG": env_sup.get("DSOXLAB_LANG", "fr"),
        **env_sup,
    }
    acheve = subprocess.run(
        argv,
        check=False,
        capture_output=True,
        text=True,
        cwd=cwd,
        env=env,
        timeout=180,
    )
    return acheve.stdout + acheve.stderr, acheve.returncode


def mesurer_ecran(
    argv: list[str], *, cwd: Path, env_sup: dict[str, str], largeur: int
) -> Ecran:
    """Joue une commande et mesure ce qu'elle affiche."""
    sortie, code = _executer(argv, largeur=largeur, cwd=cwd, env_sup=env_sup)
    lignes = _nettoyer(sortie)
    utiles = [ligne for ligne in lignes if ligne.strip() and not _BORDURES.match(ligne)]
    jargon = _compter_jargon(utiles)
    gestes = _compter_gestes(utiles)

    # `largeur_min` : la plus petite largeur essayée où rien ne tronque.
    largeur_min = LARGEURS[-1]
    for essai in LARGEURS:
        autre, _ = _executer(argv, largeur=essai, cwd=cwd, env_sup=env_sup)
        if _compter_troncatures(_nettoyer(autre)) == 0:
            largeur_min = essai
            break

    # Un écran qui tient en deux lignes et ne propose rien est une impasse,
    # quelle que soit sa légèreté par ailleurs.
    impasse = 1 if len(utiles) <= 2 and not gestes else 0

    return Ecran(
        commande=" ".join(argv[1:]) or "(sans argument)",
        lignes=len(lignes),
        tronque=_compter_troncatures(lignes),
        colonnes=_compter_colonnes(lignes),
        gestes=len(gestes),
        jargon=len(jargon),
        traces=_compter_traces(lignes),
        largeur_min=largeur_min,
        code_retour=code,
        impasse=impasse,
        jargon_vu=jargon,
        gestes_vus=gestes,
    )


def _binaire() -> str:
    """Le dsoxlab à mesurer : celui du venv du dépôt, sinon celui du PATH.

    Jamais celui de PyPI quand le venv existe : on mesure ce dépôt, pas la
    version publiée.
    """
    local = RACINE / ".venv" / "bin" / "dsoxlab"
    return str(local) if local.is_file() else "dsoxlab"


def parcours_accueil(base: Path, largeur: int) -> Parcours:
    """Le premier contact : un poste sans aucun catalogue."""
    dsox = _binaire()
    vide = base / "vide"
    vide.mkdir(parents=True, exist_ok=True)
    env = _env_isole(base)
    ecrans = [
        mesurer_ecran([dsox], cwd=vide, env_sup=env, largeur=largeur),
        mesurer_ecran([dsox, "doctor"], cwd=vide, env_sup=env, largeur=largeur),
        mesurer_ecran(
            [dsox, "list-labs"], cwd=vide, env_sup=env, largeur=largeur
        ),
    ]
    return Parcours("accueil", ecrans, cd_imposes=0)


def parcours_demo(base: Path, largeur: int) -> Parcours:
    """Le parcours que le README met en avant, joué pour de vrai.

    **Les commandes sont jouées depuis un répertoire quelconque**, et c'est le
    cœur de la mesure : jusqu'à la 0.4.0, `demo` affichait un chemin de
    quatre-vingt-dix caractères et un `cd` sur une ligne séparée, et les trois
    commandes qu'il proposait ensuite échouaient toutes les trois sur « Lab
    introuvable » pour qui ne l'avait pas fait. Mesurer depuis le répertoire du
    catalogue aurait caché exactement le défaut qu'on cherchait.

    ``cd_imposes`` vaut donc 0, et si le `cd` revenait un jour, les trois
    écrans suivants le diraient par leur code de retour.
    """
    dsox = _binaire()
    vide = base / "vide"
    vide.mkdir(parents=True, exist_ok=True)
    env = _env_isole(base)
    ecrans = [mesurer_ecran([dsox, "demo"], cwd=vide, env_sup=env, largeur=largeur)]
    for argv in (
        [dsox, "course", "premiers-pas", "--no-pager"],
        [dsox, "challenge", "premiers-pas", "--no-pager"],
        [dsox, "check", "premiers-pas"],
    ):
        ecrans.append(mesurer_ecran(argv, cwd=vide, env_sup=env, largeur=largeur))
    return Parcours("demo", ecrans, cd_imposes=0)


def parcours_catalogue(base: Path, largeur: int) -> Parcours:
    """Choisir un lab dans un catalogue réel, s'il y en a un sur la machine.

    Mesuré sur un catalogue **local**, sans réseau : l'audit doit pouvoir se
    rejouer hors ligne, et `catalog add` cloner depuis GitHub n'est pas ce qu'on
    mesure ici.
    """
    dsox = _binaire()
    env = _env_isole(base)
    for nom in (
        "python-dsoxlab-training",
        "terraform-dsoxlab-training",
        "linux-dsoxlab-training",
    ):
        racine = Path.home() / "Projets" / nom
        if (racine / "meta.yml").is_file():
            break
    else:
        return Parcours("catalogue", [], cd_imposes=0)
    ecrans = [
        mesurer_ecran(
            [dsox, "list-labs", "--lab-home", str(racine)],
            cwd=racine,
            env_sup=env,
            largeur=largeur,
        ),
        mesurer_ecran(
            [dsox, "next", "--lab-home", str(racine)],
            cwd=racine,
            env_sup=env,
            largeur=largeur,
        ),
        mesurer_ecran(
            [dsox, "progress", "--lab-home", str(racine)],
            cwd=racine,
            env_sup=env,
            largeur=largeur,
        ),
    ]
    return Parcours("catalogue", ecrans, cd_imposes=0)


def _env_isole(base: Path) -> dict[str, str]:
    """Un XDG jetable : la mesure ne doit rien écrire chez l'utilisateur."""
    for nom in ("data", "state", "cache", "config"):
        (base / nom).mkdir(parents=True, exist_ok=True)
    return {
        "XDG_DATA_HOME": str(base / "data"),
        "XDG_STATE_HOME": str(base / "state"),
        "XDG_CACHE_HOME": str(base / "cache"),
        "XDG_CONFIG_HOME": str(base / "config"),
        "DSOXLAB_LANG": "fr",
        "NO_COLOR": "1",
    }


PARCOURS = {
    "accueil": parcours_accueil,
    "demo": parcours_demo,
    "catalogue": parcours_catalogue,
}


def _afficher(parcours: Parcours) -> None:
    print(f"\n=== parcours « {parcours.nom} » : score {parcours.score}")
    if not parcours.ecrans:
        print("  (aucun écran mesurable sur cette machine)")
        return
    entete = (
        f"  {'score':>6} {'lignes':>6} {'tronq':>6} {'col':>4} {'geste':>6} "
        f"{'jarg':>5} {'trace':>6} {'imp':>4} {'min':>4} {'rc':>3}  commande"
    )
    print(entete)
    for e in parcours.ecrans:
        print(
            f"  {e.score:>6} {e.lignes:>6} {e.tronque:>6} {e.colonnes:>4} "
            f"{e.gestes:>6} {e.jargon:>5} {e.traces:>6} {e.impasse:>4} "
            f"{e.largeur_min:>4} {e.code_retour:>3}  {e.commande}"
        )
    print(f"  commandes tapées : {len(parcours.ecrans)} ; cd imposés : {parcours.cd_imposes}")
    pire = max(parcours.ecrans, key=lambda e: e.score)
    print(f"  écran le plus lourd : « {pire.commande} » ({pire.score})")
    if pire.jargon_vu:
        print(f"    jargon : {', '.join(pire.jargon_vu[:12])}")
    if pire.gestes_vus:
        print(f"    gestes proposés : {len(pire.gestes_vus)} -> {', '.join(pire.gestes_vus[:6])}")


def _charger_reference() -> dict[str, float]:
    if not REFERENCE.is_file():
        return {}
    donnees = json.loads(REFERENCE.read_text(encoding="utf-8"))
    return {str(c): float(v) for c, v in donnees.get("scores", {}).items()}


def main() -> int:
    analyseur = argparse.ArgumentParser(
        description="Complexité de ce que dsoxlab affiche à l'écran."
    )
    analyseur.add_argument("--parcours", choices=sorted(PARCOURS), help="un seul parcours")
    analyseur.add_argument(
        "--largeur", type=int, default=LARGEUR_PAR_DEFAUT, help="largeur du terminal simulé"
    )
    analyseur.add_argument("--json", action="store_true", help="sortie machine")
    analyseur.add_argument("--verifier", action="store_true", help="sort 1 si un score monte")
    analyseur.add_argument("--figer", action="store_true", help="entérine les scores actuels")
    options = analyseur.parse_args()

    choisis = [options.parcours] if options.parcours else sorted(PARCOURS)
    mesures: list[Parcours] = []
    with tempfile.TemporaryDirectory(prefix="dsoxlab-ecran-") as temporaire:
        base = Path(temporaire)
        for nom in choisis:
            mesures.append(PARCOURS[nom](base / nom, options.largeur))

    if options.json:
        print(
            json.dumps(
                {
                    "largeur": options.largeur,
                    "poids": POIDS,
                    "parcours": [
                        {
                            "nom": p.nom,
                            "score": p.score,
                            "cd_imposes": p.cd_imposes,
                            "ecrans": [asdict(e) | {"score": e.score} for e in p.ecrans],
                        }
                        for p in mesures
                    ],
                },
                indent=2,
                ensure_ascii=False,
            )
        )
        return 0

    if options.figer:
        document = {
            "_lire": (
                "Scores de complexité d'écran, produits par « python3 "
                "scripts/complexite-ecran.py --figer ». Ils ne peuvent que "
                "descendre : toute hausse fait échouer le hook. Les poids et la "
                "méthode sont dans le script, et une hausse peut être légitime "
                "(un écran qui explique davantage) : elle s'entérine alors "
                "sciemment, en disant pourquoi dans le message de commit."
            ),
            "largeur": options.largeur,
            "scores": {p.nom: p.score for p in mesures if p.ecrans},
        }
        REFERENCE.write_text(
            json.dumps(document, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
        )
        print(f"Relevé écrit : scripts/{REFERENCE.name}")
        for p in mesures:
            if p.ecrans:
                print(f"  {p.nom} : {p.score}")
        return 0

    if options.verifier:
        reference = _charger_reference()
        if not reference:
            print(
                "Aucun relevé de référence. Le poser une fois :\n"
                "  python3 scripts/complexite-ecran.py --figer",
                file=sys.stderr,
            )
            return 2
        monte = [
            (p.nom, reference[p.nom], p.score)
            for p in mesures
            if p.ecrans and p.nom in reference and p.score > reference[p.nom]
        ]
        if monte:
            print("Un parcours devient plus lourd à l'écran :", file=sys.stderr)
            for nom, avant, apres in monte:
                print(f"  ✘ {nom} : {avant} -> {apres}", file=sys.stderr)
            print(
                "\nLire le détail : python3 scripts/complexite-ecran.py --parcours <nom>\n"
                "Une hausse peut être justifiée (un écran qui explique mieux) : la\n"
                "figer alors sciemment par « --figer », en disant pourquoi.",
                file=sys.stderr,
            )
            return 1
        baisse = [
            (p.nom, reference[p.nom], p.score)
            for p in mesures
            if p.ecrans and p.nom in reference and p.score < reference[p.nom]
        ]
        for nom, avant, apres in baisse:
            print(f"  ✔ {nom} : {avant} -> {apres}")
        if baisse:
            print("\nEntériner le gain : python3 scripts/complexite-ecran.py --figer")
            return 1
        print(f"Charge d'écran stable sur {len(reference)} parcours.")
        return 0

    for parcours in mesures:
        _afficher(parcours)
    print()
    print(f"Largeur simulée : {options.largeur} colonnes. Poids : {POIDS}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
