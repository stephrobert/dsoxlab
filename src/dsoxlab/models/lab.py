"""Modèle de données principal : LabDefinition."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

from ._contract import (
    LabYamlError,
    as_argv,
    as_argv_list,
    as_int,
    as_mapping,
    as_mapping_list,
    as_str_list,
)
from .runtime import RuntimeConfig, RuntimeType, Service, Target
from .schema_version import DEFAULT_SCHEMA_VERSION, read_schema_version


@dataclass
class ValidationConfig:
    functional: bool = True
    security: bool = False
    persistence_after_reboot: bool = False


def _charger_document(lab_yaml: Path) -> dict[str, Any]:
    """Le `lab.yaml` chargé, et la garantie que c'est bien un mapping.

    Un fichier vide ou réduit à des commentaires donne `None` ; une racine en
    liste ou en scalaire donne une `list` ou un `int`. Sans ce garde-fou,
    l'accès suivant lèverait `AttributeError`, hors du contrat que
    `discovery/scanner.py` rattrape : le lab ferait planter la CLI au lieu
    d'être écarté avec un avertissement.
    """
    with lab_yaml.open(encoding="utf-8") as fh:
        data = yaml.safe_load(fh)
    if not isinstance(data, dict):
        raise LabYamlError(
            f"{lab_yaml}: le document doit être un mapping YAML "
            f"(reçu : {type(data).__name__})."
        )
    return data


def _fusionner_la_traduction(
    data: dict[str, Any], lab_yaml: Path, lang: str, traduisibles: tuple[str, ...]
) -> None:
    """Applique `lab.<lang>.yaml` sur les seuls champs traduisibles.

    Une traduction illisible est **avalée volontairement** : elle ne doit pas
    faire disparaître un lab du catalogue. L'original reste affiché, dans sa
    langue, ce qui est très préférable à un lab absent de `list-labs` sans
    que rien ne le dise.
    """
    if not lang or lang == "en":
        return
    fichier = lab_yaml.parent / f"lab.{lang[:2].lower()}.yaml"
    if not fichier.exists():
        return
    try:
        with fichier.open(encoding="utf-8") as fh:
            traduction = yaml.safe_load(fh)
    except yaml.YAMLError:
        return
    if not isinstance(traduction, dict):
        return
    for cle in traduisibles:
        if cle in traduction:
            data[cle] = traduction[cle]


def _lire_targets(runtime_data: dict[str, Any], lab_yaml: Path) -> list[Target]:
    """Les cibles déclarées, chacune nommée et rattachée à un hôte."""
    targets: list[Target] = []
    for idx, t in enumerate(
        as_mapping_list(runtime_data.get("targets"), "runtime.targets", lab_yaml)
    ):
        if "name" not in t or "host" not in t:
            raise LabYamlError(
                f"{lab_yaml}: runtime.targets[{idx}] doit contenir 'name' et 'host'."
            )
        roles = as_mapping(t.get("roles"), f"runtime.targets[{idx}].roles", lab_yaml)
        targets.append(Target(
            name=str(t["name"]),
            host=str(t["host"]),
            label_en=str(t.get("label_en", "")),
            label_fr=str(t.get("label_fr", "")),
            roles={str(k): str(v) for k, v in roles.items()},
        ))
    return targets


def _lire_services(runtime_data: dict[str, Any], lab_yaml: Path) -> list[Service]:
    """Les conteneurs dont le lab a besoin, image et nom obligatoires.

    dsoxlab lance l'image que le lab déclare : aucun nom de produit n'a sa
    place ici, c'est l'invariant d'agnosticisme du contrat.
    """
    services: list[Service] = []
    for idx, s in enumerate(
        as_mapping_list(runtime_data.get("services"), "runtime.services", lab_yaml)
    ):
        if "name" not in s or "image" not in s:
            raise LabYamlError(
                f"{lab_yaml}: runtime.services[{idx}] doit contenir 'name' et 'image'."
            )
        prefixe = f"runtime.services[{idx}]"
        env = as_mapping(s.get("env"), f"{prefixe}.env", lab_yaml)
        services.append(Service(
            name=str(s["name"]),
            image=str(s["image"]),
            ports=as_str_list(s.get("ports"), f"{prefixe}.ports", lab_yaml),
            run_args=as_str_list(s.get("run_args"), f"{prefixe}.run_args", lab_yaml),
            env={str(k): str(v) for k, v in env.items()},
            ready_tcp=as_int(s.get("ready_tcp"), 0, f"{prefixe}.ready_tcp", lab_yaml),
            ready_exec=as_argv(s.get("ready_exec"), f"{prefixe}.ready_exec", lab_yaml),
            ready_timeout=as_int(
                s.get("ready_timeout"), 90, f"{prefixe}.ready_timeout", lab_yaml
            ),
            post_start=as_argv_list(
                s.get("post_start"), f"{prefixe}.post_start", lab_yaml
            ),
            spawns=as_str_list(s.get("spawns"), f"{prefixe}.spawns", lab_yaml),
        ))
    return services


def _lire_runtime(data: dict[str, Any], lab_yaml: Path) -> RuntimeConfig:
    """Le bloc `runtime:`, cibles et services compris.

    `runtime: vm` au lieu du bloc `runtime:\\n  type: vm` est la faute la plus
    naturelle du contrat : elle donne une chaîne, pas un mapping, et c'est
    `as_mapping` qui le dit en nommant le champ.
    """
    runtime_data = as_mapping(data.get("runtime"), "runtime", lab_yaml)
    return RuntimeConfig(
        type=RuntimeType(runtime_data.get("type", "shell")),
        targets=_lire_targets(runtime_data, lab_yaml),
        default=str(runtime_data.get("default", "")),
        snapshot_required=bool(runtime_data.get("snapshot_required", False)),
        session=str(runtime_data.get("session", "target")),
        workdir=runtime_data.get("workdir", "challenge/work"),
        fixtures=as_str_list(runtime_data.get("fixtures"), "runtime.fixtures", lab_yaml),
        topology=runtime_data.get("topology", "local"),
        services=_lire_services(runtime_data, lab_yaml),
    )


@dataclass
class LabDefinition:
    id: str
    title: str
    level: str
    skills: list[str]
    runtime: RuntimeConfig
    distros: list[str]
    doc_url: str
    validation: ValidationConfig
    path: Path = field(default_factory=Path)

    section: str | None = None
    """Section déclarée par le ``lab.yaml``, ou ``None`` s'il n'en déclare pas.

    La sentinelle est ``None``, jamais un nom de domaine. Le défaut était
    ``"linux"``, ce qui rendait « non déclaré » et « déclaré à linux »
    indiscernables : un lab qui écrivait ``section: linux`` dans un catalogue
    d'une autre catégorie voyait sa déclaration écrasée en silence, et le
    moteur portait un nom de domaine dans son code.

    ``discovery/scanner.py`` remplace la sentinelle par ``repo.category`` (ou
    par la section inférée du chemin en mode legacy). Elle ne survit donc que
    pour un lab qu'aucune des deux règles ne rattache."""

    description: str = ""
    track: list[str] = field(default_factory=list)
    difficulty: str = "beginner"
    estimated_time: str = "30m"
    certification_tags: list[str] = field(default_factory=list)

    prerequisites: list[str] = field(default_factory=list)
    """Identifiants des labs que celui-ci suppose déjà joués.

    ``doc_url`` dit quelle leçon un lab éprouve, et c'est exactement ce qu'il
    faut pour un micro-lab : une compétence, une leçon, un jumelage
    vérifiable. Un **capstone** n'entre pas dans ce moule — il croise sept
    sujets et ne peut en nommer qu'un, si bien qu'un lecteur du catalogue
    conclut qu'il porte sur le dépannage alors qu'il exige aussi de corriger
    une réserve CPU et d'exposer un service.

    Une liste de ``doc_url`` répondrait à moitié : elle dirait « ce lab éprouve
    ces sept leçons », ce qui est vrai et peu utile. Les prérequis disent
    l'**ordre**, qui est la vraie information — et un site qui consomme le
    catalogue peut alors proposer le capstone à la fin d'un chapitre au lieu de
    le noyer dans une liste.

    Les identifiants sont ceux d'autres labs du même catalogue.
    ``validate-structure`` vérifie qu'ils existent : un prérequis qui nomme un
    lab absent est exactement le genre d'erreur qu'un auteur ne voit jamais."""

    schema_version: int = DEFAULT_SCHEMA_VERSION
    """Version du contrat d'entrée que ce ``lab.yaml`` déclare respecter.

    Absent du fichier = 1, la seule valeur possible aujourd'hui. Voir
    :mod:`dsoxlab.models.schema_version`."""

    lab_type: str = "lab"
    """Ce que ce lab est : ``lab``, ``challenge``, ``capstone`` ou ``validation``.

    Les trois premiers supposent un **apprenant qui fait**, et se distinguent
    par leur ampleur. Le quatrième non : un ``validation`` est une suite
    d'assertions qui défend les faits publiés par un guide. Un test rouge y
    signale un guide à rafraîchir, pas un apprenant en faute — et tout ce qui
    mesure une personne perd alors son objet. Voir :attr:`is_exercise`."""

    exam_passing_score: int = 0
    """Pourcentage du barème à atteindre pour réussir, ou 0 s'il n'y a pas de seuil.

    Un ``lab_type: capstone`` est un examen blanc, et un examen sans seuil de
    réussite n'en est pas un : onze labs d'examen déclaraient ce champ, aucun
    ne le posait. ``submit`` en rend désormais un verdict et ``scores``
    l'affiche.

    Un **pourcentage**, pas un nombre de points : le barème d'un lab est celui
    de son ``challenge/hints.yaml`` (100 par défaut, mais libre), et un seuil
    en points absolus voudrait dire autre chose d'un lab à l'autre."""

    bloc: int = 0               # bloc number 1-8; 0 = unassigned
    bloc_order: int = 0         # position within the bloc; 0 = unassigned
    bloc_name: str = ""         # nom lisible du bloc (section meta.yml), ex. "Fondamentaux (l1)"

    # Translatable fields — overridden by lab.<lang>.yaml when available
    _TRANSLATABLE = ("title", "description")

    @property
    def is_exercise(self) -> bool:
        """Ce lab mesure-t-il quelqu'un ?

        La question commande tout ce qui suit un ``check`` : une note dans la
        base, une place dans la progression, un indice facturé. Pour un
        ``lab_type: validation``, la réponse est non, et ce n'est pas un détail
        de présentation — inscrire un score reviendrait à noter un **guide**,
        et la progression mesurerait une avancée qui n'existe pas.

        Une propriété plutôt qu'un test d'égalité répété : le jour où une
        cinquième forme apparaît, c'est ici qu'on tranche, et nulle part
        ailleurs.
        """
        return self.lab_type != "validation"

    @classmethod
    def from_yaml(cls, lab_yaml: Path, lang: str = "en") -> LabDefinition:
        """Load a LabDefinition from a lab.yaml file.

        If ``lang`` != "en" and a ``lab.<lang>.yaml`` file exists in the same
        directory, translatable fields (title, description) are overridden by
        that file.

        Raises:
            LabYamlError: le fichier sort du contrat. Le message n'est
                **jamais affiché** : ``discovery/scanner.py`` est le seul
                appelant, il écarte le lab et journalise la raison. Il reste
                donc technique et non traduit, à la différence de ce que lève
                la lecture d'un ``meta.yml``. Voir :class:`._contract.LabYamlError`.
        """
        data = _charger_document(lab_yaml)

        # AVANT toute autre lecture : si le fichier annonce une version du
        # contrat que ce dsoxlab ne connaît pas, aucun de ses champs n'a de
        # sens ici. Échouer sur `schema_version` nomme la vraie cause ; échouer
        # trois champs plus loin enverrait l'auteur corriger un champ correct.
        schema_version = read_schema_version(data, lab_yaml)
        _fusionner_la_traduction(data, lab_yaml, lang, cls._TRANSLATABLE)
        runtime = _lire_runtime(data, lab_yaml)

        # `None`, pas une chaîne, quand la clé est absente : c'est ce qui
        # distingue « non déclaré » de « déclaré », y compris quand la valeur
        # déclarée est le nom d'un domaine.
        section_raw = data.get("section")
        section = str(section_raw) if section_raw is not None else None

        validation_data = as_mapping(data.get("validation"), "validation", lab_yaml)
        validation = ValidationConfig(
            functional=validation_data.get("functional", True),
            security=validation_data.get("security", False),
            persistence_after_reboot=validation_data.get("persistence_after_reboot", False),
        )

        return cls(
            schema_version=schema_version,
            id=data["id"],
            title=data["title"],
            level=data["level"],
            skills=as_str_list(data.get("skills"), "skills", lab_yaml),
            runtime=runtime,
            distros=as_str_list(data.get("distros"), "distros", lab_yaml),
            doc_url=data.get("doc_url", ""),
            validation=validation,
            path=lab_yaml.parent,
            section=section,
            description=data.get("description", ""),
            track=as_str_list(data.get("track"), "track", lab_yaml),
            difficulty=data.get("difficulty", "beginner"),
            estimated_time=data.get("estimated_time", "30m"),
            certification_tags=as_str_list(
                data.get("certification_tags"), "certification_tags", lab_yaml
            ),
            prerequisites=as_str_list(
                data.get("prerequisites"), "prerequisites", lab_yaml
            ),
            lab_type=data.get("lab_type", "lab"),
            exam_passing_score=as_int(
                data.get("exam_passing_score"), 0, "exam_passing_score", lab_yaml
            ),
            bloc=as_int(data.get("bloc"), 0, "bloc", lab_yaml),
            bloc_order=as_int(data.get("bloc_order"), 0, "bloc_order", lab_yaml),
        )
