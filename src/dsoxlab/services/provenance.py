"""D'où vient une machine : le catalogue qui l'a provisionnée, et son répertoire.

Le problème, tel qu'il se pose
------------------------------

Les ressources d'un `provision` vivent longtemps, et bien plus longtemps que la
session qui les a créées. Devant un `virsh list --all` qui rend `pve.lab` et
`d29-debian.lab`, rien ne permettait de retrouver **le répertoire du catalogue
depuis lequel l'infrastructure a été montée** (issue #345) :

- le répertoire d'état ``~/.local/state/dsoxlab/<repo-id>/terraform/<provider>/``
  donne le ``repo.id``, jamais le chemin du clone ;
- ``catalogue-actif`` est un pointeur **mutable** : il dit ce qui est actif
  maintenant, et c'est une preuve d'origine qui n'en est pas une ;
- le nom du volume QCOW2 ne porte pas davantage le chemin.

Deux endroits, et c'est voulu
-----------------------------

1. **Un index local**, un fichier par dépôt :
   ``~/.local/state/dsoxlab/<repo-id>/provenance.json``, schéma versionné,
   écriture atomique. Un fichier par dépôt, et non un index global, parce que le
   verrou d'écriture de dsoxlab est **par dépôt** : un index unique serait écrit
   par deux provisions concurrentes que rien ne sérialise.
2. **Les métadonnées de la ressource elle-même**, quand le provider le permet.
   C'est ce qui répond encore quand l'index a disparu, et c'est le seul des deux
   qui voyage avec la machine.

Ce que les providers permettent, MESURÉ le 2026-11-09
-----------------------------------------------------

Terraform 1.16.1, sur la machine de référence :

- ``dmacvicar/libvirt`` **0.9.7** : ``libvirt_domain.metadata = { xml }`` prend
  du XML brut bien formé et le pose dans ``<metadata>`` du domaine. Vérifié par
  ``virsh dumpxml``, puis relu **sans Terraform** par
  ``virsh metadata <domaine> <namespace>``. Un second ``plan`` ne rend aucun
  changement, et modifier le XML donne un **update in-place** : l'UUID du
  domaine ne bouge pas, donc une reprovision ne détruit pas la machine d'un
  apprenant. Ce dernier point n'allait pas de soi, le provider ayant déjà échoué
  sur une relecture de XML (issue #234), d'où la mesure avant d'écrire une ligne
  de template.
- ``lxc/incus`` **0.5.1**, serveur Incus **7.2** : ``config`` accepte les clés
  ``user.*``, relues par ``incus config get`` ou ``incus query``, qui rend aussi
  le projet. Le plan reste stable bien que ``config`` soit à la fois
  ``optional`` et ``computed``, et une modification est là aussi in-place.

Ce que ce module ne fait pas
----------------------------

Il ne **réécrit jamais** un chemin d'origine. Un clone déplacé ou supprimé
produit un état explicite — l'origine reste ce qu'elle était au moment du
provisionnement, et c'est tout l'intérêt d'une preuve. Il n'écrit aucun secret :
les champs sont un identifiant, un chemin, un provider, un horodatage et des
identifiants de ressource.
"""

from __future__ import annotations

import json
import logging
import uuid
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal
from xml.sax.saxutils import escape as echapper_xml

from ..models import RepoMetadata
from ..utils.fichiers import ecrire_atomiquement

logger = logging.getLogger(__name__)

#: Le nom du schéma de l'index, versionné dès la première version : un document
#: dont la forme peut changer doit dire laquelle il porte, sinon le lecteur
#: suivant devine.
SCHEMA = "dsoxlab-provenance-v1"

#: Le namespace XML des métadonnées libvirt. C'est la clé que
#: ``virsh metadata <domaine> <ce namespace>`` demande, donc elle est publique
#: et ne peut plus changer sans casser les machines déjà étiquetées.
NAMESPACE_XML = "https://github.com/stephrobert/dsoxlab/provenance/v1"

#: Le préfixe des clés de configuration Incus. ``user.`` est l'espace que le
#: serveur réserve aux applications ; toute autre racine serait refusée.
PREFIXE_INCUS = "user.dsoxlab."

#: Nom du fichier d'index, sous le répertoire d'état du dépôt.
FICHIER = "provenance.json"

EtatDuChemin = Literal["present", "absent"]
Source = Literal["index", "ressource"]


@dataclass(frozen=True)
class Origine:
    """D'où vient une ressource, telle qu'elle a été consignée.

    ``catalog_path`` est le chemin **au moment du provisionnement**, résolu en
    absolu. Il n'est jamais rafraîchi : c'est une preuve, pas un pointeur.
    """

    catalog_id: str
    catalog_path: str
    provider: str
    resource: str
    provisioned_at: str
    provision_id: str
    resource_uuid: str | None = None
    project: str | None = None
    terraform_state: str | None = None
    catalog_revision: str | None = None
    #: D'où vient CETTE lecture : l'index local, ou la ressource elle-même.
    source: Source = "index"

    @property
    def chemin(self) -> Path:
        return Path(self.catalog_path)

    def etat_du_chemin(self) -> EtatDuChemin:
        """Le répertoire d'origine existe-t-il encore, maintenant ?"""
        return "present" if self.chemin.is_dir() else "absent"

    def en_json(self) -> dict[str, Any]:
        """La ligne telle que l'index la porte : sans ``source``, qui se déduit."""
        donnees = {
            "catalog_id": self.catalog_id,
            "catalog_path": self.catalog_path,
            "provider": self.provider,
            "resource": self.resource,
            "provisioned_at": self.provisioned_at,
            "provision_id": self.provision_id,
            "resource_uuid": self.resource_uuid,
            "project": self.project,
            "terraform_state": self.terraform_state,
            "catalog_revision": self.catalog_revision,
        }
        return {cle: valeur for cle, valeur in donnees.items() if valeur is not None}

    @classmethod
    def depuis_json(cls, ligne: Any, *, source: Source = "index") -> Origine | None:
        """Une ligne d'index, ou ``None`` si elle n'est pas lisible.

        Une ligne tronquée ou d'un schéma inconnu est **ignorée**, jamais
        devinée : une provenance à moitié lue serait une preuve fausse.
        """
        if not isinstance(ligne, dict):
            return None
        requis = ("catalog_id", "catalog_path", "provider", "resource")
        if any(not isinstance(ligne.get(cle), str) for cle in requis):
            return None
        facultatif: dict[str, str | None] = {}
        for cle in ("resource_uuid", "project", "terraform_state", "catalog_revision"):
            valeur = ligne.get(cle)
            facultatif[cle] = valeur if isinstance(valeur, str) else None
        return cls(
            catalog_id=str(ligne["catalog_id"]),
            catalog_path=str(ligne["catalog_path"]),
            provider=str(ligne["provider"]),
            resource=str(ligne["resource"]),
            provisioned_at=str(ligne.get("provisioned_at") or ""),
            provision_id=str(ligne.get("provision_id") or ""),
            source=source,
            **facultatif,
        )


# ── le fichier d'index ────────────────────────────────────────────────────────


def _racine_d_etat() -> Path:
    """``XDG_STATE_HOME/dsoxlab``, par la définition unique de ``config``.

    Recalculer la racine XDG ici en dupliquerait la définition, et un
    ``XDG_STATE_HOME`` personnalisé n'en déplacerait qu'une moitié : c'est
    exactement l'avertissement que porte ``config.xdg_state_home``.
    """
    from ..config import xdg_state_home

    return xdg_state_home() / "dsoxlab"


def chemin_de_l_index(repo_id: str) -> Path:
    """L'index de CE dépôt. Voisin de son state Terraform, et pour la même raison."""
    return _racine_d_etat() / repo_id / FICHIER


def lire_l_index(repo_id: str) -> list[Origine]:
    """Les origines consignées par ce dépôt, ou une liste vide.

    Un index absent n'est pas une anomalie : un dépôt sans labs `vm` n'en a
    jamais eu. Un index illisible non plus — on le dit au journal et on rend
    vide, parce qu'une commande de lecture seule ne doit pas échouer sur un
    fichier d'état qu'elle pourrait reconstruire au prochain provision.
    """
    chemin = chemin_de_l_index(repo_id)
    if not chemin.is_file():
        return []
    try:
        document = json.loads(chemin.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        logger.warning("unreadable provenance index %s: %s", chemin, exc)
        return []
    if not isinstance(document, dict) or document.get("schema") != SCHEMA:
        logger.warning("unknown provenance schema in %s", chemin)
        return []
    lignes = document.get("resources")
    if not isinstance(lignes, list):
        return []
    origines = [Origine.depuis_json(ligne) for ligne in lignes]
    return [origine for origine in origines if origine is not None]


def _ecrire_l_index(repo_id: str, origines: list[Origine]) -> Path:
    chemin = chemin_de_l_index(repo_id)
    chemin.parent.mkdir(parents=True, exist_ok=True)
    document = {
        "schema": SCHEMA,
        "catalog_id": repo_id,
        "resources": [origine.en_json() for origine in origines],
    }
    ecrire_atomiquement(chemin, json.dumps(document, indent=2) + "\n")
    return chemin


def _cle(origine: Origine) -> tuple[str, str, str]:
    """L'identité d'une ressource : provider, projet, nom.

    Le projet entre dans la clé parce qu'Incus autorise deux instances de même
    nom dans deux projets, et qu'elles ne sont pas la même machine.
    """
    return (origine.provider, origine.project or "", origine.resource)


def enregistrer(origines: list[Origine], repo_id: str) -> Path | None:
    """Consigne ces origines dans l'index du dépôt, en remplaçant les homonymes.

    Une reprovision écrase la ligne de la MÊME ressource — c'est bien la même
    machine, provisionnée de nouveau — et ne touche à aucune autre, ni d'un autre
    provider, ni d'un autre projet. Les ressources d'un autre dépôt vivent dans
    un autre fichier et ne peuvent donc pas être perdues ici.
    """
    if not origines:
        return None
    gardees = {_cle(origine): origine for origine in lire_l_index(repo_id)}
    gardees.update({_cle(origine): origine for origine in origines})
    return _ecrire_l_index(repo_id, [gardees[cle] for cle in sorted(gardees)])


def oublier(noms: list[str], repo_id: str, *, provider: str) -> None:
    """Retire de l'index les ressources effectivement détruites.

    Appelé par `destroy`, et seulement pour ce qu'il a réellement retiré : une
    machine restée debout garde sa trace, puisque c'est précisément celle qu'on
    cherchera ensuite pour savoir d'où elle vient.
    """
    a_retirer = set(noms)
    if not a_retirer:
        return
    restantes = [
        origine for origine in lire_l_index(repo_id)
        if not (origine.provider == provider and origine.resource in a_retirer)
    ]
    _ecrire_l_index(repo_id, restantes)


# ── ce que le provisionnement consigne ────────────────────────────────────────


def horodatage() -> str:
    """L'instant du provisionnement, en UTC, à la seconde.

    UTC et non l'heure locale : deux machines provisionnées depuis deux fuseaux
    doivent se comparer, et un horodatage sans fuseau ne se compare à rien.
    """
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def nouvel_identifiant() -> str:
    """L'identifiant du provisionnement : il relie entre elles les machines d'un même apply."""
    return str(uuid.uuid4())


def construire(
    repo_meta: RepoMetadata,
    *,
    provider: str,
    ressources: list[str],
    provision_id: str,
    horodate: str,
    state: Path | None = None,
    revision: str | None = None,
    project: str | None = None,
) -> list[Origine]:
    """Les origines d'un apply, une par ressource.

    ``catalog_path`` est résolu ici, une fois : c'est le chemin réel au moment du
    provisionnement, et non celui que le pointeur de catalogue actif désignera
    demain.
    """
    chemin = str(repo_meta.path.resolve())
    return [
        Origine(
            catalog_id=repo_meta.id,
            catalog_path=chemin,
            provider=provider,
            resource=nom,
            provisioned_at=horodate,
            provision_id=provision_id,
            project=project,
            terraform_state=str(state) if state is not None else None,
            catalog_revision=revision,
        )
        for nom in ressources
    ]


def nom_chez_le_provider(provider: str, fqdn: str) -> str:
    """Le nom que la ressource porte RÉELLEMENT chez son provider.

    Incus refuse les points dans un nom d'instance : le template y remplace donc
    `.` par `-`, et c'est `alma-rhcsa-1-lab` que `incus list` affiche. Consigner
    le FQDN sous lequel le `meta.yml` le déclare donnerait un index qu'on ne peut
    pas interroger avec ce qu'on lit à l'écran, ce qui est précisément le défaut
    que cette fonctionnalité corrige.
    """
    return fqdn.replace(".", "-") if provider == "incus" else fqdn


def gabarits(
    repo_meta: RepoMetadata, *, provider: str, ressources: list[str]
) -> dict[str, Origine]:
    """L'origine à poser sur chaque ressource : celle déjà connue, ou une neuve.

    UNE ORIGINE DÉJÀ CONSIGNÉE N'EST PAS RÉÉCRITE. C'est le cœur du contrat de
    l'issue : le chemin et la date sont ceux **du provisionnement**, pas ceux de
    la dernière commande. Un reprovision sur une machine existante garde donc sa
    provenance d'origine, même si le clone a été déplacé entre-temps — et c'est
    `infra origin` qui dira que le répertoire n'existe plus, plutôt que l'index
    qui effacera l'ancien chemin sans le dire.

    Une ressource inconnue reçoit une origine neuve : date et identifiant de
    provisionnement du moment. Les deux cas cohabitent dans un même apply, ce qui
    est exactement ce qui arrive quand on ajoute un hôte à un `meta.yml` déjà
    monté.
    """
    from .revision_catalogue import revision_du_catalogue

    connues = {
        origine.resource: origine
        for origine in lire_l_index(repo_meta.id)
        if origine.provider == provider
    }
    # PUIS LA RESSOURCE ELLE-MÊME, et ce n'est pas un luxe. Mesuré sur un
    # provision réel : avec l'index pour seule mémoire, il suffit qu'il
    # disparaisse pour que le gabarit fabrique un horodatage neuf, donc un XML
    # différent, donc une mise à jour du domaine — et `dmacvicar/libvirt` 0.9.7
    # échoue sur TOUTE mise à jour in-place d'un domaine en marche, son `.id`
    # passant de 21 à 22 entre l'envoi et la relecture (« Provider produced
    # inconsistent result after apply »). Un index effacé rendait donc le dépôt
    # improvisionnable.
    #
    # Relire la machine rend la provenance stable par construction, et répare
    # l'index au passage : c'est la ressource qui se souvient, pas le poste.
    for nom in {nom_chez_le_provider(provider, fqdn) for fqdn in ressources}:
        if nom in connues:
            continue
        sur_la_ressource = lire_sur_la_ressource(nom, provider)
        if sur_la_ressource is not None:
            connues[nom] = sur_la_ressource
    horodate = horodatage()
    provision_id = nouvel_identifiant()
    revision = revision_du_catalogue(repo_meta.path)
    chemin = str(repo_meta.path.resolve())
    resultat: dict[str, Origine] = {}
    for fqdn in ressources:
        # La CLÉ reste le FQDN, parce que c'est par lui que le template indexe
        # sa map ; le nom CONSIGNÉ est celui que porte la ressource chez son
        # provider, parce que c'est par lui qu'on la cherchera.
        nom = nom_chez_le_provider(provider, fqdn)
        deja = connues.get(nom)
        resultat[fqdn] = deja if deja is not None else Origine(
            catalog_id=repo_meta.id,
            catalog_path=chemin,
            provider=provider,
            resource=nom,
            provisioned_at=horodate,
            provision_id=provision_id,
            catalog_revision=revision,
        )
    return resultat


def tfvars_de_provenance(
    repo_meta: RepoMetadata, *, provider: str, ressources: list[str]
) -> dict[str, Any]:
    """Les variables de provenance à passer au template de ce provider.

    Rend un dictionnaire vide pour un provider qui ne déclare pas ces variables :
    un ``*.auto.tfvars.json`` qui porte une variable inconnue du template fait
    **échouer** le plan, et c'est déjà le piège qu'`efi_loader` a appris.
    """
    gabarit = gabarits(repo_meta, provider=provider, ressources=ressources)
    if provider == "kvm":
        return {
            "provenance_xml": {
                nom: xml_pour_libvirt(origine)
                for nom, origine in gabarit.items()
            }
        }
    if provider == "incus":
        return {
            "provenance_config": {
                nom: config_pour_incus(origine)
                for nom, origine in gabarit.items()
            }
        }
    return {}


def avec_le_state(origines: list[Origine], state: Path) -> list[Origine]:
    """Ajoute le répertoire de state Terraform à chaque origine.

    C'est une information **locale**, et non une preuve d'origine : elle dit où
    regarder sur CETTE machine, et elle est donc rafraîchie, là où le chemin du
    catalogue ne l'est jamais.
    """
    return [replace(origine, terraform_state=str(state)) for origine in origines]


def completer_les_uuid(origines: list[Origine]) -> list[Origine]:
    """Ajoute l'UUID libvirt de chaque domaine, quand l'hyperviseur répond.

    L'UUID est l'identifiant **stable** d'un domaine : un domaine renommé reste
    le même, et deux dépôts peuvent nommer deux machines pareil. On le demande à
    libvirt plutôt qu'aux sorties Terraform, pour que la trace existe aussi quand
    l'apply s'est arrêté en route.

    Best-effort : un hyperviseur muet laisse l'UUID à ``None``, ce qui est
    « inconnu » et non « absent ». Rien d'autre n'en dépend.
    """
    from ..infra import libvirt

    completees: list[Origine] = []
    for origine in origines:
        if origine.provider != "kvm" or origine.resource_uuid:
            completees.append(origine)
            continue
        resultat = libvirt.run_virsh(["domuuid", origine.resource], check=False)
        identifiant = resultat.stdout.strip() if resultat.ok else ""
        completees.append(
            replace(origine, resource_uuid=identifiant) if identifiant else origine
        )
    return completees


# ── ce que la ressource porte elle-même ───────────────────────────────────────


def xml_pour_libvirt(origine: Origine) -> str:
    """Le bloc ``<metadata>`` d'un domaine, bien formé et échappé.

    Construit ici, en Python, et passé au template en variable : HCL n'a pas de
    fonction d'échappement XML, et un chemin de catalogue peut porter un `&`.
    Fabriquer ce XML côté Terraform aurait produit un document invalide le jour
    où quelqu'un clone dans ``/home/bob/labs & co``, et libvirt refuse alors le
    domaine entier.
    """
    def balise(nom: str, valeur: str | None) -> str:
        if not valeur:
            return ""
        return f"  <dsoxlab:{nom}>{echapper_xml(valeur)}</dsoxlab:{nom}>\n"

    corps = "".join([
        balise("catalogId", origine.catalog_id),
        balise("catalogPath", origine.catalog_path),
        balise("provider", origine.provider),
        balise("provisionedAt", origine.provisioned_at),
        balise("provisionId", origine.provision_id),
        balise("catalogRevision", origine.catalog_revision),
    ])
    return (
        f'<dsoxlab:provenance xmlns:dsoxlab="{NAMESPACE_XML}">\n'
        f"{corps}"
        "</dsoxlab:provenance>"
    )


def config_pour_incus(origine: Origine) -> dict[str, str]:
    """Les clés ``user.dsoxlab.*`` d'une instance Incus."""
    paires = {
        "catalog_id": origine.catalog_id,
        "catalog_path": origine.catalog_path,
        "provider": origine.provider,
        "provisioned_at": origine.provisioned_at,
        "provision_id": origine.provision_id,
        "catalog_revision": origine.catalog_revision,
    }
    return {
        PREFIXE_INCUS + cle: valeur for cle, valeur in paires.items() if valeur
    }


def lire_sur_la_ressource(nom: str, provider: str) -> Origine | None:
    """L'origine lue sur la ressource elle-même, sans index ni state.

    C'est le chemin qui répond encore quand l'état local a disparu. Rend ``None``
    quand la ressource n'existe pas, ne porte pas nos métadonnées, ou que l'outil
    du provider n'est pas joignable : aucun de ces cas n'est une erreur à faire
    remonter, puisque l'index reste la source principale.
    """
    if provider == "kvm":
        return _lire_sur_un_domaine(nom)
    if provider == "incus":
        return _lire_sur_une_instance(nom)
    return None


#: Au-delà, ce n'est plus une provenance : six balises courtes tiennent dans
#: quelques centaines d'octets, et un document plus gros n'a pas été écrit ici.
XML_MAX = 64 * 1024


def _xml_recevable(brut: str) -> bool:
    """Le fragment est-il de la forme que ce module écrit, et rien d'autre ?

    Trois refus, avant tout parsing : une taille déraisonnable, une déclaration
    de type de document, une déclaration d'entité. Les deux dernières sont les
    vecteurs de l'expansion récursive (« billion laughs »), que la bibliothèque
    standard ne borne pas. L'entrée vient certes de l'hyperviseur local, mais
    « local » n'est pas « écrit par nous » : n'importe quel outil ayant accès à
    libvirt peut avoir posé ce XML.
    """
    if len(brut) > XML_MAX:
        logger.warning("oversized provenance metadata (%d bytes), ignored", len(brut))
        return False
    tete = brut[:4096].upper()
    if "<!DOCTYPE" in tete or "<!ENTITY" in tete:
        logger.warning("provenance metadata declares a DTD, ignored")
        return False
    return True


def _lire_sur_un_domaine(nom: str) -> Origine | None:
    from xml.etree import ElementTree

    from ..infra import libvirt

    resultat = libvirt.run_virsh(["metadata", nom, NAMESPACE_XML], check=False)
    brut = resultat.stdout.strip() if resultat.ok else ""
    if not brut or not _xml_recevable(brut):
        return None
    try:
        # S314 : l'entrée vient de l'hyperviseur local, et les deux vecteurs que
        # `defusedxml` couvre sont refusés juste au-dessus par `_xml_recevable`
        # — aucune DTD, aucune entité, taille bornée. Ajouter une dépendance
        # runtime pour relire six balises que ce module a lui-même écrites
        # coûterait plus que le contrôle explicite.
        racine = ElementTree.fromstring(brut)  # noqa: S314
    except ElementTree.ParseError:
        logger.warning("unparsable provenance metadata on domain %s", nom)
        return None
    # `virsh metadata` rend le fragment SANS son namespace : les balises
    # arrivent donc nues, et les chercher préfixées ne trouverait rien.
    lu = {enfant.tag: (enfant.text or "").strip() for enfant in racine}
    uuid_resultat = libvirt.run_virsh(["domuuid", nom], check=False)
    return Origine.depuis_json(
        {
            "catalog_id": lu.get("catalogId", ""),
            "catalog_path": lu.get("catalogPath", ""),
            "provider": lu.get("provider", "kvm"),
            "resource": nom,
            "provisioned_at": lu.get("provisionedAt", ""),
            "provision_id": lu.get("provisionId", ""),
            "catalog_revision": lu.get("catalogRevision") or None,
            "resource_uuid": (
                uuid_resultat.stdout.strip() if uuid_resultat.ok else None
            ),
        },
        source="ressource",
    )


def _lire_sur_une_instance(nom: str) -> Origine | None:
    from ..utils.shell import run_command

    resultat = run_command(
        ["incus", "query", f"/1.0/instances/{nom}"], check=False, timeout=15,
    )
    if not resultat.ok:
        return None
    try:
        document = json.loads(resultat.stdout)
    except json.JSONDecodeError:
        return None
    config = document.get("config")
    if not isinstance(config, dict):
        return None
    lu = {
        cle.removeprefix(PREFIXE_INCUS): valeur
        for cle, valeur in config.items()
        if cle.startswith(PREFIXE_INCUS)
    }
    if not lu:
        return None
    return Origine.depuis_json(
        {
            "catalog_id": lu.get("catalog_id", ""),
            "catalog_path": lu.get("catalog_path", ""),
            "provider": lu.get("provider", "incus"),
            "resource": nom,
            "provisioned_at": lu.get("provisioned_at", ""),
            "provision_id": lu.get("provision_id", ""),
            "catalog_revision": lu.get("catalog_revision") or None,
            "project": document.get("project") or None,
        },
        source="ressource",
    )


# ── la recherche, telle que `infra origin` l'expose ───────────────────────────


def tous_les_depots() -> list[str]:
    """Les dépôts qui ont un index, lus sur le disque et non sur une liste écrite."""
    racine = _racine_d_etat()
    if not racine.is_dir():
        return []
    return sorted(
        chemin.parent.name for chemin in racine.glob(f"*/{FICHIER}")
    )


def toutes_les_origines() -> list[Origine]:
    """Toutes les origines consignées, tous dépôts confondus."""
    origines: list[Origine] = []
    for repo_id in tous_les_depots():
        origines.extend(lire_l_index(repo_id))
    return sorted(origines, key=lambda o: (o.provider, o.resource))


def chercher(nom: str, *, provider: str | None = None) -> list[Origine]:
    """Les origines d'une ressource, par nom ou par UUID.

    L'index d'abord, qui porte le plus de champs ; à défaut la ressource
    elle-même, ce qui fait tenir la traçabilité quand l'état local a disparu.

    Rend une **liste**, et c'est délibéré : deux dépôts peuvent avoir nommé deux
    machines pareil, et choisir pour l'utilisateur serait trancher à sa place.
    L'appelant doit alors désambiguïser.
    """
    # Les deux formes du nom : celle du `meta.yml` (`alma-1.lab`) et celle que
    # porte la ressource (`alma-1-lab` sur Incus). L'utilisateur tape ce qu'il a
    # sous les yeux, et ce n'est pas toujours la même.
    formes = {nom, nom.replace(".", "-")}
    trouvees = [
        origine for origine in toutes_les_origines()
        if (formes & {origine.resource} or nom == origine.resource_uuid)
        and (provider is None or origine.provider == provider)
    ]
    if trouvees:
        return trouvees
    for candidat in (provider,) if provider else ("kvm", "incus"):
        if candidat is None:
            continue
        sur_la_ressource = lire_sur_la_ressource(nom, candidat)
        if sur_la_ressource is not None:
            return [sur_la_ressource]
    return []


def catalogues_de_meme_id(origine: Origine) -> list[Path]:
    """Les catalogues installés qui déclarent le MÊME ``repo.id``, ailleurs.

    Sert à DIRE qu'un clone a probablement été déplacé, sans jamais réécrire
    l'origine : la preuve reste ce qu'elle était, et l'hypothèse s'affiche comme
    une hypothèse. La comparaison porte sur le ``repo.id`` lu dans chaque
    ``meta.yml``, et non sur le nom du répertoire, qu'un clone peut changer sans
    changer de catalogue.
    """
    from ..discovery.repo import read_repo_metadata
    from .catalog import installes

    candidats: list[Path] = []
    for catalogue in installes():
        if catalogue.racine.resolve() == origine.chemin:
            continue
        try:
            meta = read_repo_metadata(catalogue.racine)
        except (ValueError, OSError):
            continue
        if meta is not None and meta.id == origine.catalog_id:
            candidats.append(catalogue.racine)
    return candidats
