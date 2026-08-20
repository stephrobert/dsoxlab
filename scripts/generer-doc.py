#!/usr/bin/env python3
"""Génère depuis la CLI ce que la documentation ne doit plus recopier.

Une table de commandes écrite à la main dérive, et personne ne s'en aperçoit :
celle du README annonçait encore `dsoxlab clean` exécutant un `cleanup.sh`,
alors que le zéro-bash est un invariant du contrat depuis longtemps, et il y
manquait `demo` et `support`. Rien ne lit la documentation en même temps que le
code.

Le principe : la section vit entre deux marqueurs, elle est produite par
l'application elle-même, et un mode `--verifier` la compare à ce qu'elle devrait
être. La CI refuse alors une documentation périmée, exactement comme elle
refuserait un test rouge.

Usage :
    python3 scripts/generer-doc.py             # réécrit les sections générées
    python3 scripts/generer-doc.py --verifier   # sort 1 si une section a dérivé
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

RACINE = Path(__file__).resolve().parent.parent

DEBUT = "<!-- BEGIN COMMANDES : généré par scripts/generer-doc.py, ne pas éditer -->"
FIN = "<!-- END COMMANDES -->"

#: Fichier de documentation et langue dans laquelle le remplir.
CIBLES = {
    "README.md": "en",
    "README.fr.md": "fr",
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
        return 1
    return 1 if perimes else 0


if __name__ == "__main__":
    sys.exit(main())
