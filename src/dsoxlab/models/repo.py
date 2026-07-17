"""Modèle des métadonnées de dépôt fournisseur (meta.yml racine).

Le meta.yml racine est le contrat déclaratif que chaque dépôt fournisseur
de labs (linux-training, ansible-training, kubernetes-training…) doit
respecter pour être pilotable par dsoxlab.

Schéma :

    repo:
      id: <slug>                     # required
      category: <linux|ansible|...>  # required
      title: <human-readable>
      blog_url: <url>
      description: |
        <paragraphe>

    infra:                           # optional — required pour runtime: kvm
      network: <libvirt-network>
      cidr: <CIDR>
      hosts:
        - { name: <fqdn>, ip: <ip>, distro: <slug>, role: <slug>,
            ram_mb: <int>, vcpu: <int>, disk_gb: <int> }

    sections:                        # optional — pilote l'ordre dans list-labs
      - id: <slug>
        title: <human-readable>
        description: <courte>
        labs:
          - <chemin-relatif-depuis-labs/>
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

from ._contract import as_int, as_mapping, as_mapping_list, as_str_list


def _provider_overrides(value: object, meta_path: Path) -> dict[str, dict[str, Any]]:
    """Valide ``infra.providers`` : un mapping provider → mapping d'overrides."""
    if value is None:
        return {}
    if not isinstance(value, dict):
        raise ValueError(
            f"{meta_path}: 'infra.providers' doit être un mapping "
            f"(reçu : {type(value).__name__})."
        )
    overrides: dict[str, dict[str, Any]] = {}
    for name, cfg in value.items():
        if cfg is None:
            overrides[str(name)] = {}
        elif isinstance(cfg, dict):
            overrides[str(name)] = dict(cfg)
        else:
            raise ValueError(
                f"{meta_path}: 'infra.providers.{name}' doit être un mapping "
                f"(reçu : {type(cfg).__name__})."
            )
    return overrides


class ProviderUnresolved(ValueError):
    """Aucun provider d'infrastructure n'est résolu pour ce dépôt.

    Levée par :meth:`InfraDefinition.require_provider` quand une commande
    a besoin d'un provider alors que le ``meta.yml`` en déclare plusieurs
    sans qu'aucun ne soit actif (ou n'en déclare aucun).

    Ne porte **aucun texte destiné à l'utilisateur** : le modèle reste
    agnostique de la langue. La CLI catche cette exception et compose le
    message traduit à partir de ``candidates``.
    """

    def __init__(self, candidates: list[str]) -> None:
        self.candidates = candidates
        super().__init__(
            f"provider unresolved (candidates={candidates or 'none'})"
        )


def _resolve_provider(
    raw_provider: object,
    *,
    context_provider: str | None,
    meta_path: Path,
) -> tuple[str, list[str]]:
    """Résout le provider courant à partir de ``meta.yml: infra.provider``.

    ``raw_provider`` peut être :

    - une **string** (rétro-compat) : un seul provider déclaré.
    - une **liste de strings** : plusieurs providers candidats. L'apprenant
      doit choisir via ``DSOXLAB_PROVIDER``, ``dsoxlab use <name>`` (qui
      pose ``active_provider`` dans le contexte session), ou laisser
      résoudre tout seul si la liste a un seul item.

    Priorité de résolution (la première règle qui matche gagne) :

    1. ``DSOXLAB_PROVIDER`` env var (override one-shot, doit appartenir à la
       liste si une liste est déclarée).
    2. ``context_provider`` (lu depuis ``.dsoxlab-context.json``).
    3. La string brute si le YAML déclare une string, OU le seul item si
       le YAML déclare une liste à un élément.
    4. Sinon (plusieurs candidats, aucun choix actif) : le provider reste
       **non résolu** (``""``). Ce n'est pas une erreur : lister, valider
       ou noter des labs ne dépend d'aucun provider. Seules les commandes
       d'infrastructure l'exigent, via
       :meth:`InfraDefinition.require_provider`, qui lève alors une
       ``ValueError`` guidant vers ``dsoxlab use``.

    Returns:
        ``(provider_résolu_ou_chaîne_vide, providers_available)``. La liste
        retournée vaut ``[]`` quand le YAML déclare une string (pas de choix
        possible), sinon contient les candidats déclarés.
    """
    if isinstance(raw_provider, str):
        candidates: list[str] = []
        default_solo = raw_provider
    elif isinstance(raw_provider, list):
        candidates = [str(p).strip() for p in raw_provider if str(p).strip()]
        if not candidates:
            raise ValueError(
                f"{meta_path}: infra.provider est une liste vide. "
                "Déclare au moins un provider (ex. 'kvm')."
            )
        default_solo = candidates[0] if len(candidates) == 1 else ""
    else:
        raise ValueError(
            f"{meta_path}: infra.provider doit être une string ou une "
            f"liste de strings, pas {type(raw_provider).__name__}."
        )

    env = os.environ.get("DSOXLAB_PROVIDER", "").strip()
    if env:
        if candidates and env not in candidates:
            raise ValueError(
                f"DSOXLAB_PROVIDER='{env}' n'est pas dans les providers "
                f"déclarés par {meta_path}: {candidates}"
            )
        return env, candidates

    if context_provider:
        if candidates and context_provider not in candidates:
            # Contexte stale : on le laisse passer mais on aurait pu
            # raise ; on préfère retomber sur la résolution par défaut.
            pass
        elif context_provider:
            return context_provider, candidates

    if default_solo:
        return default_solo, candidates

    # Plusieurs candidats, aucun choix actif : on ne lève pas ici. La
    # lecture du meta.yml sert aussi aux commandes qui n'ont que faire
    # d'un provider (list-labs, show, validate-structure, scores…) ;
    # les faire échouer sur une ambiguïté d'infra serait absurde.
    # L'exigence est portée par require_provider(), appelée uniquement
    # par les commandes d'infrastructure.
    return "", candidates


@dataclass
class HostDefinition:
    """Une VM déclarée dans ``meta.yml: infra.hosts``.

    L'IP n'est plus une donnée du contrat : elle est calculée par le
    provider (Terraform output ``hosts``) et exposée via l'inventory
    Ansible généré dynamiquement par dsoxlab. Le champ ``ip`` est
    conservé en mode rétro-compat pour les anciens ``meta.yml``.
    """

    name: str
    ip: str = ""  # legacy/optionnel, calculé dynamiquement par provider
    distro: str = ""
    role: str = ""
    ram_mb: int = 1024
    vcpu: int = 1
    disk_gb: int = 10
    extra_disk_gb: int = 0
    """Taille d'un 2e disque additionnel attaché à la VM (en GiB).
    0 = pas de disque additionnel (cas courant). Utile pour les labs
    RHCSA/LFCS qui exigent un vrai bloc device pour partitionner +
    LVM (ex. capstone RHCSA tâches 1-3). Le disque apparaît dans la
    VM comme ``/dev/vdb`` sur kvm/incus, ``/dev/xvdb`` sur outscale."""


@dataclass
class InfraDefinition:
    """Topologie d'infrastructure (provider + réseau + VMs).

    Le provider sélectionne le sous-dossier ``infra/terraform/<provider>/``
    consommé par ``dsoxlab provision``. Surchargeable au runtime via
    la variable d'env ``DSOXLAB_PROVIDER``.
    """

    provider: str = "kvm"
    """Provider d'infrastructure courant — ``kvm`` | ``outscale`` | ``aws``
    | ``gcp`` | ``azure`` | ``vagrant`` | ``incus``.

    Vaut ``""`` quand le ``meta.yml`` déclare plusieurs candidats et
    qu'aucun choix n'est actif : le provider est alors **non résolu**.
    Tout code d'infrastructure doit passer par :meth:`require_provider`
    plutôt que lire ce champ directement."""

    providers_available: list[str] = field(default_factory=list)
    """Liste des providers candidats déclarés dans ``meta.yml``. Vide si
    le repo ne déclare qu'un seul provider (rétro-compat) ; non-vide
    quand l'apprenant peut choisir entre plusieurs (ex. ``[kvm, outscale]``).
    Utile à la CLI pour proposer des choix valides à ``dsoxlab use``."""

    network: str = ""
    cidr: str = ""
    hosts: list[HostDefinition] = field(default_factory=list)
    providers: dict[str, dict[str, Any]] = field(default_factory=dict)
    """Overrides spécifiques par provider — lus par le module Terraform
    correspondant. Exemple : ``providers.aws.region``,
    ``providers.kvm.libvirt_uri``."""

    def host(self, name: str) -> HostDefinition | None:
        """Retourne la HostDefinition par son nom, ou None."""
        for h in self.hosts:
            if h.name == name:
                return h
        return None

    def require_provider(self) -> str:
        """Retourne le provider courant, ou lève si aucun n'est résolu.

        À appeler par tout code qui a réellement besoin d'un provider
        (Terraform, snapshots, inventory). Les commandes qui n'en ont pas
        besoin ne doivent jamais l'appeler : elles fonctionnent très bien
        avec un provider non résolu.

        Raises:
            ProviderUnresolved: si aucun provider n'est résolu. La CLI la
                catche et compose le message traduit qui guide vers
                ``dsoxlab use --provider <name>``.
        """
        if self.provider:
            return self.provider
        raise ProviderUnresolved(list(self.providers_available))

    def provider_config(self, provider: str | None = None) -> dict[str, Any]:
        """Retourne le dict d'overrides du provider courant ou nommé."""
        return dict(self.providers.get(provider or self.provider, {}))


@dataclass
class SectionDefinition:
    """Une section pédagogique du dépôt (ordre + groupement de labs)."""

    id: str
    title: str = ""
    description: str = ""
    labs: list[str] = field(default_factory=list)
    """Chemins relatifs depuis ``<repo>/labs/``."""


@dataclass
class RepoMetadata:
    """Contrat déclaratif du dépôt fournisseur (`meta.yml` racine).

    Cette dataclass est le pivot du framework : elle déclare l'identité du
    dépôt, son infrastructure (si KVM/incus) et l'ordre pédagogique des
    labs. Tout autre code de dsoxlab consomme cette structure pour rester
    domain-agnostic.
    """

    id: str
    """Slug unique du dépôt — ex. ``linux-training``."""

    category: str
    """Catégorie technique — ex. ``linux``, ``ansible``, ``kubernetes``."""

    title: str = ""
    blog_url: str = ""
    description: str = ""
    infra: InfraDefinition = field(default_factory=InfraDefinition)
    sections: list[SectionDefinition] = field(default_factory=list)
    path: Path = field(default_factory=lambda: Path("."))
    """Répertoire racine du dépôt (parent du meta.yml)."""

    @classmethod
    def from_yaml(
        cls,
        meta_path: Path,
        *,
        context_provider: str | None = None,
    ) -> "RepoMetadata":
        """Charge RepoMetadata depuis un fichier meta.yml.

        Args:
            meta_path: chemin du ``meta.yml`` à lire.
            context_provider: provider actif lu depuis le contexte
                session (``.dsoxlab-context.json: active_provider``).
                Utilisé en fallback si ``meta.yml`` déclare plusieurs
                providers candidats et que ``DSOXLAB_PROVIDER`` n'est
                pas posé.

        Lève ``ValueError`` si ``repo.id``/``repo.category`` manquent.

        Une résolution de provider ambiguë (plusieurs candidats, aucun
        choix actif) **ne lève pas** : ``infra.provider`` reste vide et
        l'erreur est différée à ``infra.require_provider()``, appelée par
        les seules commandes d'infrastructure.
        """
        with meta_path.open(encoding="utf-8") as fh:
            data = yaml.safe_load(fh) or {}

        # `or {}` couvre le fichier vide, pas une racine en liste ou en scalaire
        # (ni un bloc `repo:` qui ne serait pas un mapping) : l'accès `.get`
        # lèverait alors AttributeError au lieu du ValueError attendu par la CLI.
        if not isinstance(data, dict):
            raise ValueError(
                f"{meta_path}: le document doit être un mapping YAML "
                f"(reçu : {type(data).__name__})."
            )

        repo = data.get("repo") or {}
        if not isinstance(repo, dict):
            raise ValueError(
                f"{meta_path}: le bloc 'repo' doit être un mapping "
                f"(reçu : {type(repo).__name__})."
            )
        if not repo.get("id") or not repo.get("category"):
            raise ValueError(
                f"{meta_path}: les champs 'repo.id' et 'repo.category' "
                "sont requis (contrat dsoxlab)."
            )

        infra_data = as_mapping(data.get("infra"), "infra", meta_path)
        hosts_data = as_mapping_list(infra_data.get("hosts"), "infra.hosts", meta_path)
        # Provider courant : env > contexte session > meta.yml (string OU
        # liste à 1 élément) > non résolu ("") si liste à plusieurs sans
        # choix — voir InfraDefinition.require_provider().
        provider, providers_available = _resolve_provider(
            infra_data.get("provider", "kvm"),
            context_provider=context_provider,
            meta_path=meta_path,
        )

        infra = InfraDefinition(
            provider=provider,
            providers_available=providers_available,
            network=infra_data.get("network", ""),
            cidr=infra_data.get("cidr", ""),
            hosts=[
                HostDefinition(
                    name=str(h["name"]),
                    # `or ""` plutôt que le défaut de .get() : une clé présente
                    # mais vide rend None, que str() transformerait en "None".
                    # ip est legacy/optionnel — calculé par Terraform en MVP
                    ip=str(h.get("ip") or ""),
                    distro=str(h.get("distro") or ""),
                    role=str(h.get("role") or ""),
                    ram_mb=as_int(h.get("ram_mb"), 1024, "infra.hosts[].ram_mb", meta_path),
                    vcpu=as_int(h.get("vcpu"), 1, "infra.hosts[].vcpu", meta_path),
                    disk_gb=as_int(h.get("disk_gb"), 10, "infra.hosts[].disk_gb", meta_path),
                    extra_disk_gb=as_int(
                        h.get("extra_disk_gb"), 0, "infra.hosts[].extra_disk_gb", meta_path
                    ),
                )
                for h in hosts_data
            ],
            providers=_provider_overrides(infra_data.get("providers"), meta_path),
        )

        sections = [
            SectionDefinition(
                id=str(s["id"]),
                title=s.get("title", ""),
                description=s.get("description", ""),
                labs=as_str_list(s.get("labs"), "sections[].labs", meta_path),
            )
            for s in as_mapping_list(data.get("sections"), "sections", meta_path)
        ]

        return cls(
            id=str(repo["id"]),
            category=str(repo["category"]),
            title=str(repo.get("title", "")),
            blog_url=str(repo.get("blog_url", "")),
            description=str(repo.get("description", "")),
            infra=infra,
            sections=sections,
            path=meta_path.parent.resolve(),
        )

    def lab_order(self) -> dict[str, int]:
        """Retourne un mapping ``<chemin-relatif>`` → index global pour le
        tri.

        L'index est croissant selon l'ordre des sections puis l'ordre des
        labs dans chaque section.
        """
        order: dict[str, int] = {}
        idx = 0
        for section in self.sections:
            for lab_path in section.labs:
                order[lab_path] = idx
                idx += 1
        return order
