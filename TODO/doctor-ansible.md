# Brief — Refonte de `dsoxlab doctor --fix` avec un playbook Ansible unique

**Statut :** à implémenter (document de cadrage uniquement)  
**Dépôt :** `stephrobert/dsoxlab`  
**Périmètre de cette PR :** ajout de ce brief dans `TODO/`, **sans changement de code ni de comportement**.

## 1. Problème constaté

Aujourd'hui, `dsoxlab doctor` détecte des prérequis manquants et affiche des commandes à copier. Le chemin `doctor --fix` existe déjà : le Python construit un plan puis génère un playbook Ansible à partir de commandes shell conservées dans la table des remèdes.

Ce mécanisme duplique la logique d'installation et conserve les défauts des commandes d'origine. Exemple constaté : certaines instructions `sudo apt install ...` (git, KVM, OVMF, Incus) ne sont pas précédées d'une mise à jour de l'index APT. Sur une machine fraîche, elles peuvent échouer.

**Décision visée :** garder Python pour piloter et diagnostiquer, mais confier à **un playbook Ansible versionné, fixe et déclaratif** la mise en conformité du poste. Python ne doit plus générer de commandes d'installation ni de playbook shell à partir du diagnostic.

## 2. Contrat de la CLI

| Commande | Comportement attendu |
| --- | --- |
| `dsoxlab doctor` | Diagnostic et conseils uniquement ; aucune modification du système. |
| `dsoxlab doctor --fix` | Installer/configurer les prérequis KVM et libvirt requis pour les labs VM, ainsi que leur socle indispensable (paquets, firmware EFI si nécessaire, services, pool, groupes). |
| `dsoxlab doctor --fix --clients` | Même socle KVM, **plus Docker et Incus**. |
| `dsoxlab doctor --fix --all` | Tous les composants pris en charge : socle KVM, Docker, Incus, Terraform et dépendances applicables (dont Ansible et collections nécessaires). |

- `--clients` et `--all` sont des **profils de remédiation**, et non des commandes arbitraires à exécuter.
- Conserver `--strict`, `--json` et `--yes` selon leurs contrats existants. Ne pas mêler `--json` et une exécution de correctifs qui écrirait du bruit non JSON sur stdout.
- Montrer à l'utilisateur le plan avant de modifier le système ; demander confirmation, sauf `--yes`. Le mot de passe sudo peut rester requis : « sans recopier de commandes » ne signifie pas « sans consentement ni élévation de privilèges ».
- La sélection des composants doit être explicite et déterministe, indépendante du contenu fortuit du catalogue ; les prérequis propres au catalogue restent des contrôles complémentaires.

## 3. Bootstrap obligatoire AVANT le playbook

Un playbook ne peut pas installer son propre moteur si celui-ci est absent.

1. Vérifier la disponibilité effective d'`ansible-playbook` et d'`ansible-galaxy`, ainsi que la version d'`ansible-core`. Vérifier le chemin réellement exécutable, y compris lorsqu'Ansible vit dans l'environnement isolé de `uv tool install dsoxlab` : ne pas présumer que son binaire figure dans le `PATH` global.
2. Si le moteur est absent ou incompatible, réutiliser/préserver le mécanisme de bootstrap Python déjà disponible (`_installer_ansible`) ou le mécanisme d'installation du paquet ; **ne pas lancer le playbook avant que le moteur soit fonctionnel**.
3. Identifier les collections nécessaires aux playbooks des catalogues actifs via `requirements.yml` et `services/collections_ansible.py`. Installer uniquement les dépendances nécessaires, en **respectant les versions bornées par les catalogues** ; ne pas remplacer ces contraintes par la dernière version du moment.
4. Le playbook d'installation du poste doit, autant que possible, utiliser les modules `ansible.builtin` pour ne pas dépendre d'une collection externe avant son bootstrap.
5. En cas d'échec (Ansible absent et bootstrap impossible, collections incompatibles, manque de réseau), s'arrêter avec une cause et une action compréhensibles ; ne pas considérer l'environnement prêt.

## 4. Un playbook déclaratif, aucune génération de commandes

- Stocker **un seul playbook d'installation du poste** dans le dépôt et l'embarquer dans le paquet Python distribué.
- Python transmet le profil sélectionné et le contexte minimal nécessaire, puis lance ce playbook. Il **n'assemble pas** des fragments de shell en YAML.
- Utiliser `gather_facts`, `ansible_facts`, `package_facts`, `service_facts`, les conditions et les modules natifs pour adapter l'exécution.
- Privilégier `ansible.builtin.apt`, `dnf`, `package`, `systemd_service`, `user`, `file`, `get_url`, etc. Les commandes impératives (`virsh`, initialisation Incus...) ne sont admises qu'en l'absence de module adapté, avec garde préalable et validation de l'état obtenu.
- Sur Debian/Ubuntu et dérivées : le cache APT doit être actualisé **avant la première installation** et **après l'ajout de tout nouveau dépôt**. Éviter les `apt update` inutiles à chaque tâche.
- Pour Docker et Terraform, utiliser des dépôts officiels et leurs signatures ; ne jamais ajouter de dépôt sans vérification de la distribution supportée. Préserver les configurations préexistantes quand elles conviennent.
- Réaliser la gestion des groupes de l'utilisateur réel, pas de `root` sous `become`. Expliquer qu'une nouvelle session peut être indispensable.
- KVM exige des contrôles supplémentaires au-delà des facts génériques (`/dev/kvm`, permissions, virtualisation imbriquée, libvirt, firmware EFI). Si la virtualisation n'est pas disponible, **le signaler** : un playbook ne peut pas activer à lui seul un réglage BIOS ou un hyperviseur hôte.
- Les plateformes non prises en charge doivent être signalées proprement ; en particulier, ne pas présumer qu'Incus est disponible dans les dépôts de base RHEL/AlmaLinux. Ne pas exécuter une recette Ubuntu sur AlmaLinux, ni l'inverse.

## 5. Sûreté et reproductibilité

- **Idempotence :** une deuxième exécution réussie n'apporte pas de changement inutile.
- **Moindre modification :** ne pas reconfigurer ou remplacer un Docker, un Incus, un pool libvirt ou un dépôt déjà opérationnel sans nécessité ; ne pas forcer de mise à niveau générale du système.
- **Sécurité :** les groupes `docker` et `incus-admin` confèrent des privilèges élevés ; les annoncer explicitement dans le plan. Ne jamais stocker de mot de passe sudo ni le passer en argument en clair.
- **Traçabilité :** rendre visibles les tâches modifiées, ignorées, échouées et les actions différées (reconnexion / redémarrage).
- **Échec franc :** une étape indispensable en erreur bloque les étapes qui en dépendent ; aucun faux succès. Ne pas confondre échec et état impossible à mesurer.
- **Vérification :** relancer les contrôles de Doctor après les modifications et garder un code de retour exploitable pour `--strict`. Distinguer les contrôles satisfaits, les prérequis encore manquants et les effets nécessitant une reconnexion.
- Prévoir un mode de prévisualisation sans modification (plan lisible et, si pertinent, contrôle Ansible en `--check`), sans annoncer de succès que le mode `--check` ne peut pas prouver.

## 6. Cibles et scénarios de test

Valider au minimum les profils **défaut**, **`--clients`**, **`--all`**, sur les familles :

- Ubuntu 24.04 / dérivé Pop!_OS, Debian 13 ;
- AlmaLinux 10 / famille RHEL, ainsi que Fedora si officiellement supportée ;
- WSL2 Linux lorsque KVM et les services nécessaires sont réellement disponibles ; comportement explicite sinon.

Scénarios obligatoires :

1. Machine neuve, **index APT absent** : les premières installations réussissent après actualisation du cache.
2. Machine déjà conforme : la deuxième exécution ne change rien.
3. `--clients` : Docker et Incus sont configurés uniquement là où leur installation est supportée ; absence de réinstallation inutile.
4. `--all` : Terraform provient de la source prévue, Docker/Incus/KVM sont couverts, et les dépendances Ansible sont contrôlées.
5. `ansible-core` absent / binaire hors `PATH` / collection manquante ou bornée : bootstrap correct ou erreur intelligible, sans cascade.
6. Absence de `/dev/kvm`, virtualisation imbriquée indisponible, distro non supportée : diagnostic honnête, sans changement destructeur.
7. Droits sudo absents, exécution non interactive, plan refusé, mode `--yes`, contrôles `--strict` et `--json`.
8. L'ajout de l'utilisateur aux groupes est annoncé comme effet différé et ne se traduit pas par un faux « prêt » immédiat.
9. Tests de non-régression de `doctor`, `start`, `run` et des catalogues existants.

## 7. Éléments existants à prendre en compte

- `src/dsoxlab/cli/diagnostic.py` : CLI, `_installer_ansible`, confirmation, remesure, exécution du playbook actuel.
- `src/dsoxlab/services/remediation.py` : plan et génération actuelle d'un playbook depuis les commandes shell ; logique à remplacer.
- `src/dsoxlab/services/doctor_controles/remedes.py` : table des remèdes et problème des `apt install` sans mise à jour préalable.
- `src/dsoxlab/services/collections_ansible.py` : exigences et état des collections des catalogues.
- `pyproject.toml` : dépendance explicite à `ansible-core`.

## 8. Livrables attendus de la future implémentation

1. Un playbook Ansible statique, maintenu et distribué avec DSOXLab.
2. Une orchestration CLI/bootstrap compatible avec les trois profils définis.
3. Une migration maîtrisée hors de la génération dynamique de commandes d'installation.
4. Des tests unitaires et de bout en bout sur machines propres et déjà configurées.
5. Une documentation utilisateur FR/EN correspondant au comportement réellement testé.

**Hors périmètre de la présente PR :** modifier des sources Python, créer le playbook, lancer des installations, changer les tests ou merger du code. Cette PR demande uniquement la validation du cadrage.
