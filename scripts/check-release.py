#!/usr/bin/env python3
"""Vérifie qu'un tag de release peut être posé sans rien casser.

Le garde-fou du workflow arrive trop tard : il parle une fois le tag poussé,
et il faut alors le supprimer des deux côtés. PyPI, lui, est définitif — un
numéro de version consommé ne se réutilise jamais. D'où ce contrôle local,
qui rejoue à froid les cinq étapes que RELEASING confie à la vigilance
humaine, et qui a un cas de figure réel derrière chaque test.

Le pendant existe pour l'APRÈS. Le workflow vert ne prouve pas que la version
est installable : à la publication de la 0.1.42, l'upload avait bien reçu deux
« 200 OK » de PyPI, la page projet répondait, et pourtant l'index simple, le
seul que lisent pip et uv, ne listait pas encore la version. Un « c'est
publié » fondé sur le statut du workflow était faux pendant plusieurs minutes.

Usage :
    python3 scripts/check-release.py           # déduit la version du pyproject
    python3 scripts/check-release.py v0.1.28   # vérifie un tag précis
    python3 scripts/check-release.py --publiee # APRÈS le tag : est-ce arrivé ?

Sortie 0 : le tag peut être posé, la commande exacte est affichée.
Sortie 1 : au moins un contrôle a échoué, chacun dit quoi corriger.
Sortie 2 : rien n'est faux, mais il est trop tôt. Relancer plus tard.
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
        self.attentes: list[str] = []

    def ok(self, titre: str, detail: str = "") -> None:
        suffixe = f" {detail}" if detail else ""
        print(f"  {VERT}✔{RAZ} {titre}{suffixe}")

    def ko(self, titre: str, quoi_faire: str) -> None:
        print(f"  {ROUGE}✘{RAZ} {titre}")
        print(f"      {quoi_faire}")
        self.echecs.append(titre)

    def note(self, titre: str, detail: str) -> None:
        """Information : n'empêche pas de taguer."""
        print(f"  {JAUNE}!{RAZ} {titre}")
        print(f"      {detail}")

    def attendre(self, titre: str, detail: str) -> None:
        """Rien n'est faux, mais il est trop tôt pour taguer.

        Distinct d'un échec : il n'y a rien à corriger, seulement à
        attendre. Distinct d'une note : conclure « tout est bon » ici
        reviendrait à encourager ce que RELEASING interdit.
        """
        print(f"  {JAUNE}⏳{RAZ} {titre}")
        print(f"      {detail}")
        self.attentes.append(titre)


def git_resultat(*args: str) -> subprocess.CompletedProcess[str]:
    # check=False : plusieurs appelants attendent un code retour non nul comme
    # RÉPONSE (un tag inconnu, un `ls-remote` hors ligne). C'est à eux de
    # décider ce qu'il signifie, pas à subprocess de lever.
    return subprocess.run(
        ["git", *args], cwd=RACINE, capture_output=True, text=True, check=False
    )


def git(*args: str) -> str:
    """La sortie standard de git, vide si la commande a échoué.

    Attention en l'appelant : une sortie vide ne distingue pas « git a répondu
    rien » de « git a échoué ». Là où cette confusion transformerait un rouge en
    vert, passer par :func:`git_resultat` et lire le code retour.
    """
    return git_resultat(*args).stdout.strip()


def version_empaquetee() -> str | None:
    m = re.search(
        r'^version = "([^"]+)"',
        (RACINE / "pyproject.toml").read_text(encoding="utf-8"),
        re.MULTILINE,
    )
    return m.group(1) if m else None


def _verifier_arbre(r: Rapport) -> None:
    """Ce que le tag figerait, et ce qu'il laisserait derrière lui.

    Deux questions, et une seule bloque. Un fichier **suivi** modifié rend le
    tag menteur : il figerait un commit qui ne correspond pas à ce qu'on a sous
    les yeux. Un fichier **non suivi**, lui, n'entre dans aucun commit ; il ne
    peut que signaler un `git add` oublié, ce qu'aucun script ne sait trancher à
    la place de qui écrit le code.

    Les confondre coûtait cher ici : l'environnement de ce dépôt monte en
    permanence des nœuds `/dev/null` à la racine (`.bashrc`, `.gitconfig`,
    `.idea`, `.mcp.json`…), que `git status --porcelain` liste en non suivis.
    Le contrôle passait ou échouait selon que ces montages étaient visibles au
    moment de l'appel, c'est-à-dire par intermittence, dans l'outil même qui
    garde une publication définitive. Un garde-fou qui se déclenche au hasard
    finit contourné, et c'est alors tout le contrôle qui ne sert plus.
    """
    # Garde-fou : « rien à signaler » vaut feu vert, or un git en échec rend lui
    # aussi une sortie vide. On lit le code retour pour distinguer les deux.
    suivis = git_resultat("status", "--porcelain", "--untracked-files=no")
    if suivis.returncode != 0:
        r.ko(
            "Impossible de lire l'état de l'arbre de travail",
            f"git status a échoué : {suivis.stderr.strip() or 'sans message'}",
        )
        return
    if suivis.stdout.strip():
        r.ko(
            "L'arbre de travail n'est pas propre",
            "Committe ou remise tes modifications : le tag figerait un état "
            "que personne d'autre n'a.",
        )
    else:
        r.ok("Arbre de travail propre")

    tous = git_resultat("status", "--porcelain")
    if tous.returncode != 0:
        return
    non_suivis = [
        ligne[3:] for ligne in tous.stdout.splitlines() if ligne.startswith("?? ")
    ]
    if non_suivis:
        apercu = ", ".join(sorted(non_suivis)[:6])
        reste = f" (et {len(non_suivis) - 6} autres)" if len(non_suivis) > 6 else ""
        r.note(
            f"{len(non_suivis)} fichier(s) non suivi(s), qui n'iront pas dans le tag",
            f"{apercu}{reste}\n"
            "      Si l'un d'eux devait être publié, il manque un git add : "
            "la version partirait sans lui.",
        )


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
        if re.search(rf"^## \[{re.escape(version)}\]", contenu, re.MULTILINE):
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
        with urllib.request.urlopen(
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
    # check=False : `gh` absent ou non authentifié est un cas prévu, traité
    # deux lignes plus bas en « état de la CI inconnu ».
    sortie = subprocess.run(
        ["gh", "run", "list", "--commit", sha, "--json", "conclusion,name,status"],
        cwd=RACINE, capture_output=True, text=True, check=False,
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
        r.attendre(
            f"CI encore en cours : {', '.join(sorted(set(en_cours)))}",
            "Attends la fin, puis relance ce contrôle. PyPI est définitif.",
        )
    else:
        r.ok("CI verte sur ce commit")


# ── après le tag : la version est-elle réellement arrivée ? ──────────────────

def _index_simple() -> str | None:
    """Le contenu de l'index simple de PyPI, ou None s'il est injoignable.

    C'est CET index que lisent pip et uv pour résoudre une version, et lui seul
    fait foi. L'API JSON et la page projet peuvent répondre avant lui.
    """
    try:
        with urllib.request.urlopen(
            "https://pypi.org/simple/dsoxlab/", timeout=10
        ) as reponse:
            return reponse.read().decode("utf-8", "replace")
    except (urllib.error.URLError, OSError):
        return None


def _verifier_installable(r: Rapport, version: str) -> None:
    """La version est-elle visible là où un installateur la cherche ?

    Mesuré sur la 0.1.42 : la page projet et l'API JSON répondaient 200 alors
    que l'index simple ne la listait pas encore, et `uv tool install` posait
    donc la version précédente sans broncher.
    """
    index = _index_simple()
    if index is None:
        r.note(
            "Index PyPI injoignable",
            "Contrôle sauté. Vérifie à la main : "
            "curl -s https://pypi.org/simple/dsoxlab/ | grep " + version,
        )
        return

    if f"dsoxlab-{version}" in index:
        r.ok(f"La version {version} est servie par l'index PyPI")
        return

    # L'API JSON répond-elle déjà ? La distinction dit s'il faut attendre ou
    # s'inquiéter : connue de l'API mais absente de l'index, c'est la
    # propagation ; inconnue des deux, l'upload n'a pas eu lieu.
    try:
        with urllib.request.urlopen(
            f"https://pypi.org/pypi/dsoxlab/{version}/json", timeout=10
        ) as reponse:
            connue = reponse.status == 200
    except (urllib.error.URLError, OSError):
        connue = False

    if connue:
        r.attendre(
            f"La version {version} est publiée mais pas encore servie",
            "L'index simple n'a pas fini de propager. Attends une minute puis "
            "relance. N'annonce pas la publication tant que ce contrôle est "
            "orange : un utilisateur qui installe maintenant aura la version "
            "précédente.",
        )
    else:
        r.ko(
            f"La version {version} est absente de PyPI",
            "Le workflow Release a-t-il vraiment publié ? Regarde le job "
            "« Publish to PyPI » : un job vert peut avoir sauté l'upload.",
        )


def _verifier_release_github(r: Rapport, tag: str) -> None:
    """La Release GitHub porte les artefacts et la provenance."""
    # check=False : « aucune Release pour ce tag » se dit par un code retour,
    # et c'est précisément le constat que ce contrôle doit rapporter.
    sortie = subprocess.run(
        ["gh", "release", "view", tag, "--json", "tagName,assets"],
        cwd=RACINE, capture_output=True, text=True, check=False,
    )
    if sortie.returncode != 0:
        r.ko(
            f"Aucune Release GitHub pour {tag}",
            "Le workflow Release ne part que sur push de tag. Vérifie qu'il a "
            "tourné : gh run list --workflow Release",
        )
        return
    try:
        assets = json.loads(sortie.stdout).get("assets", [])
    except ValueError:
        r.note("Release GitHub illisible", "Vérifie à la main.")
        return
    noms = [a.get("name", "") for a in assets]
    manquants = [
        quoi for quoi, motif in (
            ("le wheel", ".whl"),
            ("la tarball", ".tar.gz"),
            ("la provenance", "intoto"),
        )
        if not any(motif in n for n in noms)
    ]
    if manquants:
        r.ko(
            f"Release {tag} incomplète : il manque {', '.join(manquants)}",
            f"Artefacts présents : {', '.join(noms) or 'aucun'}",
        )
    else:
        r.ok(f"Release GitHub {tag} complète", f"({len(noms)} artefacts)")


def _verifier_tag_pousse(r: Rapport, tag: str) -> None:
    sortie = git("ls-remote", "--tags", "origin", f"refs/tags/{tag}")
    if tag in sortie:
        r.ok(f"Le tag {tag} est sur origin")
    else:
        r.ko(
            f"Le tag {tag} n'est pas sur origin",
            f"git push origin {tag} : sans push, aucun workflow ne part.",
        )


def controler_publication(version: str, tag: str) -> int:
    """Le pendant d'après le tag : la release est-elle réellement livrée ?"""
    print(f"\n{GRAS}Contrôle après publication de {tag}{RAZ}\n")
    r = Rapport()
    _verifier_tag_pousse(r, tag)
    _verifier_release_github(r, tag)
    _verifier_installable(r, version)

    print()
    if r.echecs:
        print(f"{ROUGE}{GRAS}{len(r.echecs)} contrôle(s) en échec.{RAZ} "
              "La publication n'est pas terminée.\n")
        return 1
    if r.attentes:
        print(f"{JAUNE}{GRAS}Publié, mais pas encore servi.{RAZ} "
              "Relance dans une minute.\n")
        return 2
    print(f"{VERT}{GRAS}La version {version} est livrée.{RAZ}\n")
    print("    Pour l'installer, pense au cache : "
          "uv tool install --force --refresh dsoxlab\n")
    return 0


def main() -> int:
    version = version_empaquetee()
    if version is None:
        print(f"{ROUGE}pyproject.toml ne déclare aucune version.{RAZ}")
        return 1
    arguments = [a for a in sys.argv[1:] if a != "--publiee"]
    tag = arguments[0] if arguments else f"v{version}"

    if "--publiee" in sys.argv:
        # La version à chercher sur PyPI est celle du tag qu'on vérifie, pas
        # celle qu'on empaquette aujourd'hui. Les deux divergent dès qu'une
        # autre version a été fusionnée depuis : `--publiee v0.1.65` sur un
        # dépôt passé à 0.1.66 annonçait « la version 0.1.66 est absente de
        # PyPI », un verdict faux sur une version pourtant bien livrée. Un
        # contrôle d'après-publication qui parle d'autre chose que du tag qu'on
        # lui donne ne contrôle rien.
        publiee = arguments[0].lstrip("v") if arguments else version
        return controler_publication(publiee, tag)

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
    if r.attentes:
        print(f"{JAUNE}{GRAS}Rien n'est faux, mais il est trop tôt.{RAZ} "
              "Attends puis relance ce contrôle.\n")
        return 2
    print(f"{VERT}{GRAS}Tout est bon.{RAZ} Pose le tag :\n")
    print(f'    git tag -a {tag} -m "{tag}" && git push origin {tag}\n')
    return 0


if __name__ == "__main__":
    sys.exit(main())
