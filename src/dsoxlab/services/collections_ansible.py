"""Les collections Ansible qu'un catalogue exige, et celles qui sont là.

Défaut rapporté par deux utilisateurs (kubernetes-dsoxlab-training#94) : sur
une machine fraîche, **tous** les labs de ce catalogue échouaient au `run`, sur
un `couldn't resolve module/action 'community.general.modprobe'`. La cause
tient en une phrase : `ansible-core` ne fournit que `ansible.builtin`, les
collections ne sont pas des paquets Python, et rien ne les installe.

Le mainteneur ne reproduisait pas, et pour une raison instructive : sa machine
portait douze collections installées au fil d'années de travail. C'est le cas
d'école du défaut qu'on ne voit jamais chez soi.

Ce module mesure donc les deux moitiés du problème :

- ce que le catalogue **exige**, et c'est lui qui le dit. D'abord son
  `requirements.yml` racine, la convention Ansible, versionnée et porteuse des
  bornes de version ; à défaut, les modules appelés en FQCN dans les playbooks
  que dsoxlab joue lui-même (`setup.yaml`, `cleanup.yaml`, `shared/`) ;
- ce qui est **installé**, demandé à `ansible-galaxy`.

La distinction des deux sources n'est pas cosmétique : elle décide du geste de
réparation. Un `requirements.yml` borne les versions, et le catalogue
kubernetes explique noir sur blanc pourquoi (ses 37 labs ont été validés en
`community.general` 11.4.7, deux majeures avant la dernière publiée). Réparer
en installant le nom seul y installerait ce que personne n'a joué : quand la
déclaration existe, c'est elle qu'on joue, avec son `-r`.

Ce que la `solution/` d'un lab appelle ne compte pas : c'est le travail de
l'apprenant, et souvent le sujet même du lab.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path

import yaml

from ..utils.shell import run_command

#: Un module appelé en FQCN, en tête de tâche. `ansible.builtin` est exclu à la
#: lecture : il vient avec ansible-core, et ne s'installe pas.
_MODULE = re.compile(r"^\s+([a-z0-9_]+)\.([a-z0-9_]+)\.[a-z0-9_]+:\s*$", re.MULTILINE)

#: La convention Ansible, à la racine du catalogue.
_REQUIREMENTS = "requirements.yml"

#: Au-delà, on cesse de lire : un catalogue aux centaines de playbooks ne doit
#: pas rallonger `doctor` de plusieurs secondes. La limite est haute devant les
#: 176 playbooks du plus gros catalogue mesuré.
_PLAFOND_DE_FICHIERS = 600


@dataclass(frozen=True)
class BesoinsEnCollections:
    """Ce que le catalogue exige, et ce qui manque pour le jouer."""

    #: Collection -> le fichier qui l'exige, pour pouvoir le nommer.
    exigees: dict[str, str] = field(default_factory=dict)
    installees: frozenset[str] = frozenset()
    #: ``False`` quand `ansible-galaxy` n'a pas répondu : on ne conclut alors
    #: NI que tout va bien, NI que tout manque.
    mesurable: bool = True
    #: Le `requirements.yml` du catalogue, s'il en a un. Sa présence change le
    #: geste de réparation : lui seul porte les bornes de version.
    declaration: Path | None = None

    @property
    def manquantes(self) -> list[str]:
        if not self.mesurable:
            return []
        return sorted(set(self.exigees) - self.installees)


def playbooks_joues(racine: Path) -> list[Path]:
    """Les playbooks que dsoxlab lance, et eux seuls.

    `shared/` est inclus parce que les `setup.yaml` y délèguent le gros du
    travail : sur `kubernetes`, un unique `shared/noeud-kubernetes.yml` est
    joué par les 64 labs, et c'est lui qui portait le module manquant.
    """
    fichiers: list[Path] = []
    for motif in ("labs/**/setup.yaml", "labs/**/cleanup.yaml"):
        fichiers += sorted(racine.glob(motif))
    partage = racine / "shared"
    if partage.is_dir():
        fichiers += sorted(partage.rglob("*.yml")) + sorted(partage.rglob("*.yaml"))
    return [f for f in fichiers[:_PLAFOND_DE_FICHIERS] if f.is_file()]


def collections_declarees(racine: Path) -> dict[str, str]:
    """Ce que le `requirements.yml` racine déclare, s'il existe.

    Le format Galaxy admet une chaîne (`- community.general`) comme un mapping
    (`- name: community.general`) ; les deux se rencontrent dans les catalogues.
    """
    fichier = racine / _REQUIREMENTS
    if not fichier.is_file():
        return {}
    try:
        document = yaml.safe_load(fichier.read_text(encoding="utf-8")) or {}
    except (OSError, yaml.YAMLError):
        return {}
    if not isinstance(document, dict):
        return {}
    entrees = document.get("collections") or []
    if not isinstance(entrees, list):
        return {}
    declarees: dict[str, str] = {}
    for entree in entrees:
        nom = entree.get("name") if isinstance(entree, dict) else entree
        if isinstance(nom, str) and nom.count(".") == 1:
            declarees.setdefault(nom, _REQUIREMENTS)
    return declarees


def collections_appelees(racine: Path) -> dict[str, str]:
    """Les collections appelées par les playbooks joués, et où les trouver.

    Lire les appels, et pas seulement la déclaration, attrape le cas que le
    `requirements.yml` ne dit pas : un module ajouté dans un `setup.yaml` sans
    que personne ait pensé à compléter la liste.
    """
    appelees: dict[str, str] = {}
    for fichier in playbooks_joues(racine):
        try:
            texte = fichier.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        for espace, collection in _MODULE.findall(texte):
            if espace == "ansible" and collection == "builtin":
                continue
            nom = f"{espace}.{collection}"
            appelees.setdefault(nom, str(fichier.relative_to(racine)))
    return appelees


def collections_installees() -> frozenset[str] | None:
    """Ce qu'`ansible-galaxy` déclare, ou ``None`` s'il n'a pas répondu.

    La sortie JSON est un mapping chemin -> {collection: {version}}. Une
    installation peut en avoir plusieurs, et c'est l'union qui compte.
    """
    resultat = run_command(
        ["ansible-galaxy", "collection", "list", "--format", "json"],
        check=False,
        timeout=30,
    )
    if not resultat.ok:
        return None
    try:
        document = json.loads(resultat.stdout)
    except (ValueError, TypeError):
        return None
    if not isinstance(document, dict):
        return None
    noms: set[str] = set()
    for contenu in document.values():
        if isinstance(contenu, dict):
            noms.update(str(nom) for nom in contenu)
    return frozenset(noms)


def geste_d_installation(besoins: BesoinsEnCollections) -> list[str]:
    """La commande qui installe ce qui manque, et respecte ce qui est déclaré.

    Quand le catalogue porte un `requirements.yml`, c'est LUI qu'on joue : il
    borne les versions, là où le nom seul prendrait la dernière publiée. Le
    catalogue kubernetes écrit pourquoi dans ce fichier même : ses 37 labs ont
    été validés deux majeures avant elle, et faire installer une version que
    personne n'a jouée est précisément ce qu'un diagnostic ne doit pas faire.

    Un seul endroit la construit, parce que deux appelants la proposent
    (`doctor --fix` et `catalog add`) et qu'ils doivent dire la même chose.
    """
    if besoins.declaration:
        return [
            "ansible-galaxy", "collection", "install",
            "-r", str(besoins.declaration),
        ]
    return ["ansible-galaxy", "collection", "install", *besoins.manquantes]


def mesurer(racine: Path) -> BesoinsEnCollections:
    """Confronte ce que le catalogue exige à ce qui est installé."""
    declarees = collections_declarees(racine)
    exigees = {**collections_appelees(racine), **declarees}
    declaration = racine / _REQUIREMENTS if declarees else None
    if not exigees:
        # Rien à vérifier : on n'interroge pas ansible-galaxy pour rien, et le
        # contrôle restera vert sans avoir eu besoin de lui.
        return BesoinsEnCollections(exigees={}, installees=frozenset())
    installees = collections_installees()
    if installees is None:
        return BesoinsEnCollections(
            exigees=exigees, mesurable=False, declaration=declaration
        )
    return BesoinsEnCollections(
        exigees=exigees, installees=installees, declaration=declaration
    )
