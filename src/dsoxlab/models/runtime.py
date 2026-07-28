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

    roles: dict[str, str] = field(default_factory=dict)
    """Hôtes additionnels utilisés simultanément par le lab, par rôle —
    ex. ``{"server": "alma-rhcsa-2.lab"}``. Chaque rôle devient un groupe
    Ansible ``lab_<role>`` dans l'inventory du ``setup.yaml`` /
    ``solution.yaml`` / ``cleanup.yaml``, en plus de ``lab_target`` (l'hôte
    primaire, où tournent les tests). Vide = lab mono-hôte (défaut). Les FQDN
    doivent être déclarés dans ``meta.yml: infra.hosts[]`` et provisionnés."""

    def label(self, lang: str = "en") -> str:
        """Retourne le label dans la langue demandée, fallback EN."""
        if lang == "fr" and self.label_fr:
            return self.label_fr
        return self.label_en or self.name


@dataclass
class Service:
    """Un service conteneurisé dont un lab a besoin le temps de l'exercice.

    Certains labs ``shell`` ciblent une API que le poste n'héberge pas (un
    émulateur de cloud, une base de données, un registre). Plutôt que d'imposer
    à l'apprenant un ``docker run`` manuel dans le scénario, le lab déclare ici
    le conteneur à lancer, et dsoxlab le démarre avant ``run``/``check`` et
    l'arrête à ``destroy``/``clean``.

    **dsoxlab reste agnostique du domaine.** Il lance **l'image que le lab
    déclare**, sur les ports que le lab déclare : il ne connaît ni le cloud, ni
    le produit émulé. Toute la spécificité vit dans le ``lab.yaml`` du dépôt
    fournisseur, jamais dans ce code.
    """

    name: str
    """Nom court du service, unique dans le lab (ex. ``db``, ``cloud``).

    Le conteneur est nommé ``dsoxlab-<repo_id>-<name>`` pour éviter toute
    collision entre dépôts de labs."""

    image: str
    """Image du conteneur, tag compris (ex. ``postgres:16``). REQUIS."""

    ports: list[str] = field(default_factory=list)
    """Publications de ports au format Docker ``hôte:conteneur`` (ex.
    ``["4566:4566"]``). Passées telles quelles en ``-p``."""

    run_args: list[str] = field(default_factory=list)
    """Arguments bruts ajoutés au ``docker run`` (ex.
    ``["-v", "/var/run/docker.sock:/var/run/docker.sock"]``). Le lab en assume
    le sens ; dsoxlab ne les interprète pas."""

    env: dict[str, str] = field(default_factory=dict)
    """Variables d'environnement du conteneur, passées en ``-e NOM=valeur``."""

    ready_tcp: int = 0
    """Port **de l'hôte** à sonder jusqu'à ce qu'il accepte une connexion.
    0 = pas d'attente TCP.

    C'est bien le port publié, celui de gauche dans ``ports``, pas celui du
    conteneur : la sonde ouvre une connexion sur ``127.0.0.1``. La distinction
    n'a l'air de rien tant que les deux coïncident, et devient un piège dès
    qu'on remappe pour cohabiter — avec ``ports: ["8201:8200"]``, un
    ``ready_tcp: 8200`` sonderait le 8200 de l'hôte, donc **le service de
    quelqu'un d'autre**, et le déclarerait prêt. Écrire ``ready_tcp: 8201``."""

    ready_exec: list[str] = field(default_factory=list)
    """Commande de SONDE jouée dans le conteneur jusqu'à ce qu'elle réussisse.

    ``ready_tcp`` ne suffit pas dès que le port est publié : Docker installe un
    proxy sur le port de l'hôte **au moment du ``run``**, et ce proxy accepte
    les connexions avant que le service écoute — vérifié, une connexion réussit
    sur un ``-p 8299:1234`` dont le conteneur n'écoute nulle part. La sonde TCP
    répond donc « prêt » quasi immédiatement, et ce qui suit part trop tôt.

    Cette commande, elle, s'exécute **dans** le conteneur et interroge le
    service lui-même (``vault status``, ``pg_isready``, ``redis-cli ping``…).
    Elle est réessayée jusqu'à ``ready_timeout``. Elle doit être **sans effet** :
    c'est une question posée au service, pas une initialisation — celle-ci vit
    dans ``post_start``, qui ne tourne qu'une fois la sonde satisfaite."""

    ready_timeout: int = 90
    """Délai maximum, en secondes, pour que le service devienne disponible.

    Vaut pour ``ready_tcp`` et ``ready_exec``."""

    post_start: list[list[str]] = field(default_factory=list)
    """Commandes à jouer DANS le conteneur une fois le service prêt.

    Un conteneur qui démarre est rarement un service utilisable : une base veut
    son schéma, un coffre veut ses secrets, un registre veut son dépôt. Sans ce
    crochet, cette initialisation retombait sur un script bash à la racine du
    lab, que l'apprenant devait penser à lancer — donc un lab qui se skippe ou
    qui échoue selon l'humeur du poste.

    Chaque entrée est un **argv** exécuté par ``docker exec``, sans shell : pas
    d'expansion, pas de pipe, pas de redirection. Le ``lab.yaml`` peut l'écrire
    en liste (``["vault", "kv", "put", "secret/x", "k=v"]``) ou en chaîne
    (``vault kv put secret/x k=v``), découpée à la manière du shell.

    **Ces commandes sont rejouées à chaque démarrage**, y compris quand le
    conteneur tournait déjà : c'est ce qui garantit un état de départ identique
    d'un lab à l'autre. Elles doivent donc être idempotentes, au même titre
    qu'un ``setup.yaml``.

    dsoxlab ne les interprète pas : il ne sait pas ce qu'est un secret ni un
    schéma, il exécute ce que le lab déclare."""


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

    session: str = "target"
    """Où s'ouvre la session interactive de ``dsoxlab run``.

    - ``target`` (défaut) : session SSH sur ``targets[].host``. L'apprenant
      travaille **dans** la machine, cas des labs système.
    - ``local`` : sous-shell sur le poste, à la racine du dépôt. Le poste est
      alors le poste de pilotage : l'apprenant y écrit son code et lance ses
      commandes vers les hôtes du lab, qui restent provisionnés et ciblés par
      le ``setup.yaml``.

    Ce choix n'a de sens que pour ``runtime: vm`` : un lab ``shell`` ouvre
    déjà un sous-shell local, dans son ``workdir``.

    Sans ce champ, un lab piloté depuis le poste déposait l'apprenant en SSH
    sur un hôte qui ne contient ni le dépôt ni ses outils."""

    # ── Pour runtime: shell ───────────────────────────────────────────
    workdir: str = "challenge/work"
    """Chemin relatif du répertoire de travail créé par ``dsoxlab run``.

    Ignoré pour ``runtime: vm``.
    """

    fixtures: list[str] = field(default_factory=list)
    """Liste de fichiers de ``fixtures/`` à copier vers ``workdir``.

    Chemins relatifs depuis ``<lab>/fixtures/``. Ignoré pour ``vm``.
    """

    services: list["Service"] = field(default_factory=list)
    """Services conteneurisés dont le lab a besoin le temps de l'exercice.

    Démarrés par ``run``/``check``, arrêtés par ``destroy``/``clean``, affichés
    par ``status``. Vide = aucun service (défaut). Voir :class:`Service`."""

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
