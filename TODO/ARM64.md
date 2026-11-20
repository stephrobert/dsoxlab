# ARM64 — Support des labs DSOXLab sur macOS Apple Silicon

**Statut :** brief de cadrage, à valider et à implémenter  
**Cible :** Mac Apple Silicon (M1 à M5, selon disponibilité et compatibilité des systèmes)  
**Dépôt :** `stephrobert/dsoxlab`  
**Nature de cette PR :** document Markdown seulement — aucun code, configuration ni test modifié.

## 1. Vision et périmètre

Permettre à un utilisateur de Mac Apple Silicon de préparer ses certifications et de pratiquer les labs DSOXLab **sans Docker Desktop, UTM, Lima, Multipass, Colima, OrbStack ni Incus**.

Conserver l'architecture de provisioning **Terraform** que DSOXLab maîtrise déjà, et faire démarrer de vraies machines Linux ARM64 :

```text
Mac Apple Silicon (macOS arm64)
└── DSOXLab (Python + Ansible + pytest-testinfra)
    └── Terraform (darwin_arm64)
        └── dmacvicar/libvirt (darwin_arm64, à valider)
            └── libvirt / QEMU + HVF (hyperviseur Apple)
                ├── Ubuntu / Debian / AlmaLinux ARM64
                │   ├── SSH + cloud-init
                │   ├── exercices Linux et Ansible
                │   ├── Docker Engine Linux ARM64
                │   └── kind ou minikube (driver Docker), si lab compatible
                └── Disques virtuels pour LVM, partitions, quotas, etc.
```

Le **choix ferme est Terraform + libvirt**, pas un nouvel orchestrateur ni l'intégration de Lima/Multipass. La compatibilité complète de cette chaîne **n'est pas encore démontrée avec DSOXLab** ; le premier jalon est une preuve de faisabilité sur un vrai Mac Apple Silicon.

### Hors périmètre initial

- Réécriture de tous les catalogues ;
- support des Mac Intel ;
- exécution des labs directement dans le macOS hôte ;
- installation de Docker Desktop ;
- reprise des backends Incus sur Mac ;
- Kubernetes imbriqué dans plusieurs couches d'hyperviseurs ;
- remplacement des providers Linux KVM et Outscale existants.

Sur Linux, **conserver KVM et Incus** là où ils fonctionnent déjà : « oublier Incus » concerne la **cible macOS**, pas la suppression de son support Linux.

## 2. Ce qui existe déjà dans DSOXLab

Le moteur contient :

- `src/dsoxlab/infra/terraform.py` : sélection de provider, génération des variables et des workdirs, `terraform init/apply/destroy/output` ; le state reste dans le répertoire XDG du catalogue ;
- `src/dsoxlab/templates/terraform/kvm/` : infrastructure Terraform/libvirt, réseau libvirt NAT/DHCP, images QCOW2, cloud-init, firmware UEFI, domaines et disques supplémentaires ;
- `src/dsoxlab/templates/terraform/incus/` et `outscale/` : providers distincts sur Linux/cloud ;
- `src/dsoxlab/templates/cloud-init/` : configuration utilisateur et SSH adaptée aux distributions ;
- `src/dsoxlab/infra/libvirt.py` : opérations `virsh`, URL actuellement `qemu:///system`, ensemble des providers inspectables limité à `kvm` ;
- `docs/trainer.fr.md` et `docs/learner.fr.md` : parcours d'installation et contrats utilisateur à réviser après la preuve de faisabilité.

**Contrat Terraform à préserver** (voir `src/dsoxlab/templates/terraform/README.md`) : variables `hosts`, `network_name`, `network_cidr`, `provider_config` ; outputs `hosts` (FQDN → adresse joignable) et `bastion` ; éventuels outputs additionnels. Ne pas casser `dsoxlab start/provision/run/check/reset/clean`, les inventaires SSH/Ansible, les snapshots et les tests des autres providers.

Le catalogue `stephrobert/linux-dsoxlab-training` déclare actuellement les candidats `kvm`, `incus`, `outscale` et des hôtes AlmaLinux 10 / Ubuntu 24.04. Les exercices de base sont déjà indépendants de l'architecture CPU, mais le provisionnement existant est **orienté x86_64** : images cloud `amd64/x86_64` et topologie libvirt Linux.

## 3. Étude et exemples GitHub à exploiter

### A. Exemple macOS Apple Silicon le plus pertinent

**PR #1288** dans `dmacvicar/terraform-provider-libvirt`, « Add Tofu configuration for Ubuntu 24.04 VM on ARM64 for Apple Silicon » :

https://github.com/dmacvicar/terraform-provider-libvirt/pull/1288  
https://github.com/dmacvicar/terraform-provider-libvirt/pull/1288/files

Le fichier `examples/domain_with_cloudinit_macos.tf` proposé contient :

- `provider "libvirt"`, URI de session libvirt ;
- image Ubuntu 24.04 `noble-server-cloudimg-arm64.img` ;
- ressources `libvirt_volume`, `libvirt_cloudinit_disk`, `libvirt_domain` ;
- `type = "hvf"`, `type_arch = "aarch64"`, `type_machine = "virt"` ;
- chargeur UEFI ARM, disques virtio, réseau QEMU utilisateur et tentative de redirection SSH.

**Statut vérifié le 18 novembre 2026 : PR ouverte, non fusionnée.** Exemple de conception seulement, **pas une validation officielle ni un test DSOXLab réussi**.

Points à **ne pas recopier tels quels** : chemins Homebrew `Cellar/qemu/10.2.1/...` figés, mot de passe SSH de démonstration, option `ssh_pwauth: true`, commande manuelle de `hostfwd_add`, `null_resource` déclenché systématiquement par `timestamp()`, et toute dépendance à des ports constants.

### B. Terraform/libvirt ARM64 sous Linux

`jpartlow/kvm_automation_tooling` :

https://github.com/jpartlow/kvm_automation_tooling/blob/main/terraform/modules/vm/main.tf  
https://github.com/jpartlow/kvm_automation_tooling/blob/main/terraform/modules/vm/locals.tf

Prend en compte `aarch64`, la machine QEMU `virt`, le firmware UEFI, cloud-init et le CPU selon l'architecture invitée et hôte. Pour hôte Linux x86_64 + invité ARM64 : **émulation QEMU TCG**, pas accélération KVM ; attention aux configurations de CPU et au temps de boot. Ce dépôt est une référence technique à challenger, pas un backend macOS prêt à employer.

### C. Provider officiel / références

- https://github.com/dmacvicar/terraform-provider-libvirt/tree/main/examples
- https://github.com/dmacvicar/terraform-provider-libvirt/releases
- https://libvirt.org/macos.html
- https://www.qemu.org/docs/master/system/introduction.html
- https://cloud-images.ubuntu.com/noble/current/
- https://cloud.debian.org/images/cloud/

**Travail de vérification requis** : versions réellement disponibles et compatibles de Terraform, du provider libvirt (`darwin_arm64`), de libvirt, QEMU et HVF ; fonctionnement de `virsh` sur macOS ; limitations exactes du backend libvirt pour réseaux, storage pools, volumes et snapshots. La disponibilité de binaires ne prouve pas à elle seule que la chaîne marche de bout en bout.

## 4. Proposition de conception : provider dédié `macos` ou `qemu-hvf`

**Recommandation :** ajouter un template Terraform spécifique dans `src/dsoxlab/templates/terraform/<nom-à-fixer>/` plutôt que modifier le template `kvm` Linux à coups de conditions fragiles. Le nom final peut être `macos` ou `qemu-hvf` après validation du contrat existant.

- `kvm` reste libvirt + KVM sur Linux.
- Le nouveau provider vise libvirt + QEMU/HVF sur macOS.
- Les deux partagent autant que possible les modèles de variables, les templates cloud-init et les sorties, **sans confondre les implémentations de réseau**.
- Aucune modification automatique des catalogues tant que le test intégral n'est pas validé ; permettre ensuite la sélection par `dsoxlab use --provider <nom>` ou `DSOXLAB_PROVIDER=<nom>`.
- Ne pas déduire du seul `uname -m` qu'HVF est disponible ; diagnostiquer hôte macOS, puce ARM64, versions, libvirt et support d'accélération effectif.
- Préserver une seule source de vérité pour la configuration (variables du `meta.yml`, outputs et état Terraform), y compris au deuxième apply et au destroy.

### Images, CPU et firmware

- Support initial : **Ubuntu 24.04 ARM64** avec image cloud native.
- Ensuite Debian ARM64, AlmaLinux ARM64, et autres distributions effectivement utilisées par les labs.
- Architecture `aarch64`, machine `virt`, périphériques virtio compatibles, firmware **UEFI ARM64** ; découvrir le chemin du firmware de manière robuste au lieu de figer une version Homebrew.
- Valider Secure Boot, ACPI, pilotes réseau, disque et console pour chaque distribution ; un paramétrage valable pour Ubuntu peut différer sur AlmaLinux.
- Réutiliser cloud-init pour le compte `student`, la clé SSH du catalogue et la configuration initiale ; désactiver l'authentification par mot de passe, ne jamais coder de secret dans le HCL ni le state.
- Prévoir cache des images, images de base en lecture seule et disques de travail QCOW2 pour limiter l'espace et les temps de reprovisionnement.

### Stockage et disques

- Vérifier le stockage et les pools libvirt macOS (différences avec `/var/lib/libvirt/images`).
- Supporter `disk_gb`, `extra_disk_gb` et l'attachement stable de disques supplémentaires.
- Ne **pas supposer** que le disque supplémentaire a toujours le nom `/dev/vdb` : documenter les bus virtio/virtio-scsi et adapter le contrat des labs si nécessaire, sans le changer silencieusement.
- Tester partitionnement, systèmes de fichiers, LVM, swap et quotas avec **un vrai noyau invité**.

## 5. Point critique : réseau et accès SSH macOS

Sous Linux, le template KVM crée un réseau libvirt en bridge/NAT avec DHCP et des IP privées joignables depuis l'hôte. **Ne pas supposer que cette topologie est disponible sur macOS**.

Commencer par un POC **mono-VM** avec réseau utilisateur QEMU/SLIRP et **redirection d'un port TCP de `127.0.0.1` de l'hôte vers le SSH de la VM**. Puis étudier :

1. Comment libvirt/QEMU expose et maintient ce port forwarding avec HVF, de manière déclarative, sans commande QEMU monitor non gérée.
2. Comment DSOXLab traduit une machine `ubuntu-lfcs-1.lab` en `127.0.0.1:<port>` pour l'inventaire Ansible, les commandes SSH et pytest-testinfra.
3. Comment exposer l'information de connexion dans Terraform sans violer le contrat des outputs `hosts` (simple map IP). **Une extension du contrat est probablement nécessaire** : `ssh_host`, `ssh_port`, ou équivalent ; spécifier migration et compatibilité.
4. Comment allouer des ports distincts et stables entre plusieurs VMs/catalogues, empêcher les collisions et éviter toute écoute réseau sur `0.0.0.0` par défaut.
5. Comment communiquer entre VMs et faire fonctionner des labs multi-hôtes : SLIRP individuel peut ne **pas** fournir le réseau commun attendu. Étudier les capacités réelles de QEMU/libvirt sur macOS avant de promettre un bridge équivalent à Linux.
6. Comment conserver des réseaux isolés et nettoyer correctement les ressources après `destroy`.

**Critère bloquant** : les opérations `dsoxlab start/run/check/reset/clean`, Ansible et les connexions SSH doivent utiliser le bon endpoint de la bonne VM, sans manipulation manuelle de ports ou de fichiers `/etc/hosts` par l'apprenant.

## 6. Impacts dans le moteur DSOXLab

À examiner dans le code existant, sans développement au stade du brief :

- `infra/terraform.py` : nouvelle ressource machine, extraction du state, sélection de template, sorties, workdir, apply idempotent, destroy, diagnostics. Actuellement `_HOST_RESOURCE_TYPES` énumère `libvirt_domain` / `incus_instance` / `outscale_vm`, et le code comporte des chemins spécifiques à `kvm`.
- `infra/libvirt.py` : URI `qemu:///system` en dur par défaut, `INSPECTABLE_PROVIDERS = {"kvm"}`, accès `virsh` et privilèges `sudo` ; utiliser l'URI réellement sélectionnée et traiter les sessions/macOS.
- `snapshot` et `reset` : capacité réelle des snapshots pour les disques et pools macOS ; sinon fournir un mode de repli explicite sans annoncer une fonctionnalité absente.
- `doctor` et futur `doctor --fix` Ansible : les remèdes `apt`/`dnf` ne conviennent pas à macOS. Prévoir des prérequis macOS, distinction entre installer et vérifier, messages d'erreur précis, jamais `sudo apt` sur le Mac.
- `models/repo.py`, schémas YAML, sélection des providers, chemins XDG/app data macOS, documentation FR/EN et packaging `darwin_arm64` (plusieurs métadonnées actuelles annoncent uniquement Linux).
- inventaire SSH, ansible-runner, pytest-testinfra, fonctions d'attente SSH, localisation des clés, gestion d'erreurs et interruption.
- sûreté : ne pas exposer de service SSH au-delà de localhost par défaut ; nettoyage des ports/processus ; éviter les commandes shell interpolant des valeurs non sûres ; ne jamais écraser le state Linux existant.

## 7. Stratégie de compatibilité des catalogues

### Priorité 1 — Linux

Commencer par `stephrobert/linux-dsoxlab-training` :

- **`drill-essential-commands`** : `find`, grep, archives, liens, permissions, redirections ; `setup.yaml` Ansible ; cible initiale idéale.
- puis exercices fichiers/utilisateurs/paquets, services `systemd`, réseau, sécurité, LVM et disques.
- tester **Ubuntu**, puis **Debian**, puis **AlmaLinux/RHCSA** ; ne pas promettre une équivalence immédiate si certains lab reposent sur une image, un outil, un noyau ou un chemin de device propre à une architecture.
- séparer `runtime.type: shell` (aucune VM requise) et `runtime.type: vm` (provisionnement). Ne pas transformer tous les labs shell en VM inutilement.

### Priorité 2 — Ansible

- Inventaire généré par DSOXLab, SSH/port de la VM, `ansible-core` et collections ;
- `setup.yaml` et contrôles inchangés si possible ;
- tests de plusieurs distributions et de plusieurs hôtes ;
- vérification du temps de provisionnement et d'Ansible depuis macOS.

### Priorité 3 — Terraform

- Terraform CLI existe sur `darwin_arm64` et `linux_arm64` ;
- vérifier les providers **individuellement** (versions, packages ARM64, dépendances) ;
- conserver les labs `runtime: shell` qui n'exigent pas de VM ;
- valider les exercices de provisioning de VM et la gestion du state indépendamment du simple fait que la CLI Terraform se lance.

### Priorité 4 — Conteneurs

- **Aucun Docker Desktop**.
- Installer Docker Engine **dans la VM Linux ARM64** ; le client `docker` de macOS peut être optionnel et pointer via SSH vers la VM, si nécessaire à l'expérience apprenant.
- Tester `docker run`, images `linux/arm64`, build et Compose selon les besoins des labs.
- Auditer les images des catalogues : les images uniquement `amd64` ne fonctionneront pas nativement. Tester leurs variantes ARM64 ou prévoir un écart documenté ; ne pas présumer l'émulation x86 dans l'invité.

### Priorité 5 — Kubernetes, après les quatre premiers

- **kind** sur Docker Engine dans la VM Linux ARM64 comme première option, **minikube avec driver Docker** comme solution alternative ;
- pas de KVM imbriqué ni d'hyperviseur Kubernetes supplémentaire pour ce mode ;
- distinguer les labs compatibles kind (beaucoup de scénarios CKAD/CKA/CKS) de ceux qui exigent un vrai nœud, l'accès à l'OS, `kubeadm`, des opérations noyau ou une topologie spécifique ;
- dimensionner la RAM et les vCPU à partir de vrais tests. Une VM avec 6–8 Go peut constituer un point de départ exploratoire, **pas une garantie de performance ou de couverture**.

## 8. Validation sans posséder de Mac

### Sur le poste Linux x86_64 existant

Il est possible de tester l'**invité ARM64** sur Linux avec `qemu-system-aarch64` et **TCG**, y compris Ubuntu, cloud-init, SSH, Ansible, Docker Engine et les tests des labs. Sur un processeur x86_64, **KVM ne peut pas accélérer un invité ARM64** : ne pas confondre ce test avec la performance native HVF.

Étapes du prototype Linux :

1. télécharger une image cloud Ubuntu 24.04 ARM64 ;
2. démarrer la VM via QEMU TCG et firmware UEFI AArch64 ;
3. valider SSH, `uname -m = aarch64`, cloud-init, Ansible ;
4. installer Docker Engine dans l'invité et lancer une image `linux/arm64` ;
5. intégrer le lab `drill-essential-commands` (setup, actions de l'apprenant, check/score) ;
6. tester le cycle de provisionnement Terraform/libvirt côté Linux, en distinguant systématiquement les options QEMU et KVM ;
7. enregistrer les échecs de distribution, compatibilité périphériques et temps de démarrage.

### Sur GitHub Actions

- Exécuter les tests Python, schémas, génération HCL, validation Terraform et éventuellement lint de shell sur les runners macOS ARM64 **si disponibles et compatibles avec les besoins CI**.
- **Ne pas supposer** qu'un runner hébergé autorise QEMU/HVF et l'accélération matérielle nécessaires. Les tests réels doivent être effectués sur un Mac Apple Silicon dédié ou équivalent ayant les capacités vérifiées.
- Ajouter des jobs Mac sans ralentir ni bloquer les CI Linux existantes tant que le support n'est pas mature.

### Validation finale sur un vrai Mac

- Louer temporairement un Mac mini Apple Silicon (par exemple Scaleway) ou emprunter une machine ; vérifier au préalable les conditions d'accès, la possibilité réelle d'utiliser HVF/libvirt et les limitations éventuelles de l'hébergeur.
- Tester au minimum un M1/M2 16 Go si disponible ; **32 Go n'est pas un prérequis** pour un lab Linux simple. Les chiffres de performance publiés avec des protocoles différents ne remplacent pas un benchmark DSOXLab.
- Mesurer explicitement la première création (téléchargement inclus), le démarrage après cache, le reboot, l'accès SSH, le setup, le check, le destroy, le comportement multi-VM, CPU/RAM/SSD.
- L'objectif « VM en quelques secondes » reste une **hypothèse à mesurer** (cache chaud, machine et image précisées), pas une promesse produit.

## 9. Ordre de réalisation — jalons et critères go/no-go

### J0 — étude de faisabilité (aucun changement de contrat)

- Identifier une combinaison maintenue Terraform / provider libvirt / libvirt / QEMU / macOS arm64.
- Prouver `virsh` + domaine `hvf`, UEFI ARM64, image Ubuntu 24.04 et SSH depuis l'hôte Mac.
- Documenter les fonctionnalités absentes et les contournements éventuels.

**No-go** si libvirt ne peut pas gérer de manière reproductible un domaine HVF avec stockage et SSH. Ne pas développer un nouveau backend QEMU sans décision explicite après ce résultat.

### J1 — prototype Terraform reproductible

- `terraform init/plan/apply/destroy` sur Mac et un second `apply` sans dérive non voulue.
- Cloud-init à clé SSH, QCOW2, firmware sans chemin figé, redirection SSH stable.
- Une VM Ubuntu ARM64 et logs de diagnostic utiles.

### J2 — intégration DSOXLab mono-VM

- Un provider dédié sélectionnable, inventaire/SSH correct, `start/run/check/clean` réels.
- Validation du lab `drill-essential-commands` **avec le même score attendu** qu'en Linux.
- Aucune régression sur les providers existants.

### J3 — multi-VM et distributions

- Ubuntu, Debian, puis AlmaLinux ; disques secondaires ; LVM ; systemd ;
- SSH stable de plusieurs VMs, communication inter-VM si requise, snapshots/restore si pris en charge ;
- tests des catalogues Linux et Ansible.

### J4 — Docker et Terraform

- Docker Engine ARM64 dans une VM Linux ;
- compatibilité des labs conteneurs et Terraform, avec matrice des images/providers ;
- diagnostics exploitables si image architecture indisponible.

### J5 — Kubernetes (exploratoire)

- kind ou minikube Docker dans une VM Linux ;
- tests représentatifs de CKAD et CKA, puis des scénarios CKS compatibles ;
- matrice de ce qui exige de vraies VM/nœuds et dépasse le périmètre kind.

## 10. Livrables attendus et critères d'acceptation

1. **Matrice de compatibilité** des catalogues/labs : architecture, distribution, type de runtime, ressources, dépendances système, verdict (validé / non compatible / non testé).
2. **Prototype Terraform macOS** documenté avec versions exactes, chemins découverts, plan/apply/destroy reproductibles, aucun mot de passe hardcodé.
3. **Stratégie réseau** validée sur mono-VM, puis multi-VM, avec retour d'information exact vers SSH/Ansible/testinfra ; définition formelle de l'évolution de l'output `hosts` si nécessaire.
4. **Matrice de tests Linux x86_64→ARM64 TCG / Mac ARM64→HVF**, sans confondre les deux.
5. **Documentation d'installation et de diagnostic** macOS pour l'apprenant, en français et en anglais.
6. **Découpage en petites PR** : socle macOS → intégration DSOXLab → distributions → Docker → Kubernetes.
7. **Non-régression** : tests existants Linux KVM/Incus/Outscale, stabilité de l'état Terraform, absence de suppression involontaire, aucune dégradation des labs existants.

### Principes non négociables

- **Terraform reste le moteur de provisionnement.**
- **libvirt + QEMU/HVF** est la piste prioritaire à valider sur macOS.
- **Pas d'Incus, Docker Desktop, Lima, Multipass, UTM ou OrbStack imposés sur Mac.**
- **Pas de code source modifié dans la PR du présent brief.**
- Les affirmations « fonctionne sur Mac », « tous les labs » et « VM créée en quelques secondes » ne deviennent publiques **qu'après vérification de bout en bout**, avec matériel et versions documentés.

## 11. Références techniques

- PR expérimentale Terraform/libvirt/macOS ARM64 : https://github.com/dmacvicar/terraform-provider-libvirt/pull/1288
- Exemples provider libvirt : https://github.com/dmacvicar/terraform-provider-libvirt/tree/main/examples
- Module Terraform compatible invité ARM64 : https://github.com/jpartlow/kvm_automation_tooling/blob/main/terraform/modules/vm/main.tf
- Logique architecture/firmware Linux : https://github.com/jpartlow/kvm_automation_tooling/blob/main/terraform/modules/vm/locals.tf
- libvirt sur macOS : https://libvirt.org/macos.html
- Images Ubuntu : https://cloud-images.ubuntu.com/noble/current/
- Images Debian : https://cloud.debian.org/images/cloud/
- Catalogue Linux : https://github.com/stephrobert/linux-dsoxlab-training
- Contrat Terraform DSOXLab : https://github.com/stephrobert/dsoxlab/blob/main/src/dsoxlab/templates/terraform/README.md
