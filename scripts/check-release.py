#!/usr/bin/env python3
"""Vérifie qu'un tag de release peut être posé sans rien casser.

Le garde-fou du workflow arrive trop tard : il parle une fois le tag poussé,
et il faut alors le supprimer des deux côtés. PyPI, lui, est définitif — un
numéro de version consommé ne se réutilise jamais. D'où ce contrôle local,
qui rejoue à froid les cinq étapes que RELEASING confie à la vigilance
humaine, et qui a un cas de figure réel derrière chaque test.

Usage :
    python3 scripts/check-release.py           # déduit la version du pyproject
    python3 scripts/check-release.py v0.1.28   # vérifie un tag précis

Sortie 0 : le tag peut être posé, la commande exacte est affichée.
Sortie 1 : au moins un contrôle a échoué, chacun dit quoi corriger.
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
import urllib.error
import urllib.request
from pathlib import Path

RACINE = Path(__file__).resolve().parent.parent

VERT, ROUGE, JAUNE, GRAS, RAZ = (
    "\033[32m", "\033[31m", "\033[33m", "\033[1m", "\033[0m"
)


class Rapport:
    """Accumule les verdicts pour tout afficher, même après un échec.

    S'arrêter au premier problème ferait relancer le script cinq fois de
    suite. On veut la liste complète en une passe.
    """

    def __init__(self) -> None:
        self.echecs: list[str] = []

    def ok(self, titre: str, detail: str = "") -> None:
        suffixe = f" {detail}" if detail else ""
        print(f"  {VERT}✔{RAZ} {titre}{suffixe}")

    def ko(self, titre: str, quoi_faire: str) -> None:
        print(f"  {ROUGE}✘{RAZ} {titre}")
        print(f"      {quoi_faire}")
        self.echecs.append(titre)

    def note(self, titre: str, detail: str) -> None:
        print(f"  {JAUNE}!{RAZ} {titre}")
        print(f"      {detail}")


def git(*args: str) -> str:
    return subprocess.run(
        ["git", *args], cwd=RACINE, capture_output=True, text=True
    ).stdout.strip()


def version_empaquetee() -> str | None:
    m = re.search(
        r'^version = "([^"]+)"',
        (RACINE / "pyproject.toml").read_text(encoding="utf-8"),
        re.M,
    )
    return m.group(1) if m else None


def _verifier_arbre(r: Rapport) -> None:
    if git("status", "--porcelain"):
        r.ko(
            "L'arbre de travail n'est pas propre",
            "Committe ou remise tes modifications : le tag figerait un état "
            "que personne d'autre n'a.",
        )
    else:
        r.ok("Arbre de travail propre")


def _verifier_branche(r: Rapport) -> None:
    branche = git("rev-parse", "--abbrev-ref", "HEAD")
    if branche != "main":
        r.ko(
            f"Branche courante : {branche}",
            "Place-toi sur main : c'est le commit fusionné qui doit être "
            "publié, pas une branche de travail.",
        )
        return
    subprocess.run(["git", "fetch", "-q", "origin"], cwd=RACINE, check=False)
    local, distant = git("rev-parse", "HEAD"), git("rev-parse", "origin/main")
    if local != distant:
        r.ko(
            "main diverge de origin/main",
            "Lance « git pull ». Taguer un commit local non poussé produit un "
            "tag qui ne référence rien de public.",
        )
    else:
        r.ok("Sur main, à jour avec origin")


def _verifier_tag(r: Rapport, tag: str, version: str) -> None:
    # Le défaut vécu deux fois : v0.1.22 a republié 0.1.21, et v0.1.25 a
    # publié 0.1.26 sous son propre nom.
    if tag.lstrip("v") != version:
        r.ko(
            f"Le tag {tag} ne correspond pas à la version empaquetée {version}",
            "Tague le commit qui porte le bon bump, ou aligne pyproject.toml "
            "avant de taguer. C'est exactement ce qui a produit les trous "
            "0.1.22 et 0.1.25 sur PyPI.",
        )
    else:
        r.ok(f"Le tag {tag} correspond à la version empaquetée")

    if tag in git("tag").splitlines():
        r.ko(
            f"Le tag {tag} existe déjà en local",
            f"Supprime-le (git tag -d {tag}) ou choisis une autre version.",
        )
    else:
        r.ok(f"Le tag {tag} est libre en local")


def _verifier_changelog(r: Rapport, version: str) -> None:
    # Le projet est bilingue : une entrée en anglais seul est incomplète, et
    # release.yml extrait la section du CHANGELOG pour en faire les notes.
    # Sans section, la Release sort avec « Release X.Y.Z » et rien d'autre.
    for nom in ("CHANGELOG.md", "CHANGELOG.fr.md"):
        contenu = (RACINE / nom).read_text(encoding="utf-8")
        if re.search(rf"^## \[{re.escape(version)}\]", contenu, re.M):
            r.ok(f"{nom} décrit la version {version}")
        else:
            r.ko(
                f"{nom} n'a pas de section [{version}]",
                "Ajoute-la : le workflow en tire les notes de release, sinon "
                "elles sortent vides.",
            )


def _verifier_lock(r: Rapport, version: str) -> None:
    lock = (RACINE / "uv.lock").read_text(encoding="utf-8")
    if re.search(
        rf'name = "dsoxlab"\nversion = "{re.escape(version)}"', lock
    ):
        r.ok("uv.lock est aligné sur la version")
    else:
        r.ko(
            "uv.lock ne connaît pas cette version",
            "Lance « uv lock » et committe le résultat.",
        )


def _verifier_pypi(r: Rapport, version: str) -> None:
    # PyPI est définitif. Republier un numéro déjà pris fait échouer le job
    # d'upload, après que le tag et la Release ont été créés.
    try:
        with urllib.request.urlopen(  # noqa: S310 - URL constante, https
            "https://pypi.org/pypi/dsoxlab/json", timeout=5
        ) as reponse:
            publiees = set(json.loads(reponse.read().decode("utf-8"))["releases"])
    except (urllib.error.URLError, OSError, ValueError, KeyError):
        r.note(
            "PyPI injoignable",
            "Contrôle sauté. Vérifie à la main que la version n'est pas déjà "
            "publiée : un numéro consommé ne se réutilise jamais.",
        )
        return
    if version in publiees:
        r.ko(
            f"La version {version} est DÉJÀ publiée sur PyPI",
            "Choisis le numéro suivant. PyPI refusera l'upload, et le tag "
            "comme la Release auront déjà été créés.",
        )
    else:
        r.ok(f"La version {version} est libre sur PyPI")


def _verifier_ci(r: Rapport) -> None:
    # RELEASING demande d'attendre une CI verte : le tag construit depuis ce
    # commit, et PyPI ne se rattrape pas.
    sha = git("rev-parse", "HEAD")
    sortie = subprocess.run(
        ["gh", "run", "list", "--commit", sha, "--json", "conclusion,name,status"],
        cwd=RACINE, capture_output=True, text=True,
    )
    if sortie.returncode != 0 or not sortie.stdout.strip():
        r.note("État de la CI inconnu", "gh indisponible : vérifie à la main.")
        return
    try:
        runs = json.loads(sortie.stdout)
    except ValueError:
        r.note("État de la CI illisible", "Vérifie à la main.")
        return
    en_cours = [x["name"] for x in runs if x.get("status") != "completed"]
    echoues = [
        x["name"] for x in runs
        if x.get("status") == "completed" and x.get("conclusion") not in
        (None, "success", "skipped", "neutral")
    ]
    if echoues:
        r.ko(
            f"CI en échec sur ce commit : {', '.join(sorted(set(echoues)))}",
            "Corrige avant de taguer : le tag publie ce commit tel quel.",
        )
    elif en_cours:
        r.note(
            f"CI encore en cours : {', '.join(sorted(set(en_cours)))}",
            "Attends la fin. PyPI est définitif.",
        )
    else:
        r.ok("CI verte sur ce commit")


def main() -> int:
    version = version_empaquetee()
    if version is None:
        print(f"{ROUGE}pyproject.toml ne déclare aucune version.{RAZ}")
        return 1
    tag = sys.argv[1] if len(sys.argv) > 1 else f"v{version}"

    print(f"\n{GRAS}Contrôle avant tag {tag}{RAZ}\n")
    r = Rapport()
    _verifier_arbre(r)
    _verifier_branche(r)
    _verifier_tag(r, tag, version)
    _verifier_changelog(r, version)
    _verifier_lock(r, version)
    _verifier_pypi(r, version)
    _verifier_ci(r)

    print()
    if r.echecs:
        print(f"{ROUGE}{GRAS}{len(r.echecs)} contrôle(s) en échec.{RAZ} "
              "Ne pose pas le tag.\n")
        return 1
    print(f"{VERT}{GRAS}Tout est bon.{RAZ} Pose le tag :\n")
    print(f'    git tag -a {tag} -m "{tag}" && git push origin {tag}\n')
    return 0


if __name__ == "__main__":
    sys.exit(main())
