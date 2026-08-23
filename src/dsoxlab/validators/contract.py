"""Contrôles du contrat lus **à la source** : version, et clés inconnues.

Les autres validators itèrent sur ``discover_labs()``, donc sur ce qui a déjà
été chargé avec succès : un ``lab.yaml`` qui lève au parsing traverse toute la
validation sans un mot. C'est exactement le sort d'un fichier dont le
``schema_version`` est illisible ou trop récent : il n'existe plus pour le reste
de la chaîne, et le seul symptôme est un lab absent de ``list-labs``.

Ce contrôle-ci relit donc les fichiers du catalogue directement, avant toute
découverte, et ne regarde qu'une chose : le numéro de version du contrat. Il
voit ce que les autres ne peuvent pas voir.

Le second contrôle, :func:`validate_unknown_keys`, relève **les clés que le
moteur n'ira jamais lire**. Le parseur les ignore en silence — c'est une
garantie de la v1, et elle doit le rester : un outil v1 doit survivre à un
catalogue v1.1. Mais « toléré par le moteur » n'est pas « voulu par l'auteur ».
Quatre clés écrites de bonne foi dans les catalogues réels ne servaient à
personne, dont un ``exam_passing_score`` dans onze labs d'examen : leur auteur
croyait poser un seuil de réussite, et rien ne le posait. Une clé inconnue à
ce niveau est une faute de frappe ou une attente déçue, presque jamais une
extension délibérée — d'où un contrôle de lint, là où le parseur reste
tolérant.

Il ne compose aucune phrase : chaque anomalie porte une **clé i18n** et ses
paramètres, que la CLI rend dans la langue de l'apprenant. Un validator qui
écrirait ses messages en dur les afficherait dans une seule langue.
"""

from __future__ import annotations

import difflib
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

from ..models._contract import ContractError
from ..models.schema_version import (
    UnsupportedSchemaVersion,
    read_schema_version,
)


@dataclass(frozen=True)
class ContractIssue:
    """Une anomalie de version de contrat, prête à être traduite."""

    path: Path
    key: str
    """Clé i18n du message, présente dans ``strings/en.py`` ET ``strings/fr.py``."""

    params: dict[str, Any] = field(default_factory=dict)
    """Paramètres de substitution du message."""


@dataclass
class ContractReport:
    issues: list[ContractIssue] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.issues

    @property
    def meta_is_unreadable(self) -> bool:
        """Le ``meta.yml`` lui-même est-il en cause ?

        Il décrit tout le catalogue : ne pas savoir le lire rend chaque
        contrôle suivant douteux, alors qu'un lab isolé n'empêche pas de
        valider les autres. La CLI s'arrête dans un cas, poursuit dans l'autre.
        """
        return any(issue.path.name == "meta.yml" for issue in self.issues)


def _documents(root: Path) -> list[Path]:
    """Les fichiers du contrat, ``meta.yml`` puis les ``lab.yaml``.

    Même parcours que ``discovery/scanner.py``, y compris les ``tp-*`` de
    rétro-compat : un contrôle qui regarderait moins de fichiers que le moteur
    laisserait passer précisément ceux qu'il faut signaler.
    """
    documents: list[Path] = []
    meta = root / "meta.yml"
    if meta.is_file():
        documents.append(meta)
    if (root / "labs").exists():
        documents += sorted(
            chemin
            for chemin in (root / "labs").glob("**/*.yaml")
            if chemin.name == "lab.yaml"
        )
    documents += sorted(root.glob("tp-*/lab.yaml"))
    return documents


def validate_schema_versions(root: Path) -> ContractReport:
    """Signale tout ``schema_version`` non entier ou inconnu du catalogue.

    Un document illisible pour une autre raison (YAML cassé, racine qui n'est
    pas un mapping) n'est **pas** rapporté ici : ce n'est pas le sujet de ce
    contrôle, et les validators de structure le signalent déjà à leur manière.
    """
    report = ContractReport()

    for chemin in _documents(root):
        try:
            data = yaml.safe_load(chemin.read_text(encoding="utf-8"))
        except (OSError, yaml.YAMLError):
            continue  # hors sujet : ce contrôle ne parle que de version
        if not isinstance(data, dict):
            continue

        try:
            read_schema_version(data, chemin)
        except UnsupportedSchemaVersion as exc:
            report.issues.append(ContractIssue(
                path=chemin,
                key="schema_version_too_new",
                params={"found": exc.found, "supported": exc.supported},
            ))
        except ContractError as exc:
            # Le modèle porte désormais la clé et les faits : les recopier ici
            # ferait deux textes pour un seul défaut, qui finiraient par
            # diverger. Voir `models/_contract.py: ContractError`.
            report.issues.append(ContractIssue(
                path=chemin, key=exc.key, params=exc.params,
            ))

    return report


# ── Clés inconnues ────────────────────────────────────────────────────────────
#
# Les ensembles ci-dessous décrivent le contrat en **chemins pointés** :
# ``runtime.targets[].host`` désigne la clé ``host`` d'un élément de la liste
# ``targets`` du bloc ``runtime``. Ils sont l'exact reflet des ``properties``
# des schémas JSON publiés, et ``tests/test_json_schemas.py`` en fait foi : il
# dérive le même ensemble depuis ``schemas/*.json`` et exige l'égalité. Les
# schémas restent la référence publiée ; ces constantes sont ce que l'outil
# embarque, puisque ``schemas/`` ne fait pas partie de la roue.
#
# Un nœud SANS enfant déclaré ici est **opaque** : le contrôle n'y descend pas.
# C'est ce qui laisse passer les mappings libres du contrat —
# ``runtime.targets[].roles`` (rôle → FQDN), ``runtime.services[].env``
# (variables d'environnement) et ``infra.providers.<provider>`` (variables du
# module Terraform) — dont les clés appartiennent au catalogue, pas au moteur.

KNOWN_LAB_KEYS: frozenset[str] = frozenset({
    "schema_version",
    "id", "title", "level", "skills", "distros", "doc_url",
    "section", "description", "track", "difficulty", "estimated_time",
    "certification_tags", "lab_type", "exam_passing_score", "bloc", "bloc_order",
    "runtime", "validation",
    "runtime.type", "runtime.targets", "runtime.default",
    "runtime.snapshot_required", "runtime.session", "runtime.workdir",
    "runtime.fixtures", "runtime.services", "runtime.topology",
    "runtime.targets[].name", "runtime.targets[].host",
    "runtime.targets[].label_en", "runtime.targets[].label_fr",
    "runtime.targets[].roles",
    "runtime.services[].name", "runtime.services[].image",
    "runtime.services[].ports", "runtime.services[].run_args",
    "runtime.services[].env", "runtime.services[].ready_tcp",
    "runtime.services[].ready_exec", "runtime.services[].ready_timeout",
    "runtime.services[].post_start",
    "validation.functional", "validation.security",
    "validation.persistence_after_reboot",
})

KNOWN_META_KEYS: frozenset[str] = frozenset({
    "schema_version",
    "repo", "infra", "sections",
    "repo.id", "repo.category", "repo.title", "repo.blog_url", "repo.description",
    "infra.provider", "infra.network", "infra.cidr", "infra.hosts", "infra.providers",
    "infra.hosts[].name", "infra.hosts[].distro", "infra.hosts[].role",
    "infra.hosts[].ram_mb", "infra.hosts[].vcpu", "infra.hosts[].disk_gb",
    "infra.hosts[].extra_disk_gb", "infra.hosts[].ip",
    "sections[].id", "sections[].title", "sections[].description", "sections[].labs",
})

#: Ce qu'un ``lab.<lang>.yaml`` peut porter. La surcharge ne vaut que pour
#: ``title`` et ``description`` ; ``id`` est accepté parce qu'il nomme le lab
#: pour qui relit le fichier, et les 284 traductions des catalogues réels le
#: portent déjà. Tout autre champ y serait ignoré, ce qui est exactement le
#: défaut qu'on répare ailleurs.
KNOWN_LAB_LANG_KEYS: frozenset[str] = frozenset({"id", "title", "description"})

#: Ce qu'un ``meta.<lang>.yml`` peut porter. ``sections[].id`` n'est pas une
#: traduction : c'est la clé d'appariement, sans laquelle la surcharge ne
#: saurait pas quelle section elle traduit.
KNOWN_META_LANG_KEYS: frozenset[str] = frozenset({
    "repo", "sections",
    "repo.title", "repo.description",
    "sections[].id", "sections[].title", "sections[].description",
})

_LAB_LANG = re.compile(r"^lab\.[a-z]{2}\.yaml$")
_META_LANG = re.compile(r"^meta\.[a-z]{2}\.yml$")


def _has_children(known: frozenset[str], prefix: str) -> bool:
    """Le contrat décrit-il quelque chose SOUS ``prefix`` ?

    Non veut dire « nœud opaque » : ses clés appartiennent au catalogue et
    aucune ne peut donc être inconnue. C'est le cas des mappings libres.
    """
    depart = f"{prefix}."
    return any(cle.startswith(depart) for cle in known)


def _unknown_paths(noeud: Any, known: frozenset[str], prefix: str = "") -> list[str]:
    """Les chemins pointés que ``noeud`` porte et que le contrat ne décrit pas."""
    trouves: list[str] = []
    if isinstance(noeud, dict):
        for cle, valeur in noeud.items():
            chemin = f"{prefix}.{cle}" if prefix else str(cle)
            if chemin not in known:
                trouves.append(chemin)
                continue  # inutile de fouiller sous une clé qui n'existe pas
            if _has_children(known, chemin) or _has_children(known, f"{chemin}[]"):
                trouves += _unknown_paths(valeur, known, chemin)
    elif isinstance(noeud, list):
        for element in noeud:
            if isinstance(element, dict):
                trouves += _unknown_paths(element, known, f"{prefix}[]")
    return trouves


def _suggestion(cle: str, known: frozenset[str]) -> str:
    """La clé connue la plus proche **au même niveau**, ou une chaîne vide.

    Chercher dans tout le contrat proposerait ``runtime.session`` pour un
    ``sesion`` écrit à la racine : une piste fausse coûte plus cher que pas
    de piste du tout.

    Le message qui l'emploie dit « la clé la plus proche est X », et non
    « voulais-tu écrire X ». La nuance est mesurée : ``title_en`` → ``title``
    (0,77) et ``hosts_required`` → ``snapshot_required`` (0,77) ont le même
    score, alors que la première est l'intention de l'auteur et la seconde
    une coïncidence. Aucun seuil ne les sépare ; énoncer un fait plutôt que
    prêter une intention reste vrai dans les deux cas.
    """
    prefixe, _sep, feuille = cle.rpartition(".")
    voisines = [
        candidate.rpartition(".")[2]
        for candidate in known
        if candidate.rpartition(".")[0] == prefixe
    ]
    proches = difflib.get_close_matches(feuille, voisines, n=1, cutoff=0.7)
    if not proches:
        return ""
    return f"{prefixe}.{proches[0]}" if prefixe else proches[0]


def _keyed_documents(root: Path) -> list[tuple[Path, frozenset[str]]]:
    """Chaque document du contrat, avec l'ensemble de clés qui le décrit."""
    documents: list[tuple[Path, frozenset[str]]] = []

    meta = root / "meta.yml"
    if meta.is_file():
        documents.append((meta, KNOWN_META_KEYS))
    documents += [
        (chemin, KNOWN_META_LANG_KEYS)
        for chemin in sorted(root.glob("meta.*.yml"))
        if _META_LANG.match(chemin.name)
    ]

    candidats: list[Path] = []
    if (root / "labs").exists():
        candidats += sorted((root / "labs").glob("**/*.yaml"))
    candidats += sorted(root.glob("tp-*/*.yaml"))
    for chemin in candidats:
        if chemin.name == "lab.yaml":
            documents.append((chemin, KNOWN_LAB_KEYS))
        elif _LAB_LANG.match(chemin.name):
            documents.append((chemin, KNOWN_LAB_LANG_KEYS))

    return documents


def validate_unknown_keys(root: Path) -> ContractReport:
    """Signale toute clé qu'aucun champ du contrat ne décrit.

    Parcourt les quatre familles de documents du contrat — ``meta.yml``,
    ``lab.yaml`` et leurs fichiers de traduction — et confronte chaque chemin
    pointé à l'ensemble connu. Un document illisible n'est **pas** rapporté
    ici : ce n'est pas le sujet de ce contrôle, et les autres le signalent.

    Le moteur, lui, continue d'ignorer ces clés sans broncher : c'est une
    garantie du contrat v1, et ce contrôle est un lint, pas le parseur.
    """
    report = ContractReport()

    for chemin, connues in _keyed_documents(root):
        try:
            data = yaml.safe_load(chemin.read_text(encoding="utf-8"))
        except (OSError, yaml.YAMLError):
            continue
        if not isinstance(data, dict):
            continue
        for inconnue in sorted(set(_unknown_paths(data, connues))):
            proche = _suggestion(inconnue, connues)
            report.issues.append(ContractIssue(
                path=chemin,
                key="unknown_key_suggest" if proche else "unknown_key",
                params={"field": inconnue, "suggestion": proche},
            ))

    return report
