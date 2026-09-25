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

**Le rapport rendu s'écrit en anglais, quelle que soit ``DSOXLAB_LANG``**
(0.1.98, issue #227). Il ne passe donc par ``_()`` nulle part, et
``tests/test_support_en_anglais.py`` tient la règle. C'est exactement le
raisonnement qui a mis le journal en anglais en 0.1.83, avec une condition de
plus : ce rapport est **publié**. Il se cherche mot pour mot, se compare entre
deux machines aux locales différentes, transporte déjà un journal anglais, et
depuis la 0.1.86 ``--issue`` le dépose dans un formulaire dont tous les libellés
sont anglais. Une session ``DSOXLAB_LANG=en`` obtenait un rapport français : la
cohérence de la 0.1.83 s'arrêtait au milieu du fichier.

Deux choses restent séparées, et c'est tout l'enjeu de la correction :

- **les clés du document** rendu par :func:`collecter`, qui sont la sortie de
  ``support --json``, donc un contrat pour les programmes. Elles sont françaises
  (``systeme``, ``labs_decouverts``…) et le **restent** : les renommer casserait
  un contrat sans rapport avec le problème ;
- **les libellés du rendu Markdown**, qui sont anglais, par la table
  :data:`_LIBELLES` ci-dessous.
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
        return "present, version unreadable"
    sortie = (proc.stdout or "") + (proc.stderr or "")
    lignes = [ligne.strip() for ligne in sortie.splitlines() if ligne.strip()]
    return lignes[0][:120] if lignes else "present, version unreadable"


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
        "shell": Path(os.environ.get("SHELL", "")).name or "unknown",
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
            # La version du provider Terraform en place, et non la contrainte du
            # template : deux postes qui honorent « ~> 0.9 » peuvent avoir des
            # versions différentes, et c'est celle-là qui décide. Comprendre
            # l'issue #234 a demandé de la chercher à la main, faute que ce
            # rapport la porte.
            from ..infra.terraform import providers_epingles
            epingles = providers_epingles(meta)
            catalogue["providers_terraform"] = (
                ", ".join(f"{nom} {v}" for nom, v in sorted(epingles.items())) or None
            )
            catalogue["hotes_declares"] = len(meta.infra.hosts)
        labs = get_all_labs(racine)
        catalogue["labs_decouverts"] = len(labs)
        catalogue["labs_vm"] = sum(
            1 for lab in labs if lab.runtime.type.value in ("vm", "kvm", "incus")
        )
        # Le runtime du lab actif, et non celui du dépôt : un dépôt mixte porte
        # les deux, et c'est bien le lab en cours qui explique la panne. Rendu
        # sous la valeur du contrat (`vm`), jamais sous ses alias historiques
        # `kvm`/`incus`, qui désignent un provider et non un runtime.
        actif = next((lab for lab in labs if lab.id == contexte.active_lab), None)
        if actif is not None:
            brut = actif.runtime.type.value
            catalogue["runtime_lab_actif"] = "vm" if brut in ("vm", "kvm", "incus") else brut
    except Exception as exc:  # noqa: BLE001 : un rapport partiel vaut mieux que rien
        catalogue["erreur"] = anonymiser(f"{type(exc).__name__}: {exc}")
    rapport["catalogue"] = catalogue

    rapport["etat"] = {
        "xdg_state": anonymiser(str(xdg_state_home() / "dsoxlab")),
        "journal": anonymiser(str(chemin_journal())),
    }
    rapport["journal"] = [anonymiser(ligne) for ligne in dernieres_lignes(lignes_journal)]
    return rapport


#: Libellé anglais de chaque clé du document, pour le **rendu** seul.
#:
#: Les clés, elles, ne bougent pas : ce sont celles de ``support --json``, un
#: contrat documenté dans ``docs/machine-output.*``. Renommer ``systeme`` en
#: ``system`` pour corriger un affichage casserait un consommateur sans aucun
#: rapport avec le défaut qu'on répare (issue #227).
#:
#: Une clé absente de cette table est rendue telle quelle. C'est voulu : les
#: noms d'outils (``terraform``, ``virsh``…) viennent du système et n'ont pas à
#: être traduits, et un champ nouveau vaut mieux affiché brut que caché.
_LIBELLES: dict[str, str] = {
    # Environnement
    "systeme": "system",
    "distribution": "distribution",
    "architecture": "architecture",
    # Catalogue
    "racine": "root",
    "section_active": "active_section",
    "lab_actif": "active_lab",
    "categorie": "category",
    "provider_actif": "active_provider",
    "providers_declares": "declared_providers",
    "providers_terraform": "terraform_providers",
    "hotes_declares": "declared_hosts",
    "labs_decouverts": "labs_discovered",
    "labs_vm": "vm_labs",
    "labs_services": "labs_with_services",
    "erreur": "error",
    # Emplacements
    "journal": "log",
}

#: Ce qu'une valeur absente écrit dans le rendu. ``collecter`` met ``None`` dans
#: le document, qui devient ``null`` en JSON : c'est ici, et ici seulement, qu'un
#: mot est nécessaire.
_RIEN = "none"


def _tableau(titre: str, valeurs: dict[str, Any]) -> list[str]:
    lignes = [f"### {titre}", "", "| | |", "|---|---|"]
    for cle, valeur in valeurs.items():
        rendu = _RIEN if valeur is None else valeur
        if isinstance(rendu, list):
            rendu = ", ".join(str(x) for x in rendu) or _RIEN
        lignes.append(f"| {_LIBELLES.get(cle, cle)} | {rendu} |")
    lignes.append("")
    return lignes


def en_markdown(rapport: dict[str, Any]) -> str:
    """Le rapport prêt à coller dans une issue, sans retouche, **en anglais**.

    Aucun appel à ``_()`` ici, et c'est délibéré : voir l'en-tête du module. Ce
    texte est publié, comparé entre machines et déposé dans un formulaire
    anglais ; il ne suit pas la locale de celui qui le produit.
    """
    general = {
        cle: rapport[cle]
        for cle in ("dsoxlab", "python", "systeme", "distribution",
                    "architecture", "shell")
    }
    lignes = ["## dsoxlab support", ""]
    lignes += _tableau("Environment", general)
    lignes += _tableau("External tools", rapport["outils"])
    lignes += _tableau("Catalog", rapport["catalogue"])
    lignes += _tableau("Locations", rapport["etat"])

    journal = rapport.get("journal") or []
    lignes += ["### Last log lines", ""]
    if journal:
        lignes += ["```", *journal, "```", ""]
    else:
        lignes += ["_No log entry recorded._", ""]
    return "\n".join(lignes)
