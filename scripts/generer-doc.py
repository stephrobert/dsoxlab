#!/usr/bin/env python3
"""Confronte la documentation au code, sur ce que le code peut affirmer.

Deux dérives, la même cause : rien ne lit la documentation en même temps que le
code.

1. **La table des commandes.** Écrite à la main, celle du README annonçait
   encore `dsoxlab clean` exécutant un `cleanup.sh`, alors que le zéro-bash est
   un invariant du contrat depuis longtemps, et il y manquait `demo` et
   `support`. Elle est désormais produite par l'application elle-même, entre
   deux marqueurs.

2. **Les emplacements de fichiers.** La section « Persistence » des deux README
   annonçait `~/.local/share/dsoxlab/progress.db`, `~/.config/dsoxlab/config.yaml`
   et deux variables XDG que rien ne lit : trois affirmations fausses dans le
   document que lit quiconque cherche où sont ses notes (issue #86). Les
   emplacements de référence sont donc obtenus **en appelant le code**, dans un
   sous-processus dont le `HOME` est jetable, puis en relevant ce qui a
   réellement été créé.

Un mode `--verifier` compare sans réécrire : la CI refuse une documentation
périmée, exactement comme elle refuserait un test rouge. La table se régénère,
les chemins non : un chemin faux se corrige à la main, puisque seul l'auteur
sait ce qu'il voulait dire.

Usage :
    python3 scripts/generer-doc.py             # réécrit les sections générées
    python3 scripts/generer-doc.py --verifier   # sort 1 si la doc a dérivé
"""

from __future__ import annotations

import fnmatch
import json
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import NamedTuple

RACINE = Path(__file__).resolve().parent.parent

DEBUT = "<!-- BEGIN COMMANDES : généré par scripts/generer-doc.py, ne pas éditer -->"
FIN = "<!-- END COMMANDES -->"

#: Fichier de documentation et langue dans laquelle le remplir.
CIBLES = {
    "docs/commands.md": "en",
    "docs/commands.fr.md": "fr",
}

TITRES = {
    "en": ("| Command | Purpose |", "| --- | --- |"),
    "fr": ("| Commande | Rôle |", "| --- | --- |"),
}

#: Programme joué dans un sous-processus par langue. L'aide des commandes est
#: résolue par `_()` au moment de l'import : changer la langue APRÈS n'aurait
#: aucun effet, d'où un interpréteur neuf par langue.
_EXTRACTION = """
import json
from dsoxlab.cli import app

commandes = []
for info in app.registered_commands:
    if info.name:
        commandes.append((info.name, (info.help or "").strip()))
for groupe in app.registered_groups:
    sous = getattr(groupe, "typer_instance", None)
    if groupe.name and sous is not None:
        for info in sous.registered_commands:
            if info.name:
                commandes.append(
                    (f"{groupe.name} {info.name}", (info.help or "").strip())
                )
print(json.dumps(sorted(commandes)))
"""


def commandes(langue: str) -> list[tuple[str, str]]:
    """Les commandes de la CLI et leur aide, dans une langue donnée."""
    env = dict(os.environ, DSOXLAB_LANG=langue, PYTHONPATH=str(RACINE / "src"))
    proc = subprocess.run(
        [sys.executable, "-c", _EXTRACTION],
        capture_output=True, text=True, env=env, cwd=RACINE, check=True,
    )
    return [(nom, aide) for nom, aide in json.loads(proc.stdout)]


def table(langue: str) -> str:
    entete, separateur = TITRES[langue]
    lignes = [DEBUT, "", entete, separateur]
    for nom, aide in commandes(langue):
        # L'aide peut contenir des barres verticales, qui casseraient la table.
        lignes.append(f"| `dsoxlab {nom}` | {aide.replace('|', '/')} |")
    lignes += ["", FIN]
    return "\n".join(lignes)


def remplacer(document: Path, contenu: str) -> str | None:
    """Rend le texte mis à jour, ou None si les marqueurs sont absents."""
    texte = document.read_text(encoding="utf-8")
    if DEBUT not in texte or FIN not in texte:
        return None
    avant = texte[: texte.index(DEBUT)]
    apres = texte[texte.index(FIN) + len(FIN) :]
    return avant + contenu + apres


# ── les chemins cités par la documentation existent-ils ? ─────────────────────

#: Valeur injectée à la place de l'identifiant du catalogue et du provider. Elle
#: devient un joker dans les motifs de référence, puisque la documentation, elle,
#: écrit `<catalog-id>`.
SENTINELLE = "catalogue-sentinelle"

#: Chemins que la documentation cite **pour dire qu'ils n'existent pas**, et les
#: seules pages qui ont le droit de les citer. L'exemption est nominative : une
#: dispense globale rouvrirait la porte qu'elle prétend fermer, puisque n'importe
#: quelle page pourrait alors réannoncer `progress.db` comme un emplacement réel.
#:
#: `absents_devenus_reels()` tient l'autre bout : le jour où l'un d'eux devient
#: réel (la découverte multi-catalogues de #78, par exemple), la page qui
#: l'annonce absent devient fausse à son tour, et le contrôle le dit.
CHEMINS_ABSENTS = {
    "~/.config/dsoxlab": {"docs/files.md", "docs/files.fr.md"},
    "~/.config/dsoxlab/config.yaml": {"docs/files.md", "docs/files.fr.md"},
    "~/.local/share/dsoxlab/progress.db": {"docs/files.md", "docs/files.fr.md"},
    # Écrit jusqu'en 0.1.61, plus depuis : les pages le disent pour qui en
    # aurait un qui traîne d'une ancienne installation.
    "~/.local/bin/dsoxlab": {"docs/files.md", "docs/files.fr.md"},
}

#: Programme joué dans un sous-processus : il appelle les fonctions que la CLI
#: appelle, sur un `HOME` jetable, et rend les emplacements obtenus **plus** ce
#: qui a été créé sur le disque. Les deux sont nécessaires : certaines fonctions
#: rendent un chemin sans le créer (le fragment `~/.ssh/config.d`), et le
#: provisioning crée des répertoires que personne ne rend (`cloud-init/`).
_CHEMINS_REELS = r"""
import json
import os
import tempfile
from pathlib import Path

from dsoxlab import config, locking, logging_setup
from dsoxlab.discovery.repo import read_repo_metadata
from dsoxlab.infra import inventory, terraform
from dsoxlab.services import demo, update_check
from dsoxlab.sessions import store
from dsoxlab.templates import template_root

SENTINELLE = "__SENTINELLE__"

maison = Path(os.environ["HOME"])
rendus = set()
noms = set()

providers = sorted(
    p.name for p in (template_root() / "terraform").iterdir() if p.is_dir()
)

with tempfile.TemporaryDirectory() as tmp:
    racine = Path(tmp)
    (racine / "ssh").mkdir()
    (racine / "ssh" / "id_ed25519.pub").write_text("ssh-ed25519 AAAA sentinelle\n")

    # Un provider à la fois : chacun a son work-dir, et la documentation a le
    # droit de nommer celui qu'elle veut.
    for provider in providers:
        (racine / "meta.yml").write_text(
            "repo:\n"
            "  id: " + SENTINELLE + "\n"
            "  category: domaine\n"
            "infra:\n"
            "  provider: " + provider + "\n"
            "  network: reseau\n"
            "  cidr: 10.10.10.0/24\n"
            "  hosts:\n"
            "    - name: hote.lab\n"
            "      distro: alma10\n",
            encoding="utf-8",
        )
        meta = read_repo_metadata(racine)
        rendus.update(str(c) for c in (
            terraform.workdir(meta),
            terraform.write_tfvars(meta),
            inventory.inventory_path(meta),
            inventory.ssh_config_path(meta),
            inventory.user_ssh_config_path(meta),
        ))

    avant = {p.name for p in racine.iterdir()}
    store.record_hint(racine, "lab-sentinelle", 0, 5)
    config.set_active_lab(racine, "lab-sentinelle")
    noms = {p.name for p in racine.iterdir()} - avant

    rendus.update(str(c) for c in (
        logging_setup.chemin_journal(),
        locking.lock_path(racine),
        demo.destination(),
        update_check.cache_path(),
    ))

rendus.update(str(p) for p in maison.rglob("*"))
print(json.dumps({
    "depot": sorted(noms),
    "maison": sorted(
        "~/" + str(Path(c).relative_to(maison))
        for c in rendus
        if str(c).startswith(str(maison) + os.sep)
    ),
}))
"""

#: `Path.home() / "a" / "b"` dans les sources : les emplacements que le code
#: compose sans passer par une fonction qu'on puisse appeler (le wrapper de
#: `install`, les fichiers d'identifiants des providers).
_CHAINE_MAISON = re.compile(r'Path\.home\(\)((?:\s*/\s*f?"[^"]*")+)')
_MORCEAU = re.compile(r'f?"([^"]*)"')

#: Racines XDG dont le code ne construit que la valeur par défaut. Les retenir
#: comme références ouvertes rendrait acceptable n'importe quoi sous elles,
#: c'est-à-dire précisément les chemins que ce contrôle existe pour attraper.
_RACINES_XDG = frozenset({"~/.local/state", "~/.local/share", "~/.cache"})

_BLOC_CODE = re.compile(r"```.*?```", re.DOTALL)
_CODE_EN_LIGNE = re.compile(r"`([^`\n]+)`")
_SOUS_MAISON = re.compile(r"~/[A-Za-z0-9._/<>{}-]+")
_FICHIER_DEPOT = re.compile(r"[A-Za-z0-9._/<>{}-]*\.dsoxlab[A-Za-z0-9._-]*")


def _pages_versionnees() -> set[Path] | None:
    """Les Markdown que git suit, ou None si la question n'a pas de sens ici.

    None quand le dépôt n'est pas un dépôt git, ou que git est absent : le
    contrôle retombe alors sur tout ce qu'il trouve, ce qui est le comportement
    d'origine.
    """
    try:
        res = subprocess.run(
            ["git", "-C", str(RACINE), "ls-files", "-z", "--", "*.md"],
            capture_output=True, text=True, check=False, timeout=30,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if res.returncode != 0:
        return None
    return {RACINE / nom for nom in res.stdout.split("\0") if nom}


def documents_documentation() -> list[Path]:
    """Les pages de documentation, celles qui décrivent le produit d'aujourd'hui.

    Le CHANGELOG en est exclu : il raconte le passé, où un chemin retiré depuis
    a toute sa place.

    Les fichiers **non versionnés** en sont exclus aussi, et pour la même raison
    de fond : ils ne décrivent pas le produit. Un `CLAUDE.md` d'agent, un
    brouillon de notes, tout Markdown que git ne suit pas vit sur une seule
    machine. Les inclure rendait le contrôle rouge chez le contributeur et vert
    en intégration continue, où ces fichiers n'existent pas : le pire écart
    possible pour une porte de contribution, puisqu'il apprend à ne pas croire
    la suite là où elle est justement censée faire foi.
    """
    pages = sorted(RACINE.glob("*.md")) + sorted((RACINE / "docs").rglob("*.md"))
    pages = [p for p in pages if not p.name.startswith("CHANGELOG")]
    versionnees = _pages_versionnees()
    if versionnees is None:
        return pages
    return [p for p in pages if p in versionnees]


def chemins_reels() -> tuple[set[str], set[str]]:
    """Les emplacements que le code produit vraiment.

    Rend deux ensembles : les noms de fichiers posés **dans le catalogue**, et
    les motifs de chemins sous le répertoire personnel.
    """
    with tempfile.TemporaryDirectory() as maison:
        env = dict(
            os.environ,
            HOME=maison,
            PYTHONPATH=str(RACINE / "src"),
        )
        # Un XDG_* hérité de la session déplacerait les chemins hors de ce HOME
        # jetable, et la mesure ne porterait plus sur rien.
        for variable in ("XDG_STATE_HOME", "XDG_DATA_HOME", "XDG_CACHE_HOME"):
            env.pop(variable, None)
        proc = subprocess.run(
            [sys.executable, "-c", _CHEMINS_REELS.replace("__SENTINELLE__", SENTINELLE)],
            capture_output=True, text=True, env=env, cwd=RACINE, check=True,
        )
        data = json.loads(proc.stdout)
    return set(data["depot"]), set(data["maison"])


def chemins_du_code() -> set[str]:
    """Les chemins que les sources composent depuis `Path.home()`."""
    trouves: set[str] = set()
    for source in sorted((RACINE / "src").rglob("*.py")):
        texte = source.read_text(encoding="utf-8")
        for chaine in _CHAINE_MAISON.findall(texte):
            segments = [
                "*" if "{" in morceau else morceau
                for morceau in _MORCEAU.findall(chaine)
            ]
            chemin = "~/" + "/".join(segments)
            if chemin not in _RACINES_XDG:
                trouves.add(chemin)
    return trouves


def _nettoyer(brut: str) -> str:
    """Retire la ponctuation que la prose colle à la fin d'un chemin."""
    return brut.rstrip("/.,;:)").rstrip("/")


def chemins_cites(texte: str) -> tuple[set[str], set[str]]:
    """Les chemins cités **dans du code** : blocs clôturés et accents graves.

    La prose emploie les mêmes mots sans les citer, et un contrôle qui crie au
    loup sur de la grammaire finit désactivé, ce qui est pire que son absence.
    """
    fragments = _BLOC_CODE.findall(texte)
    fragments += _CODE_EN_LIGNE.findall(_BLOC_CODE.sub("", texte))

    maison: set[str] = set()
    depot: set[str] = set()
    for fragment in fragments:
        restant = fragment
        for brut in _SOUS_MAISON.findall(fragment):
            maison.add(_nettoyer(brut))
            restant = restant.replace(brut, " ")
        # Après retrait des chemins sous ~, ce qui reste et porte `.dsoxlab`
        # est un fichier posé dans le catalogue.
        for brut in _FICHIER_DEPOT.findall(restant):
            depot.add(_nettoyer(brut).rsplit("/", 1)[-1])
    return maison, depot


def _segments(chemin: str) -> list[str]:
    """Un chemin découpé, chaque partie variable devenue un joker."""
    parties = [p for p in chemin.removeprefix("~/").split("/") if p]
    return [
        "*" if ("<" in p or "{" in p or SENTINELLE in p) else p
        for p in parties
    ]


def _compatibles(cite: str, reference: str) -> bool:
    return fnmatch.fnmatch(cite, reference) or fnmatch.fnmatch(reference, cite)


def _correspond(cite: list[str], reference: list[str], *, ouverte: bool) -> bool:
    """Le chemin cité désigne-t-il cette référence ?

    Une référence **fermée** vient d'un appel au code : le chemin cité doit en
    être un préfixe (citer un répertoire de la liste est légitime, inventer un
    fichier dedans ne l'est pas). Une référence **ouverte** vient d'une lecture
    des sources, où le code ajoute encore des segments : la comparaison
    s'arrête alors au plus court.
    """
    if not ouverte and len(cite) > len(reference):
        return False
    commun = min(len(cite), len(reference))
    if commun == 0:
        return False
    return all(
        _compatibles(c, r)
        for c, r in zip(cite[:commun], reference[:commun], strict=True)
    )


class References(NamedTuple):
    """Ce que le code produit, prêt à être confronté à une page.

    Obtenu une fois (le relevé passe par un sous-processus), puis réutilisé :
    les tests s'en servent pour éprouver le contrôle sur des textes fabriqués,
    sans repayer la mesure à chaque cas.
    """

    noms_depot: set[str]
    fermees: list[list[str]]
    ouvertes: list[list[str]]
    racines: set[str]


def references() -> References:
    """Relève les emplacements réels, par appel du code puis lecture des sources."""
    noms_depot, fermees = chemins_reels()
    fermees_seg = [_segments(c) for c in fermees]
    ouvertes_seg = [_segments(c) for c in chemins_du_code()]
    return References(
        noms_depot=noms_depot | {Path(c).name for c in fermees},
        fermees=fermees_seg,
        ouvertes=ouvertes_seg,
        # Un chemin sous ~ n'est contrôlé que si sa première partie est une de
        # celles que dsoxlab occupe : `~/Projets/mon-catalogue` est un exemple
        # de répertoire de travail, pas une affirmation sur l'outil.
        racines={seg[0] for seg in fermees_seg + ouvertes_seg if seg},
    )


def chemins_inconnus(
    texte: str, refs: References, *, dispenses: frozenset[str] = frozenset()
) -> list[str]:
    """Les chemins que ce texte cite et que le code ne produit nulle part."""
    maison, depot = chemins_cites(texte)
    inconnus: list[str] = []

    for chemin in sorted(maison):
        if chemin in dispenses:
            continue
        segments = _segments(chemin)
        if not segments or segments[0] not in refs.racines:
            continue
        connu = any(
            _correspond(segments, ref, ouverte=False) for ref in refs.fermees
        ) or any(
            _correspond(segments, ref, ouverte=True) for ref in refs.ouvertes
        )
        if not connu:
            inconnus.append(chemin)

    inconnus += [nom for nom in sorted(depot) if nom not in refs.noms_depot]
    return inconnus


def dispenses_de(document: str) -> frozenset[str]:
    """Les chemins que cette page a le droit de citer comme inexistants."""
    return frozenset(
        chemin for chemin, pages in CHEMINS_ABSENTS.items() if document in pages
    )


def verifier_chemins(refs: References | None = None) -> list[str]:
    """Rend un message par chemin cité qui ne correspond à rien dans le code."""
    refs = refs or references()
    problemes: list[str] = []
    for document in documents_documentation():
        relatif = str(document.relative_to(RACINE))
        inconnus = chemins_inconnus(
            document.read_text(encoding="utf-8"),
            refs,
            dispenses=dispenses_de(relatif),
        )
        problemes += [
            f"  ✘ {relatif} cite « {chemin} », que le code ne produit nulle part"
            for chemin in inconnus
        ]
    return problemes


def absents_devenus_reels(refs: References | None = None) -> list[str]:
    """Les chemins déclarés absents que le code produit désormais."""
    refs = refs or references()
    return sorted(
        chemin
        for chemin in CHEMINS_ABSENTS
        if any(
            _correspond(_segments(chemin), ref, ouverte=False) for ref in refs.fermees
        )
    )


def main() -> int:
    verifier = "--verifier" in sys.argv
    perimes: list[str] = []

    for nom, langue in CIBLES.items():
        document = RACINE / nom
        if not document.is_file():
            print(f"  ! {nom} absent, ignoré")
            continue

        attendu = remplacer(document, table(langue))
        if attendu is None:
            print(
                f"  ! {nom} ne porte pas les marqueurs de section générée.\n"
                f"    Ajoute-les autour de la table des commandes :\n"
                f"    {DEBUT}\n    {FIN}"
            )
            perimes.append(nom)
            continue

        if attendu == document.read_text(encoding="utf-8"):
            print(f"  ✔ {nom} à jour")
            continue

        if verifier:
            print(f"  ✘ {nom} a dérivé de la CLI")
            perimes.append(nom)
        else:
            document.write_text(attendu, encoding="utf-8")
            print(f"  ✔ {nom} régénéré")

    if perimes and verifier:
        print(
            "\nLa documentation ne décrit plus la CLI. Régénère-la :\n"
            "    python3 scripts/generer-doc.py\n"
        )

    # Les chemins ne se régénèrent pas : seul l'auteur sait ce qu'il voulait
    # écrire. Ils sont donc signalés dans les deux modes.
    refs = references()
    problemes = verifier_chemins(refs)
    for message in problemes:
        print(message)
    if problemes:
        print(
            "\nUn chemin cité par la documentation ne correspond à aucun\n"
            "emplacement que le code produit. Corrige la page, ou la liste\n"
            "CHEMINS_ABSENTS de ce script si le chemin est cité pour dire\n"
            "qu'il n'existe pas.\n"
        )

    reels = absents_devenus_reels(refs)
    for chemin in reels:
        print(f"  ✘ « {chemin} » est déclaré absent, mais le code le produit désormais")
    if reels:
        print(
            "\nLa documentation qui annonce ces chemins comme inexistants est\n"
            "devenue fausse. Mets-la à jour, puis retire-les de CHEMINS_ABSENTS.\n"
        )

    if not problemes and not reels:
        print("  ✔ les chemins cités existent tous dans le code")

    return 1 if (perimes or problemes or reels) else 0


if __name__ == "__main__":
    sys.exit(main())
