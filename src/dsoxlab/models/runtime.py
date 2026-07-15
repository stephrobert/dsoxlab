"""Modèles de données pour la configuration runtime.

Le runtime ``vm`` est **agnostique du provider** d'infrastructure : un
même lab tournera sur KVM, Proxmox, AWS, GCP ou Azure sans modification,
le provider étant sélectionné dans le ``meta.yml: infra.provider``.

Les types ``kvm`` et ``incus`` sont conservés pour rétro-compatibilité
des anciens labs ; la cible est ``vm``.
"""

from dataclasses import dataclass, field
from enum import Enum


class RuntimeType(str, Enum):
    """Type de runtime déclaré par un lab."""

    SHELL = "shell"
    """Atelier shell-local — exécuté sur le poste de l'apprenant.

    Pour ce type, ``RuntimeConfig.workdir`` et ``RuntimeConfig.fixtures``
    pilotent la préparation déclarative (création du répertoire de
    travail + copie de fixtures). Aucun script bash n'est invoqué.
    """

    VM = "vm"
    """VM accessible en SSH — provider sélectionné par meta.yml.

    Pour ce type, ``setup.yaml`` et ``cleanup.yaml`` (playbooks Ansible)
    sont obligatoires à la racine du lab.
    """

    INCUS = "incus"
    """Conteneur Incus (rétro-compat, à éviter dans les nouveaux labs)."""

    KVM = "kvm"
    """Alias historique de ``vm`` quand le provider est KVM (rétro-compat)."""


@dataclass
class Target:
    """Une cible d'exécution proposée par un lab ``runtime: vm``.

    Chaque lab ``runtime: vm`` déclare une **liste** de cibles dans
    ``runtime.targets``. L'apprenant choisit explicitement laquelle
    utiliser via ``--target <name>`` (ou via le contexte
    ``dsoxlab use --target``). Cela permet de pratiquer le même lab
    sur plusieurs distributions (ex. RHEL puis Ubuntu pour LFCS).
    """

    name: str
    """ID court utilisé en CLI — ex. ``rhel``, ``ubuntu``, ``suse``."""

    host: str
    """FQDN déclaré dans ``meta.yml: infra.hosts[].name``."""

    label_en: str = ""
    """Description courte (anglais) affichée par ``dsoxlab show``."""

    label_fr: str = ""
    """Description courte (français)."""

    def label(self, lang: str = "en") -> str:
        """Retourne le label dans la langue demandée, fallback EN."""
        if lang == "fr" and self.label_fr:
            return self.label_fr
        return self.label_en or self.name


@dataclass
class RuntimeConfig:
    """Configuration runtime d'un lab — déclarée dans ``lab.yaml``."""

    type: RuntimeType

    # ── Pour runtime: vm (et alias kvm/incus) ─────────────────────────
    targets: list[Target] = field(default_factory=list)
    """Cibles d'exécution proposées. Au moins une cible obligatoire pour
    ``runtime: vm``. Le ``setup.yaml``/``cleanup.yaml``/``solution.yaml``
    cible le groupe Ansible ``lab_target`` que dsoxlab résout en
    injectant le seul host correspondant à la target choisie."""

    default: str = ""
    """Nom de la target par défaut (doit matcher un ``targets[].name``).

    Si vide, dsoxlab prend la première target déclarée."""

    snapshot_required: bool = False
    """Si True, ``dsoxlab run`` prend un snapshot avant le ``setup.yaml``
    pour permettre un rollback simple via ``dsoxlab restore``."""

    # ── Pour runtime: shell ───────────────────────────────────────────
    workdir: str = "challenge/work"
    """Chemin relatif du répertoire de travail créé par ``dsoxlab run``.

    Ignoré pour ``runtime: vm``.
    """

    fixtures: list[str] = field(default_factory=list)
    """Liste de fichiers de ``fixtures/`` à copier vers ``workdir``.

    Chemins relatifs depuis ``<lab>/fixtures/``. Ignoré pour ``vm``.
    """

    # ── Rétro-compat ──────────────────────────────────────────────────
    topology: str = "local"
    """Champ historique conservé pour rétro-compat. À déprécier."""

    # ── Helpers ───────────────────────────────────────────────────────

    def target(self, name: str | None = None) -> Target | None:
        """Retourne la Target par son nom, ou la default, ou None.

        Ordre de résolution :
        1. ``name`` si fourni et trouvé.
        2. ``self.default`` si défini et trouvé.
        3. ``self.targets[0]`` (la première) si la liste est non vide.
        4. None.
        """
        if name:
            for t in self.targets:
                if t.name == name:
                    return t
            return None  # nom explicite mais introuvable → erreur explicite côté appelant
        if self.default:
            for t in self.targets:
                if t.name == self.default:
                    return t
        return self.targets[0] if self.targets else None
