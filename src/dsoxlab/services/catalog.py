"""Découvrir, installer et retrouver les catalogues de labs.

Le moteur et les catalogues sont séparés à dessein, mais cette séparation était
entièrement à la charge de l'utilisateur : rien ne disait quels catalogues
existent, comment en installer un, ni où se placer pour l'utiliser. Il fallait
avoir lu le README, retenu une URL, et compris que la découverte se fait depuis
le répertoire courant.

Trois emplacements, et chacun pour une raison :

- le **manifeste** des catalogues connus est packagé avec l'outil, donc révisable
  en pull request (`templates/catalogues.yml`) ;
- les catalogues **installés** vivent sous ``XDG_DATA_HOME``, comme le catalogue
  de démonstration : ce sont des contenus que l'utilisateur modifie et dont il
  attend qu'ils survivent, pas des caches recalculables ;
- le catalogue **actif** est un état, donc sous ``XDG_STATE_HOME`` : le perdre ne
  coûte qu'un ``dsoxlab catalog use``, jamais du travail.

Ce module reste neutre vis-à-vis des domaines : il ne connaît que des
identifiants et des URL, tous venus du manifeste ou de la ligne de commande.
"""

from __future__ import annotations

import re
import shutil
from dataclasses import dataclass
from pathlib import Path

import yaml

from ..config import xdg_data_home, xdg_state_home
from ..i18n import _
from ..templates import catalogues_manifeste
from ..utils.shell import FAILURE_NOT_FOUND, CommandResult, run_command

#: Un identifiant de catalogue sert de nom de répertoire : on le borne pour
#: qu'il ne puisse ni remonter l'arborescence, ni porter d'espace.
_ID_VALIDE = re.compile(r"^[a-z0-9][a-z0-9._-]*$")

#: Ce qui ressemble à une URL de dépôt plutôt qu'à un identifiant du manifeste.
_URL = re.compile(r"^(https?://|git@|ssh://|git://|file://)")


class CatalogueError(RuntimeError):
    """Une opération de catalogue a échoué, avec un message déjà traduit."""


@dataclass(frozen=True)
class CatalogueConnu:
    """Une entrée du manifeste packagé."""

    id: str
    depot: str
    description_en: str = ""
    description_fr: str = ""

    def description(self, lang: str) -> str:
        return self.description_fr if lang == "fr" else self.description_en


@dataclass(frozen=True)
class CatalogueInstalle:
    """Un catalogue présent sur le disque."""

    id: str
    racine: Path
    actif: bool
    depot: str | None = None


def racine_catalogues() -> Path:
    """Où les catalogues installés vivent."""
    return xdg_data_home() / "dsoxlab" / "catalogs"


def _fichier_actif() -> Path:
    """Le fichier qui retient le catalogue actif.

    Un fichier d'une ligne plutôt qu'une entrée dans un format structuré : ce
    qu'il porte tient en un identifiant, et il doit rester lisible et
    supprimable à la main quand quelque chose va mal.
    """
    return xdg_state_home() / "dsoxlab" / "catalogue-actif"


def lire_manifeste() -> list[CatalogueConnu]:
    """Les catalogues connus, lus dans le manifeste packagé.

    Un manifeste illisible ne doit pas emporter la commande : l'utilisateur peut
    toujours installer un catalogue par son URL, et `catalog list` doit encore
    pouvoir montrer ce qui est installé.
    """
    chemin = catalogues_manifeste()
    try:
        document = yaml.safe_load(chemin.read_text(encoding="utf-8")) or {}
    except (OSError, yaml.YAMLError):
        return []
    entrees = document.get("catalogues")
    if not isinstance(entrees, list):
        return []

    connus: list[CatalogueConnu] = []
    for entree in entrees:
        if not isinstance(entree, dict):
            continue
        identifiant = entree.get("id")
        depot = entree.get("depot")
        if not isinstance(identifiant, str) or not isinstance(depot, str):
            continue
        connus.append(CatalogueConnu(
            id=identifiant,
            depot=depot,
            description_en=str(entree.get("description_en") or ""),
            description_fr=str(entree.get("description_fr") or ""),
        ))
    return connus


def _est_un_catalogue(racine: Path) -> bool:
    """Un catalogue est un répertoire qui porte un ``meta.yml``.

    Même critère que la découverte par le répertoire courant : un répertoire
    laissé par un clone interrompu n'en est pas un, et ne doit pas être proposé.
    """
    return (racine / "meta.yml").is_file()


def _git(args: list[str], *, timeout: int) -> CommandResult:
    """Appelle git, et refuse tôt s'il n'est pas là.

    `git` n'est pas une dépendance Python : il n'est ni installé par
    ``uv tool install``, ni déclaré nulle part. Sans ce point de passage, son
    absence remontait en « Commande introuvable », qui dit ce qui s'est passé
    mais pas quoi faire — sur la deuxième commande que tape un nouvel
    utilisateur.
    """
    res = run_command(["git", *args], check=False, timeout=timeout)
    if res.failure == FAILURE_NOT_FOUND:
        raise CatalogueError(_("catalog_git_absent"))
    return res


def _origine(racine: Path) -> str | None:
    """L'URL d'origine d'un catalogue cloné, si git la connaît."""
    res = _git(["-C", str(racine), "remote", "get-url", "origin"], timeout=15)
    return res.stdout.strip() if res.ok and res.stdout.strip() else None


def installes() -> list[CatalogueInstalle]:
    """Les catalogues présents sur le disque, l'actif marqué comme tel."""
    racine = racine_catalogues()
    if not racine.is_dir():
        return []
    actif = nom_actif()
    trouves: list[CatalogueInstalle] = []
    for chemin in sorted(racine.iterdir()):
        if not chemin.is_dir() or not _est_un_catalogue(chemin):
            continue
        trouves.append(CatalogueInstalle(
            id=chemin.name,
            racine=chemin,
            actif=chemin.name == actif,
            depot=_origine(chemin),
        ))
    return trouves


def nom_actif() -> str | None:
    """L'identifiant du catalogue actif, ou None.

    Un actif qui ne correspond plus à rien d'installé est traité comme absent :
    l'utilisateur a pu retirer le répertoire à la main, et une commande ne doit
    pas échouer sur un état que l'outil peut recalculer.
    """
    fichier = _fichier_actif()
    try:
        nom = fichier.read_text(encoding="utf-8").strip()
    except OSError:
        return None
    if not nom or not _ID_VALIDE.match(nom):
        return None
    return nom if _est_un_catalogue(racine_catalogues() / nom) else None


def racine_active() -> Path | None:
    """La racine du catalogue actif, si elle existe encore."""
    nom = nom_actif()
    return racine_catalogues() / nom if nom else None


def definir_actif(identifiant: str) -> Path:
    """Rend un catalogue actif. Il doit être installé."""
    racine = racine_catalogues() / identifiant
    if not _ID_VALIDE.match(identifiant) or not _est_un_catalogue(racine):
        raise CatalogueError(_("catalog_absent", name=identifiant))
    fichier = _fichier_actif()
    fichier.parent.mkdir(parents=True, exist_ok=True)
    fichier.write_text(identifiant + "\n", encoding="utf-8")
    return racine


def _oublier_actif_si(identifiant: str) -> None:
    """Retire la marque d'actif si elle désigne ce catalogue."""
    fichier = _fichier_actif()
    try:
        if fichier.read_text(encoding="utf-8").strip() == identifiant:
            fichier.unlink()
    except OSError:
        return


def _identifiant_depuis_url(url: str) -> str:
    """Déduit un identifiant du dernier segment d'une URL de dépôt."""
    segment = url.rstrip("/").rsplit("/", 1)[-1].removesuffix(".git")
    identifiant = segment.lower()
    if not _ID_VALIDE.match(identifiant):
        raise CatalogueError(_("catalog_id_invalide", name=segment))
    return identifiant


def resoudre(reference: str) -> tuple[str, str]:
    """Rend (identifiant, url) pour un nom du manifeste ou une URL brute.

    Une URL absente du manifeste est acceptée : le manifeste facilite la
    découverte, il ne restreint pas ce qu'on peut installer.
    """
    if _URL.match(reference):
        return _identifiant_depuis_url(reference), reference
    for connu in lire_manifeste():
        if connu.id == reference:
            return connu.id, connu.depot
    raise CatalogueError(_("catalog_inconnu", name=reference))


def ajouter(reference: str, *, force: bool = False) -> CatalogueInstalle:
    """Installe un catalogue par clone, et le rend actif.

    Le rendre actif est le geste qui évite d'avoir à se placer dans son
    répertoire ensuite : sans lui, l'installation ne changerait rien à ce que
    l'utilisateur doit savoir.
    """
    identifiant, url = resoudre(reference)
    destination = racine_catalogues() / identifiant

    if destination.exists():
        if not force:
            # Ne pas écraser : ce répertoire porte la progression et le travail.
            raise CatalogueError(_("catalog_deja_installe",
                                   name=identifiant, path=str(destination)))
        shutil.rmtree(destination)

    destination.parent.mkdir(parents=True, exist_ok=True)
    res = _git(["clone", "--depth", "1", url, str(destination)], timeout=900)
    if not res.ok:
        # Un clone à moitié fait laisserait un répertoire qui n'est pas un
        # catalogue, que `list` montrerait comme installé.
        shutil.rmtree(destination, ignore_errors=True)
        raise CatalogueError(_("catalog_clone_echec",
                               url=url, detail=res.stderr.strip()))

    if not _est_un_catalogue(destination):
        shutil.rmtree(destination, ignore_errors=True)
        raise CatalogueError(_("catalog_sans_meta", url=url))

    definir_actif(identifiant)
    return CatalogueInstalle(id=identifiant, racine=destination,
                             actif=True, depot=url)


def mettre_a_jour(identifiant: str) -> str:
    """Met un catalogue à jour, et rend ce que git a fait."""
    racine = racine_catalogues() / identifiant
    if not _ID_VALIDE.match(identifiant) or not _est_un_catalogue(racine):
        raise CatalogueError(_("catalog_absent", name=identifiant))

    res = _git(["-C", str(racine), "pull", "--ff-only"], timeout=600)
    if not res.ok:
        raise CatalogueError(_("catalog_update_echec",
                               name=identifiant,
                               detail=(res.stderr or res.stdout).strip()))
    return res.stdout.strip()


def retirer(identifiant: str) -> Path:
    """Retire un catalogue du disque."""
    racine = racine_catalogues() / identifiant
    if not _ID_VALIDE.match(identifiant) or not racine.is_dir():
        raise CatalogueError(_("catalog_absent", name=identifiant))
    shutil.rmtree(racine)
    _oublier_actif_si(identifiant)
    return racine
