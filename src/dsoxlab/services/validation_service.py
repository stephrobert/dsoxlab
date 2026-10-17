"""Valider un catalogue, et rendre le résultat sans l'afficher.

Ce que ce module corrige
========================

``validate-structure`` était la fonction la plus complexe du dépôt :
280 lignes, complexité cyclomatique **53**, cognitive **65**, mesurées le
2026-10-16. Elle enchaînait onze familles de contrôles, tenait le document
machine au fil de l'eau, décidait du verdict, et rendait les deux sorties.

Le même patron de trois instructions y était répété **sept fois** :

.. code-block:: python

    rapport = valider_quelque_chose(root)
    documents += [machine.issue_dict("categorie", a.key, ...) for a in rapport.issues]
    _rendre("entete_i18n", [f"  ✘ {...}" for a in rapport.issues])

Chaque répétition ajoutait ses branches, et la validation n'était appelable que
par la CLI : une CI de catalogue ne pouvait pas l'utiliser autrement qu'en
lançant un sous-processus et en analysant du JSON.

Ici, une **table** décrit les familles, et une boucle les joue. Le service rend
un :class:`RapportValidation` ; la CLI et le mode machine lisent le même objet,
ce qui supprime le risque que l'un signale une anomalie que l'autre taise.

Ce qui ne change pas, et c'est une contrainte dure
==================================================

Le document ``--json`` est joué en CI dans les dépôts de labs : **aucun champ
ne bouge, aucun ordre ne change**. L'ordre des familles ci-dessous est celui de
l'ancienne fonction, et il n'est pas arbitraire : un ``schema_version``
illisible empêche un lab d'être découvert, donc tous les contrôles suivants
l'ignoreraient. On nomme la cause avant les conséquences.
"""

from __future__ import annotations

import contextlib
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from ..models.lab import LabDefinition

#: Les familles d'anomalies, dans l'ordre où elles sont jouées et affichées.
#: Elles figurent **toutes** dans ``counts``, à zéro s'il le faut : un tableau
#: de bord qui n'aurait pas la clé ne saurait pas si la famille est saine ou si
#: cette version de l'outil ne la connaît pas.
FAMILLES = (
    "contract",
    "catalog",
    "unknown_key",
    "structure",
    "content",
    "doc_url",
    "metadata",
)


@dataclass(frozen=True)
class Anomalie:
    """Une anomalie, telle que les deux sorties la liront.

    ``lab`` et ``field`` sont absents selon la famille : une anomalie de
    ``meta.yml`` ne porte pas de lab, une anomalie de structure ne porte pas de
    champ. Les garder à ``None`` plutôt que de les omettre tient la forme du
    document stable.
    """

    famille: str
    cle: str
    params: dict[str, Any] = field(default_factory=dict)
    lab: str | None = None
    chemin: Path | None = None
    champ: str | None = None

    rubrique: str = ""
    """Le titre sous lequel cette anomalie s'affiche.

    Distinct de la famille, et il le faut : deux entrées de la table portent la
    famille ``contract`` (les versions de schéma, et les champs du `meta.yml`)
    avec des titres différents. Grouper sur la seule famille affichait les
    mêmes anomalies sous les deux titres, ce qu'une comparaison du document
    `--json` ne pouvait pas voir, puisqu'il ne groupe pas.
    """


@dataclass
class RapportValidation:
    """Tout ce qu'une validation a trouvé, et ce qu'elle a pu regarder."""

    labs_examines: int = 0
    urls_examinees: bool = False
    anomalies: list[Anomalie] = field(default_factory=list)
    #: Les guides injoignables, à part : un guide qui ne répond pas n'est **pas**
    #: un défaut du lab, c'est un contrôle qui n'a pas pu regarder. Les mêler aux
    #: anomalies ferait échouer une validation pour une coupure de réseau.
    urls_injoignables: list[Anomalie] = field(default_factory=list)
    #: Le ``meta.yml`` est-il illisible ? La validation s'arrête alors, parce
    #: qu'un catalogue dont le contrat ne se lit pas rend tout le reste douteux.
    meta_illisible: bool = False

    @property
    def ok(self) -> bool:
        return not self.anomalies

    def par_famille(self, famille: str) -> list[Anomalie]:
        return [a for a in self.anomalies if a.famille == famille]

    def comptes(self) -> dict[str, int]:
        return {f: len(self.par_famille(f)) for f in FAMILLES}


@dataclass(frozen=True)
class Famille:
    """Une famille de contrôles : son nom, et comment la jouer."""

    nom: str
    entete: str
    #: Joue les contrôles et rend des anomalies. La signature est volontairement
    #: pauvre : la racine et les labs suffisent à tout, et une table se lit mieux
    #: que sept appels aux arguments différents.
    jouer: Callable[[Path, list[LabDefinition]], Iterable[Anomalie]]


def _anomalies_du_contrat(root: Path, _labs: list[LabDefinition]) -> list[Anomalie]:
    """Les ``schema_version`` que cet outil ne sait pas lire.

    **En premier, et à la source** : un lab écarté faute de version n'est pas
    découvert, donc tous les contrôles suivants l'ignoreraient. Ce contrôle
    relit les fichiers du disque plutôt que la liste des labs chargés, qui est
    précisément ce dont il mesure l'amputation.
    """
    from ..validators.contract import validate_schema_versions

    rapport = validate_schema_versions(root)
    return [
        Anomalie("contract", a.key, a.params, chemin=a.path, rubrique="contract_issues_header")
        for a in rapport.issues
    ]


def _anomalies_du_catalogue(root: Path, _labs: list[LabDefinition]) -> list[Anomalie]:
    """Les labs que le moteur ne voit pas : illisibles, ou déclarés et absents.

    Avant tout le reste, parce que ces deux contrôles expliquent pourquoi un lab
    manque aux suivants. Les deux disparaissaient en silence, et l'auteur lisait
    « tous les labs sont valides » sur un catalogue amputé (issue #198).
    """
    from ..validators.contract import validate_labs_chargeables, validate_labs_declares

    anomalies = [
        *validate_labs_chargeables(root).issues,
        *validate_labs_declares(root).issues,
    ]
    return [
        Anomalie("catalog", a.key, a.params, chemin=a.path, rubrique="catalog_issues_header")
        for a in anomalies
    ]


def _anomalies_des_cles_inconnues(
    root: Path, _labs: list[LabDefinition]
) -> list[Anomalie]:
    """Les clés que le moteur n'ira jamais lire.

    Le parseur les ignore et continuera de le faire, c'est une garantie de la
    v1 ; mais « toléré » n'est pas « voulu » : onze labs d'examen ont posé un
    seuil de réussite que personne ne lisait, sans que rien ne le dise.
    """
    from ..validators.contract import validate_unknown_keys

    return [
        Anomalie(
            "unknown_key", a.key, a.params, chemin=a.path,
            rubrique="unknown_keys_header",
        )
        for a in validate_unknown_keys(root).issues
    ]


def _anomalies_des_champs_du_depot(
    root: Path, _labs: list[LabDefinition]
) -> list[Anomalie]:
    """Les champs que le ``meta.yml`` devrait porter vu ce que le dépôt contient.

    Famille ``contract`` comme les versions de schéma, mais **sa propre
    rubrique** à l'affichage : ces anomalies ne parlent pas de la version du
    contrat, et les ranger sous le même titre faisait chercher une histoire de
    version là où il n'y en a pas.
    """
    from ..validators.contract import validate_repo_fields

    return [
        Anomalie(
            "contract", a.key, a.params, chemin=a.path, rubrique="repo_fields_header",
        )
        for a in validate_repo_fields(root).issues
    ]


def _anomalies_de_structure(root: Path, _labs: list[LabDefinition]) -> list[Anomalie]:
    """Fichiers requis, fichiers interdits, cohérence des targets."""
    from .lab_service import validate_all_structure

    return [
        Anomalie(
            "structure", i.key, i.params, lab=r.lab_id, chemin=i.path,
            rubrique="structure_issues_header",
        )
        for r in validate_all_structure(root)
        for i in r.issues
    ]


def _anomalies_de_contenu(root: Path, labs: list[LabDefinition]) -> list[Anomalie]:
    """Les contrôles locaux : liens, fixtures, barème, parité, cibles, solutions.

    Tous jouables hors ligne, donc joués par défaut. Un lien mort ou une
    solution en clair ne casse aucun test fonctionnel, c'est bien pourquoi rien
    ne les attrapait.
    """
    from ..discovery.repo import read_repo_metadata
    from ..validators.content import (
        validate_fixtures,
        validate_internal_links,
        validate_language_parity,
        validate_prerequisites,
        validate_scoring,
        validate_solutions_encrypted,
        validate_targets,
    )

    # Les cibles vm se valident contre `infra.hosts` : un FQDN inconnu ne se
    # voyait qu'au run, sur la machine de l'apprenant, après provisionnement.
    # `meta` est lié AVANT le try : sans cela, un `meta.yml` illisible le
    # laisserait non défini, et le premier contrôle qui le lit lèverait un
    # NameError au lieu de se passer de lui.
    meta = None
    try:
        meta = read_repo_metadata(root)
        hotes = {h.name for h in meta.infra.hosts} if meta else set()
    except Exception:  # noqa: BLE001 - meta.yml illisible : les autres contrôles restent utiles
        hotes = set()

    # Les prérequis se valident contre le catalogue entier : c'est le seul
    # endroit où la liste complète des identifiants existe.
    identifiants = {lab.id for lab in labs}

    anomalies: list[Anomalie] = []
    for lab in labs:
        rapports = [
            validate_internal_links(lab),
            validate_fixtures(lab),
            validate_scoring(lab),
            validate_language_parity(lab),
            validate_targets(lab, hotes),
            validate_prerequisites(lab, identifiants),
        ]
        # Deux dispositions coexistent : « solution/<chemin du lab> » à la
        # racine, et « labs/<lab>/solution/ » dans le lab. Le contrôle ne
        # regardait que la première, et passait donc au vert sur les dépôts qui
        # emploient la seconde, sans avoir regardé.
        #
        # `repo.solutions: plaintext` le désarme, pour les catalogues qui
        # enchaînent leurs labs : le point de départ de l'un y est la solution
        # du précédent, donc le fichier doit pouvoir être copié comme fixture.
        if meta is None or meta.solutions != "plaintext":
            racines = [lab.path / "solution"]
            # Un lab hors de `labs/` n'a pas de chemin relatif : il n'a alors
            # que la disposition « dans le lab », et c'est tout.
            with contextlib.suppress(ValueError):
                racines.append(root / "solution" / lab.path.relative_to(root / "labs"))
            rapports.append(validate_solutions_encrypted(lab, *racines))
        anomalies += [
            Anomalie(
                "content", s.key, s.params, lab=lab.id, chemin=s.path,
                rubrique="content_issues_header",
            )
            for rapport in rapports
            for s in rapport.issues
        ]
    return anomalies


def _anomalies_des_metadonnees(
    root: Path, _labs: list[LabDefinition]
) -> list[Anomalie]:
    """``skills``, ``distros``, ``doc_url``, ``lab_type``."""
    from .lab_service import validate_all_metadata

    return [
        Anomalie(
            "metadata", i.key, i.params, lab=r.lab_id, champ=i.field,
            rubrique="metadata_issues_header",
        )
        for r in validate_all_metadata(root)
        if not r.ok
        for i in r.issues
    ]


#: La table, dans l'ordre où les familles sont jouées et affichées. C'est elle
#: qui remplace les sept répétitions de l'ancienne fonction : ajouter une
#: famille se fait ici, et les deux sorties la servent sans rien savoir d'elle.
TABLE: tuple[Famille, ...] = (
    Famille("contract", "contract_issues_header", _anomalies_du_contrat),
    Famille("catalog", "catalog_issues_header", _anomalies_du_catalogue),
    Famille("unknown_key", "unknown_keys_header", _anomalies_des_cles_inconnues),
    Famille("contract", "repo_fields_header", _anomalies_des_champs_du_depot),
    Famille("structure", "structure_issues_header", _anomalies_de_structure),
    Famille("content", "content_issues_header", _anomalies_de_contenu),
    Famille("metadata", "metadata_issues_header", _anomalies_des_metadonnees),
)


def meta_illisible(root: Path) -> bool:
    """Le ``meta.yml`` est-il inexploitable ?

    Il décrit tout le catalogue : illisible, il rend chaque contrôle suivant
    douteux, et la découverte lèverait de toute façon. Un lab isolé, lui,
    n'empêche pas de valider les autres.
    """
    from ..validators.contract import validate_schema_versions

    rapport = validate_schema_versions(root)
    return not rapport.ok and rapport.meta_is_unreadable


def valider(
    root: Path, labs: list[LabDefinition], *, verifier_urls: bool = False
) -> RapportValidation:
    """Joue toutes les familles de contrôles sur ce catalogue.

    ``labs`` est passé plutôt que découvert ici : l'appelant l'a déjà, et le
    redécouvrir doublerait le parcours du disque sur un catalogue de cent labs.
    """
    rapport = RapportValidation(labs_examines=len(labs), urls_examinees=verifier_urls)

    rapport.anomalies += list(_anomalies_du_contrat(root, labs))
    if meta_illisible(root):
        # On s'arrête, mais on rend la même forme de document : un appelant ne
        # doit pas avoir deux structures à gérer selon l'endroit où la
        # validation s'est interrompue.
        rapport.meta_illisible = True
        rapport.labs_examines = 0
        return rapport

    for famille in TABLE[1:]:
        rapport.anomalies += list(famille.jouer(root, labs))

    if verifier_urls:
        joignables, injoignables = _anomalies_des_guides(labs)
        rapport.anomalies += joignables
        rapport.urls_injoignables += injoignables
    return rapport


def _anomalies_des_guides(
    labs: list[LabDefinition],
) -> tuple[list[Anomalie], list[Anomalie]]:
    """Les ``doc_url`` qui répondent mal, et ceux qui ne répondent pas.

    La distinction est le fond du sujet : un guide injoignable après trois
    tentatives n'est **pas** un défaut du lab, c'est un contrôle qui n'a pas pu
    regarder. Il se dit, sinon une panne durable passerait pour un succès, mais
    il ne fait pas échouer la validation. Peindre en rouge pour une coupure de
    réseau apprend surtout à relancer la CI sans lire le message.
    """
    from ..validators.content import check_doc_urls

    mauvais: list[Anomalie] = []
    muets: list[Anomalie] = []
    # Une requête par URL distincte, pas par lab : plusieurs labs jumellent la
    # même leçon, et les interroger tous n'apprend rien de plus.
    for lab_id, url, souci in check_doc_urls(labs):
        anomalie = Anomalie(
            "doc_url",
            souci.key,
            # L'URL entre dans les paramètres : c'est le fait que l'appelant
            # veut, et il n'a pas à relire le catalogue pour l'obtenir.
            {**souci.params, "url": url},
            lab=lab_id,
            chemin=souci.path,
            rubrique="doc_url_issues_header",
        )
        if souci.key == "content_doc_url_unreachable":
            muets.append(anomalie)
        else:
            mauvais.append(anomalie)
    return mauvais, muets
