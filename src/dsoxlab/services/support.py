"""Le rapport de diagnostic à coller dans une issue.

Quand quelqu'un écrit « ça ne marche pas », il faut lui redemander sa version,
son système, son provider, son catalogue, l'état de ses dépendances. Chaque
aller-retour coûte une journée, et l'outil connaît déjà toutes ces réponses.

**Ce rapport est destiné à être collé publiquement.** L'anonymisation n'est donc
pas une option de confort : elle est appliquée par défaut et testée. Un chemin
absolu suffit à publier le nom de famille de quelqu'un, un nom d'hôte à
identifier une machine d'entreprise.

Ce qui n'est PAS anonymisé, et pourquoi : les adresses privées (10.x, 192.168.x,
172.16-31.x) restent lisibles. Ce sont celles des VM de lab, elles ne désignent
personne hors du réseau local, et les masquer rendrait inexploitable tout
rapport portant sur l'infrastructure, c'est-à-dire la moitié d'entre eux.
"""

from __future__ import annotations

import getpass
import ipaddress
import os
import platform
import re
import shutil
import subprocess
from pathlib import Path
from typing import Any

from .. import __version__
from ..config import get_lab_home, read_context, xdg_state_home
from ..discovery.repo import read_repo_metadata
from ..logging_setup import chemin_journal, dernieres_lignes
from .lab_service import get_all_labs

#: Outils externes dont la présence et la version changent le diagnostic.
#: L'ordre est celui du parcours : provisionner, configurer, se connecter.
_OUTILS = (
    ("terraform", ("terraform", "version")),
    ("ansible-playbook", ("ansible-playbook", "--version")),
    ("virsh", ("virsh", "--version")),
    ("incus", ("incus", "--version")),
    ("docker", ("docker", "--version")),
    ("ssh", ("ssh", "-V")),
    ("git", ("git", "--version")),
    ("uv", ("uv", "--version")),
)

_IPV4 = re.compile(r"\b(?:\d{1,3}\.){3}\d{1,3}\b")


def _est_privee(brut: str) -> bool:
    try:
        adresse = ipaddress.ip_address(brut)
    except ValueError:
        return False
    return adresse.is_private or adresse.is_loopback or adresse.is_link_local


def anonymiser(texte: str) -> str:
    """Retire d'un texte ce qui désigne une personne ou une machine.

    Trois substitutions, dans cet ordre : le répertoire personnel devient ``~``,
    le nom d'utilisateur devient ``<user>``, et toute adresse IPv4 **publique**
    devient ``<ip>``. Le nom d'hôte est traité par l'appelant, qui ne le collecte
    tout simplement pas.
    """
    if not texte:
        return texte

    maison = str(Path.home())
    if maison and maison != "/":
        texte = texte.replace(maison, "~")

    try:
        utilisateur = getpass.getuser()
    except (KeyError, OSError):
        utilisateur = ""
    if utilisateur and len(utilisateur) > 2:
        # Un nom très court produirait des remplacements au milieu de mots
        # ordinaires, et rendrait le rapport illisible sans rien protéger.
        texte = re.sub(rf"\b{re.escape(utilisateur)}\b", "<user>", texte)

    return _IPV4.sub(
        lambda m: m.group(0) if _est_privee(m.group(0)) else "<ip>", texte
    )


def _version_outil(commande: tuple[str, ...]) -> str | None:
    """Première ligne utile de la sortie de version, ou None si absent.

    ``ssh -V`` écrit sur stderr, ``docker --version`` sur stdout : on lit les
    deux plutôt que de tenir une table des exceptions.
    """
    if shutil.which(commande[0]) is None:
        return None
    try:
        proc = subprocess.run(
            list(commande), capture_output=True, text=True, timeout=5, check=False
        )
    except (OSError, subprocess.SubprocessError):
        return "présent, version illisible"
    sortie = (proc.stdout or "") + (proc.stderr or "")
    lignes = [ligne.strip() for ligne in sortie.splitlines() if ligne.strip()]
    return lignes[0][:120] if lignes else "présent, version illisible"


def _distribution() -> str:
    """La distribution, lue dans os-release. Le nom d'hôte n'y figure pas."""
    try:
        contenu = Path("/etc/os-release").read_text(encoding="utf-8")
    except OSError:
        return platform.platform(terse=True)
    for ligne in contenu.splitlines():
        if ligne.startswith("PRETTY_NAME="):
            return ligne.split("=", 1)[1].strip().strip('"')
    return platform.platform(terse=True)


def collecter(*, lignes_journal: int = 30) -> dict[str, Any]:
    """Rassemble le rapport. Aucune section ne peut faire échouer les autres.

    Un diagnostic qui lève en cherchant à diagnostiquer est le pire des cas :
    il survient justement quand l'environnement est cassé, c'est-à-dire quand
    on en a le plus besoin.
    """
    rapport: dict[str, Any] = {
        "dsoxlab": __version__,
        "python": f"{platform.python_version()} ({platform.python_implementation()})",
        "systeme": f"{platform.system()} {platform.release()}",
        "distribution": _distribution(),
        "architecture": platform.machine(),
        "shell": Path(os.environ.get("SHELL", "")).name or "inconnu",
    }

    rapport["outils"] = {
        nom: _version_outil(cmd) or "absent" for nom, cmd in _OUTILS
    }

    catalogue: dict[str, Any] = {}
    try:
        racine = get_lab_home()
        catalogue["racine"] = anonymiser(str(racine))
        contexte = read_context(racine)
        catalogue["section_active"] = contexte.section
        catalogue["lab_actif"] = contexte.active_lab
        meta = read_repo_metadata(racine)
        if meta is not None:
            catalogue["id"] = meta.id
            catalogue["categorie"] = meta.category
            catalogue["provider_actif"] = meta.infra.provider or None
            catalogue["providers_declares"] = list(meta.infra.providers_available)
            catalogue["hotes_declares"] = len(meta.infra.hosts)
        labs = get_all_labs(racine)
        catalogue["labs_decouverts"] = len(labs)
        catalogue["labs_vm"] = sum(
            1 for lab in labs if lab.runtime.type.value in ("vm", "kvm", "incus")
        )
    except Exception as exc:  # noqa: BLE001 : un rapport partiel vaut mieux que rien
        catalogue["erreur"] = anonymiser(f"{type(exc).__name__}: {exc}")
    rapport["catalogue"] = catalogue

    rapport["etat"] = {
        "xdg_state": anonymiser(str(xdg_state_home() / "dsoxlab")),
        "journal": anonymiser(str(chemin_journal())),
    }
    rapport["journal"] = [anonymiser(ligne) for ligne in dernieres_lignes(lignes_journal)]
    return rapport


def _tableau(titre: str, valeurs: dict[str, Any]) -> list[str]:
    lignes = [f"### {titre}", "", "| | |", "|---|---|"]
    for cle, valeur in valeurs.items():
        rendu = "aucun" if valeur is None else valeur
        if isinstance(rendu, list):
            rendu = ", ".join(str(x) for x in rendu) or "aucun"
        lignes.append(f"| {cle} | {rendu} |")
    lignes.append("")
    return lignes


def en_markdown(rapport: dict[str, Any]) -> str:
    """Le rapport prêt à coller dans une issue, sans retouche."""
    general = {
        cle: rapport[cle]
        for cle in ("dsoxlab", "python", "systeme", "distribution",
                    "architecture", "shell")
    }
    lignes = ["## dsoxlab support", ""]
    lignes += _tableau("Environnement", general)
    lignes += _tableau("Outils externes", rapport["outils"])
    lignes += _tableau("Catalogue", rapport["catalogue"])
    lignes += _tableau("Emplacements", rapport["etat"])

    journal = rapport.get("journal") or []
    lignes += ["### Dernières lignes du journal", ""]
    if journal:
        lignes += ["```", *journal, "```", ""]
    else:
        lignes += ["_Aucune trace enregistrée._", ""]
    return "\n".join(lignes)
