"""Ouvrir une issue depuis la CLI, dans le dépôt qui doit la recevoir.

``dsoxlab support`` s'arrêtait à un pas du but : il produit un rapport anonymisé
« prêt à coller », puis laissait à l'apprenant le soin de trouver le dépôt, le
template et le bon champ. Ce module fait ce dernier pas, et répond pour cela à
deux questions, à elles seules.

**Quel dépôt ?** Un énoncé faux, un test qui ne prouve pas l'état du système,
une ``doc_url`` morte sont des défauts de *catalogue*, pas du moteur. Ils
atterrissaient sur le dépôt de l'outil faute de savoir où aller, et il fallait
ensuite les transférer à la main. La CLI est la seule à pouvoir trancher sans se
tromper : elle sait quel dépôt de labs est ouvert.

**Sous quelle forme ?** Le dépôt du moteur porte un *formulaire* d'issue
(``bug_report.yml``). Un formulaire ignore ``body=`` : il se remplit par
identifiant de champ. Les trois catalogues, eux, n'en portent aucun et acceptent
une issue vierge. La forme est donc **détectée sur le disque**, jamais supposée :
le jour où un catalogue ajoute un formulaire, cette commande s'y plie sans qu'on
la retouche.

Aucune URL de catalogue n'est écrite ici, et il ne faut jamais en écrire une :
elle vient de ``meta.yml: repo.issues_url``, ou à défaut du remote git du dépôt
ouvert. Le moteur, lui, lit la sienne dans les métadonnées de son propre paquet.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from enum import Enum
from importlib import metadata
from pathlib import Path
from typing import TYPE_CHECKING, Any
from urllib.parse import urlencode, urlsplit, urlunsplit

import yaml

from ..utils.shell import run_command

if TYPE_CHECKING:  # pragma: no cover - import de typage seulement
    from ..models import RepoMetadata

logger = logging.getLogger(__name__)

#: Longueur au-delà de laquelle on ne tente plus d'ouvrir l'URL pré-remplie.
#:
#: Le corps d'une issue accepte 65 536 caractères par l'API, mais l'URL casse
#: très loin en dessous : le percent-encoding triple chaque octet, et le serveur
#: rend un **414 Request-URI too large** sans rien ouvrir. C'est le défaut
#: rencontré par ``gh --web`` (cli/cli#1575). 8 000 laisse la marge sous la
#: limite habituelle des serveurs (8 Ko) sans avoir à la mesurer chez GitHub.
LIMITE_URL = 8000

#: Le formulaire de bug du dépôt du moteur, et les champs que l'on sait y
#: remplir. Ces valeurs décrivent notre propre ``.github/ISSUE_TEMPLATE/`` : les
#: coder ici n'est pas une entorse à l'agnosticisme, c'est la configuration de ce
#: dépôt-ci. Rien de ce qui touche un catalogue n'est écrit en dur.
TEMPLATE_MOTEUR = "bug_report.yml"

#: Les identifiants de champ que la CLI sait alimenter. Un formulaire qui n'en
#: déclare aucun reçoit ``template=`` et rien d'autre : on ne devine pas le sens
#: d'un champ d'après son libellé. Un catalogue qui veut le pré-remplissage
#: nomme ses champs comme ceux-ci, et c'est une convention explicite, pas une
#: heuristique.
#:
#: ``lab`` n'a de sens que pour un catalogue, dont les issues portent sur un lab
#: précis ; le formulaire du moteur ne le déclare pas, et l'intersection avec les
#: champs réellement déclarés suffit à l'écarter.
CHAMPS_CONNUS = frozenset({"support", "os", "runtime", "reproduce", "lab"})

#: Ce que déclare précisément ``bug_report.yml`` de ce dépôt-ci. On ne peut pas
#: le lire à l'exécution — le dépôt du moteur n'est pas sur le disque de
#: l'apprenant, seul son paquet l'est — donc on l'écrit, et un test le confronte
#: au fichier réel plutôt que de faire confiance à cette ligne.
CHAMPS_MOTEUR = frozenset({"support", "os", "runtime", "reproduce"})

_TEMPLATES = ("*.yml", "*.yaml")

#: Un remote SSH de la forme ``git@hôte:propriétaire/dépôt.git``. Cette écriture
#: n'est pas une URL et ``urlsplit`` n'en tire rien d'exploitable.
_REMOTE_SCP = re.compile(r"^(?:[^@/]+@)?(?P<hote>[^:/]+):(?P<chemin>.+)$")


class Cible(Enum):
    """Le dépôt qui reçoit l'issue."""

    MOTEUR = "moteur"
    CATALOGUE = "catalogue"

    @property
    def cle_i18n(self) -> str:
        """La clé qui nomme cette cible à l'écran.

        Assemblée, donc invisible au garde-fou qui relève les ``_("…")``
        littéraux. C'est un test qui la confronte aux deux catalogues de
        traduction, et il le fait pour **tous** les membres : une valeur ajoutée
        ici sans sa phrase fait échouer la suite, ce qu'une table écrite à la
        main ne garantirait pas.
        """
        return f"issue_cible_{self.value}"


class Origine(Enum):
    """D'où vient l'URL retenue. Sert à le dire, jamais à décider."""

    PAQUET = "paquet"
    """Métadonnées du paquet dsoxlab (``[project.urls] Issues``)."""

    CONTRAT = "contrat"
    """``meta.yml: repo.issues_url``, déclaré par le catalogue."""

    REMOTE = "remote"
    """``git remote get-url origin`` du dépôt de labs ouvert."""

    @property
    def cle_i18n(self) -> str:
        """La clé qui nomme cette origine. Même garantie que :attr:`Cible.cle_i18n`."""
        return f"issue_origine_{self.value}"


class Repli(Enum):
    """Ce qu'il a fallu retirer pour que l'URL passe."""

    COMPLET = "complet"
    """Rien : le rapport entier tient dans l'URL."""

    SANS_JOURNAL = "sans_journal"
    """Le rapport tient une fois ses lignes de journal retirées."""

    VIDE = "vide"
    """Même sans journal c'est trop long : le formulaire s'ouvre nu."""


@dataclass(frozen=True)
class Destination:
    """Le dépôt visé, et la forme d'issue qu'il accepte."""

    cible: Cible
    url_issues: str
    """Racine des issues, sans barre finale — ex. ``https://…/dsoxlab/issues``."""

    libelle: str
    """Ce qu'on montre à l'apprenant avant de lui demander — ``owner/repo``."""

    origine: Origine
    template: str | None = None
    """Nom du formulaire à demander, ou ``None`` pour une issue vierge."""

    champs: frozenset[str] = frozenset()
    """Identifiants que ce formulaire déclare et que l'on sait remplir."""


@dataclass(frozen=True)
class Lien:
    """L'URL à ouvrir, et ce qu'il a fallu sacrifier pour l'obtenir."""

    url: str
    repli: Repli


def _sans_identifiants(url: str) -> str:
    """Retire le ``user:token@`` d'une URL de remote.

    Un remote cloné avec un jeton le porte en clair. Cette URL est affichée,
    puis ouverte dans un navigateur : la recopier telle quelle publierait le
    jeton à l'écran et dans l'historique.
    """
    parts = urlsplit(url)
    if "@" not in parts.netloc:
        return url
    hote = parts.netloc.rsplit("@", 1)[1]
    return urlunsplit(parts._replace(netloc=hote))


def _normaliser_remote(brut: str) -> tuple[str, str] | None:
    """``(url https du dépôt, libellé owner/repo)``, ou ``None`` si illisible.

    Accepte les trois écritures qu'un clone produit : ``https://``,
    ``ssh://git@…`` et la forme courte ``git@hôte:owner/repo.git``.
    """
    brut = brut.strip()
    if not brut:
        return None

    if "://" in brut:
        parts = urlsplit(_sans_identifiants(brut))
        hote, chemin = parts.netloc, parts.path
    else:
        correspondance = _REMOTE_SCP.match(brut)
        if correspondance is None:
            return None
        hote = correspondance.group("hote")
        chemin = correspondance.group("chemin")

    chemin = chemin.strip("/").removesuffix(".git")
    if not hote or not chemin:
        return None
    return f"https://{hote}/{chemin}", chemin


def _url_issues_depuis_remote(racine: Path) -> tuple[str, str] | None:
    """L'URL d'issues déduite du remote ``origin`` du dépôt de labs.

    C'est le repli, pas le contrat : il suppose un remote nommé ``origin`` et un
    hébergeur dont les issues vivent sous ``<dépôt>/issues``. Un catalogue qui
    veut être sûr déclare ``repo.issues_url``.
    """
    resultat = run_command(
        ["git", "-C", str(racine), "remote", "get-url", "origin"],
        check=False,
        timeout=10,
    )
    if not resultat.ok:
        return None
    normalise = _normaliser_remote(resultat.stdout)
    if normalise is None:
        return None
    url, libelle = normalise
    return f"{url}/issues", libelle


def _url_issues_moteur() -> tuple[str, str] | None:
    """L'URL d'issues du moteur, lue dans les métadonnées de son paquet.

    ``[project.urls] Issues`` de ``pyproject.toml`` arrive ici en ``Project-URL``.
    On la lit plutôt que de l'écrire deux fois : une adresse recopiée finit par
    diverger de celle que PyPI publie.
    """
    try:
        infos = metadata.metadata("dsoxlab")
    except metadata.PackageNotFoundError:
        return None

    urls: dict[str, str] = {}
    for entree in infos.get_all("Project-URL") or []:
        nom, _, valeur = str(entree).partition(",")
        urls[nom.strip().lower()] = valeur.strip()

    brut = urls.get("issues") or ""
    if not brut:
        depot = urls.get("repository") or ""
        brut = f"{depot.rstrip('/')}/issues" if depot else ""
    if not brut:
        return None

    normalise = _normaliser_remote(brut.removesuffix("/issues"))
    libelle = normalise[1] if normalise else "dsoxlab"
    return brut.rstrip("/"), libelle


def _ids_formulaire(chemin: Path) -> frozenset[str]:
    """Les identifiants de champ déclarés par un formulaire, jamais une levée.

    Un formulaire illisible n'est pas une erreur ici : il ramène simplement la
    commande à l'issue vierge, qui marche partout.
    """
    try:
        with chemin.open(encoding="utf-8") as fh:
            donnees = yaml.safe_load(fh) or {}
    except (OSError, yaml.YAMLError) as exc:
        logger.warning("unreadable issue form %s: %s", chemin.name, exc)
        return frozenset()

    if not isinstance(donnees, dict):
        return frozenset()
    corps = donnees.get("body")
    if not isinstance(corps, list):
        return frozenset()

    ids: set[str] = set()
    for champ in corps:
        if isinstance(champ, dict) and isinstance(champ.get("id"), str):
            ids.add(champ["id"])
    return frozenset(ids)


def _formulaire_local(racine: Path) -> tuple[str, frozenset[str]] | None:
    """Le formulaire de bug d'un dépôt cloné, s'il en porte un.

    On préfère celui dont le nom parle de bug, puis le premier par ordre
    alphabétique : un dépôt qui déclare aussi ``feature_request.yml`` ne doit
    pas voir un rapport de diagnostic atterrir dans une demande de
    fonctionnalité. ``config.yml`` n'est pas un formulaire.
    """
    dossier = racine / ".github" / "ISSUE_TEMPLATE"
    if not dossier.is_dir():
        return None

    fichiers = sorted(
        (f for motif in _TEMPLATES for f in dossier.glob(motif) if f.name != "config.yml"),
        key=lambda f: (0 if "bug" in f.name.lower() else 1, f.name),
    )
    for fichier in fichiers:
        ids = _ids_formulaire(fichier)
        if ids:
            return fichier.name, ids & CHAMPS_CONNUS
    return None


def resoudre_destination(
    racine: Path,
    repo_meta: RepoMetadata | None,
    *,
    cible: Cible,
) -> Destination | None:
    """Le dépôt visé et sa forme d'issue, ou ``None`` si aucune URL n'est connue.

    Rendre ``None`` n'est pas un défaut du catalogue : un dépôt de labs peut très
    bien n'avoir ni ``repo.issues_url`` ni remote. C'est à l'appelant de le dire
    et de proposer autre chose, pas à ce module de lever.
    """
    if cible is Cible.MOTEUR:
        trouve = _url_issues_moteur()
        if trouve is None:
            return None
        url, libelle = trouve
        return Destination(
            cible=Cible.MOTEUR,
            url_issues=url,
            libelle=libelle,
            origine=Origine.PAQUET,
            template=TEMPLATE_MOTEUR,
            champs=CHAMPS_MOTEUR,
        )

    declaree = (repo_meta.issues_url if repo_meta is not None else "").strip()
    if declaree:
        normalise = _normaliser_remote(declaree.removesuffix("/issues"))
        url = declaree.rstrip("/")
        libelle = normalise[1] if normalise else url
        origine = Origine.CONTRAT
    else:
        trouve = _url_issues_depuis_remote(racine)
        if trouve is None:
            return None
        url, libelle = trouve
        origine = Origine.REMOTE

    formulaire = _formulaire_local(racine)
    return Destination(
        cible=Cible.CATALOGUE,
        url_issues=url,
        libelle=libelle,
        origine=origine,
        template=formulaire[0] if formulaire else None,
        champs=formulaire[1] if formulaire else frozenset(),
    )


def _corps_libre(contexte: dict[str, str], rapport: str) -> str:
    """Le Markdown d'une issue vierge, pour un dépôt sans formulaire.

    Les libellés sont les identifiants de champ eux-mêmes, et c'est délibéré :
    ce sont ceux qu'un formulaire porterait, ils sont neutres en langue, et
    l'apprenant qui ouvre ensuite une issue sur le dépôt du moteur y retrouve
    les mêmes mots. Une valeur qui tient sur plusieurs lignes prend un titre
    plutôt qu'un préfixe, sans quoi un canevas d'étapes flotte sans rien qui le
    nomme.
    """
    morceaux: list[str] = []
    for cle in ("lab", "reproduce", "os", "runtime"):
        valeur = contexte.get(cle, "").strip()
        if not valeur:
            continue
        morceaux.append(f"### {cle}\n\n{valeur}" if "\n" in valeur else f"**{cle}**: {valeur}")
    if rapport:
        morceaux.append(rapport)
    return "\n\n".join(morceaux)


def _parametres(
    destination: Destination,
    *,
    titre: str,
    contexte: dict[str, str],
    rapport: str,
) -> dict[str, str]:
    params: dict[str, str] = {}
    if titre:
        params["title"] = titre

    if destination.template is None:
        params["body"] = _corps_libre(contexte, rapport)
        return params

    params["template"] = destination.template
    for cle, valeur in contexte.items():
        if valeur and cle in destination.champs:
            params[cle] = valeur
    if rapport and "support" in destination.champs:
        params["support"] = rapport
    return params


def construire_lien(
    destination: Destination,
    *,
    titre: str = "",
    contexte: dict[str, str] | None = None,
    rapport: str,
    rapport_court: str = "",
) -> Lien:
    """L'URL d'ouverture d'issue, réduite jusqu'à ce qu'elle tienne.

    Trois tentatives, dans cet ordre : le rapport entier, le rapport sans ses
    lignes de journal, puis le formulaire nu. On ne tente pas la plus longue en
    espérant : une URL trop longue ne s'ouvre pas, elle rend un 414, et
    l'apprenant perd à la fois son rapport et sa patience.
    """
    contexte = contexte or {}
    base = destination.url_issues.rstrip("/") + "/new"

    candidats = (
        (rapport, Repli.COMPLET),
        (rapport_court, Repli.SANS_JOURNAL),
        ("", Repli.VIDE),
    )
    url = base
    repli = Repli.VIDE
    for corps, essai in candidats:
        if essai is Repli.SANS_JOURNAL and (not corps or corps == rapport):
            continue
        params = _parametres(
            destination, titre=titre, contexte=contexte, rapport=corps
        )
        url = f"{base}?{urlencode(params)}" if params else base
        repli = essai
        if len(url) <= LIMITE_URL:
            return Lien(url=url, repli=essai)

    return Lien(url=url, repli=repli)


def rapport_sans_journal(rapport: dict[str, Any]) -> dict[str, Any]:
    """Le même rapport, ses lignes de journal en moins.

    Recollecter coûterait une nouvelle série d'appels à ``--version`` alors
    qu'on cherche seulement à raccourcir une URL.
    """
    return {**rapport, "journal": []}
