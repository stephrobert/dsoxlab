# Journal des modifications

**Langue :** [English](./CHANGELOG.md) · [Français](./CHANGELOG.fr.md)

Toutes les modifications notables du projet sont documentées dans ce fichier.

Le format s'appuie sur [Keep a Changelog](https://keepachangelog.com/fr/1.1.0/),
et le projet suit le [versionnage sémantique](https://semver.org/lang/fr/).

## [Non publié]

## [0.1.12] - 2026-07-17

### Corrigé

- **La provenance de build n'atteste plus un fichier qui n'est pas publié.**
  `uv build` dépose un `dist/.gitignore` d'un octet, et
  `attest-build-provenance` inclut les fichiers cachés dans son glob (au
  contraire du glob shell qui alimente `gh release create`) : l'attestation de
  la v0.1.11 listait donc `.gitignore` à côté de la wheel et du sdist. Les
  artefacts sont désormais nommés explicitement. Anodin en soi, mais une
  attestation doit nommer exactement ce qui est publié, rien de plus.

## [0.1.11] - 2026-07-17

### Corrigé

- **Un `lab.yaml` ou un `meta.yml` malformé pouvait faire planter la CLI au lieu
  d'être ignoré.** `discovery/scanner.py` rattrape `(KeyError, ValueError,
  yaml.YAMLError)` et ignore le lab fautif avec un warning — mais les parsers
  pouvaient lever hors de ce contrat, et l'exception remontait alors en
  traceback brut sur une commande sans rapport (`list-labs`, `progress`…).
  Comme un `lab.yaml` provient d'un *dépôt fournisseur de labs*, c'est l'entrée
  non fiable du moteur. Cinq cas, tous trouvés par les nouveaux harnais de
  fuzzing :
  - un `lab.yaml` **vide** (ou réduit à des commentaires) → `AttributeError`,
    `yaml.safe_load` rendant `None` ;
  - un document dont la **racine est une liste ou un scalaire**, dans les deux
    fichiers ;
  - **`runtime: vm`** écrit à la place du bloc `runtime:`, et
    `runtime.targets: true` → `AttributeError` / `TypeError` ;
  - **`infra.hosts:` écrit en mapping** au lieu d'une liste → `TypeError` sur
    `h["name"]`, l'itération portant sur les clés ;
  - une **clé présente mais vide** comme `vcpu:` ou `bloc:` → `int(None)` lève
    `TypeError`, `.get("vcpu", 1)` rendant `None` et non le défaut quand la clé
    existe.

  Chacun de ces cas lève désormais un `ValueError` portant le chemin du fichier
  et le champ fautif : le lab est ignoré et le reste du catalogue se charge. Un
  `ip:` vide ne donne plus non plus la chaîne littérale « None ».

### Ajouté

- **Des harnais de fuzzing sur le contrat YAML non fiable** (`fuzz/`), rejoués
  en régression courte dans la CI. Ils vérifient le *contrat* — toute exception
  hors de `(KeyError, ValueError, yaml.YAMLError)` fait échouer le run — plutôt
  que de simplement exécuter les parsers. Livrés avec un corpus de graines et un
  dictionnaire libFuzzer des mots-clés du contrat ; `uv sync --group fuzz`
  installe atheris (tenu hors du groupe `dev`).
- **`actionlint` et `poutine` en gates CI**, aux côtés du job zizmor existant,
  tous deux installés depuis un binaire de release dont le SHA-256 est vérifié
  contre les checksums publiés. `poutine --fail-on-violation` en fait une gate,
  pas un rapport. Les jobs lourds attendent désormais les trois scanners.
- **`step-security/harden-runner`** en premier step de chaque job
  (`egress-policy: audit`), et un `.poutine.yml` qui acquitte trois actions
  vérifiées à la main par leur purl, sans désactiver la règle.
- **La provenance de build attachée à la Release GitHub** sous le nom
  `provenance.intoto.jsonl`. L'attestation existante est enregistrée sur l'API
  d'attestation de GitHub, qui est un artefact *distinct* de l'asset de release
  qu'attend le contrôle Signed-Releases d'OpenSSF Scorecard.

## [0.1.10] - 2026-07-16

### Corrigé

- **Les scores étaient faux sur les labs dont les données contiennent
  « ERROR », « PASSED » ou « FAILED »** : `_parse_counts()` comptait les
  occurrences de ces mots dans la sortie brute de pytest, messages d'assertion
  compris. Un lab qui filtre des lignes `ERROR` (`l1-get-help`,
  `l1-grep-regex`, `l1-redirections-pipes`, `l3-service-diagnose`…) gonflait son
  propre total — `dsoxlab check` annonçait `1/5` pour un lab de 4 tests, et le
  score de l'apprenant s'en trouvait sous-évalué (20 pts au lieu de 25). La
  ligne de résumé que pytest produit lui-même fait désormais foi, avec un repli
  ancré sur les node-ids.

## [0.1.9] - 2026-07-16

### Corrigé

- **KVM : deux dépôts de labs ne se disputent plus le même volume de base.**
  L'image de base libvirt s'appelait `dsoxlab-base-<distro>.qcow2`, sans
  l'identifiant du dépôt. Or le pool libvirt est *partagé* entre tous les
  dépôts, alors que chacun garde son **propre** state Terraform. Le second
  dépôt à provisionner sur une distro déjà utilisée par un autre échouait donc
  sur `storage volume 'dsoxlab-base-alma10.qcow2' exists already` : son state
  ignorait simplement le volume créé par le premier. Concrètement,
  `linux-dsoxlab-training` (alma10) bloquait `ansible-training` (alma10) sur la
  même machine. Le volume devient `dsoxlab-base-<repo-id>-<distro>.qcow2` : les
  catalogues cohabitent vraiment, comme le contrat le promet déjà avec leurs
  réseaux libvirt séparés. L'image cloud est dupliquée par dépôt (sparse, ~600 Mo
  à 2 Go) : c'est le prix de l'isolation.

  Terraform reçoit une variable `repo_id`, déclarée par les trois providers
  (`kvm`, `incus`, `outscale`) puisque les tfvars sont communs ; seul `kvm` crée
  un volume local, lui seul était touché. Incus tire des alias d'images publiques
  et Outscale utilise des AMI : aucune collision possible.

  **Impact à la mise à jour.** Sur un dépôt provisionné en ≤ 0.1.8, le prochain
  `dsoxlab provision` renomme le volume de base, ce que Terraform traite comme un
  *remplacement* : les VMs sont recréées. Rien n'est perdu (les VMs de labs sont
  jetables par conception, et le travail de l'apprenant vit dans le dépôt,
  `challenge/`, jamais sur la VM), mais l'état des labs en cours sur les VMs
  disparaît. Enchaîner `dsoxlab destroy` puis `dsoxlab provision` pour un cycle
  propre.

## [0.1.8] - 2026-07-16

### Corrigé

- **Plus de traceback Python quand l'infrastructure n'est pas provisionnée** :
  un apprenant qui lançait un lab VM avant `dsoxlab provision` (premier
  lancement, ou après un `destroy`) recevait un `ValueError: target_fqdn '...'
  n'est pas dans la liste des hôtes connus : []` brut. C'est une situation
  normale, pas un bug — `build_inventory()` lève désormais
  `InfraNotProvisioned`, que la CLI rend en une phrase actionnable (EN+FR)
  indiquant de lancer `dsoxlab provision`. Un point d'entrée `main()` l'attrape
  pour toutes les commandes : aucune ne peut plus afficher de traceback pour ça.
- **`check` n'enregistre plus un 0/100 en l'absence d'infrastructure** : pytest
  tourne en sous-processus, donc l'erreur d'hôte manquant ne pouvait pas
  remonter jusqu'à la CLI — l'exécution était notée comme un échec de
  l'apprenant et sauvegardée dans son historique. `check`/`submit` vérifient
  maintenant l'inventory avant de noter, et sortent sans rien enregistrer.

## [0.1.7] - 2026-07-16

### Ajouté

- **Les labs multi-distrib deviennent réels** : `check`/`submit` acceptent
  `--target/-t` et exportent le FQDN de la cible résolue aux tests via
  `DSOXLAB_TARGET_HOST`. Jusqu'ici `runtime.targets[]` n'était que déclaratif —
  un lab pouvait déclarer une cible Ubuntu pendant que ses tests codaient
  l'hôte RHEL en dur : choisir Ubuntu ne changeait rien et le contrat mentait.
  Les tests demandent désormais l'hôte choisi (helper `lab_target_host()` dans
  le `conftest.py` du dépôt), donc un même lab peut être réellement validé sur
  plusieurs distributions.

### Corrigé

- **Une faute de frappe dans `--target` n'enregistre plus un 0/100** : une
  cible explicite inconnue est désormais une erreur (`unknown_target`, EN+FR)
  levée avant le lancement des tests, au lieu d'un check échoué sauvegardé dans
  l'historique de l'apprenant.
- **Une cible de session ne casse plus les labs qui ne la déclarent pas** :
  l'`active_target` persistée par `use --target` n'est appliquée qu'aux labs
  qui la déclarent ; les labs shell et mono-cible l'ignorent silencieusement.

## [0.1.6] - 2026-07-16

### Corrigé

- **Inventory KVM après un provision ciblé** : `terraform apply -target`
  n'évalue pas les outputs racine, donc les IP des hôtes KVM (DHCP libvirt)
  manquaient et `dsoxlab check` échouait « Aucun host dans l'inventory » pour
  tout lab KVM. `apply()` lance désormais un `terraform apply -refresh-only`
  après un apply ciblé pour recalculer le map d'outputs `hosts` sans recréer de
  ressource.

### Ajouté

- **Détection de conflit de provider** : `dsoxlab provision` s'arrête avec un
  message d'aide (EN + FR) si un autre provider (incus/KVM) a encore de l'infra
  active — ils partagent le nom de réseau et le subnet du lab et ne peuvent pas
  tourner en même temps.

## [0.1.5] - 2026-07-15

### Ajouté

- **hints i18n** : le format moderne d'indice (`text_en` / `text_fr`) accepte
  désormais aussi des valeurs encodées en base64, pour que les indices soient à
  la fois bilingues et obfusqués dans le fichier. Le loader tente le base64
  d'abord, avec repli sur le texte brut.

### Modifié

- **challenge i18n** : le brief de challenge localisé est résolu en
  `challenge/README.<lang>.md` (ex. `README.fr.md`), cohérent avec
  `scenario.<lang>.md` et le `README.<lang>.md` racine — au lieu de l'ancien
  nommage `README_FR.md`.

## [0.1.4] - 2026-07-15

### Corrigé

- **progress** : `dsoxlab progress` affiche désormais un nom de bloc clair (le
  titre de la section meta.yml, ex. « Fondamentaux (l1) ») au lieu de `?`, et la
  colonne Bloc est alignée à gauche. Chaque lab est rattaché à sa section
  meta.yml à la découverte (`bloc` + nouveau `bloc_name`), donc le récapitulatif
  regroupe par vraie section plutôt que par un `bloc=0` non affecté.

## [0.1.3] - 2026-07-15

### Ajouté

- **labs multi-hôtes** : un mapping `runtime.targets[].roles` (ex.
  `roles: {server: alma-rhcsa-2.lab}`) permet à un lab `vm` d'utiliser plusieurs
  hôtes à la fois. Chaque rôle devient un groupe Ansible `lab_<role>` (en plus de
  `lab_target`, l'hôte primaire où tournent les tests), pour que `setup.yaml` /
  `solution.yaml` / `cleanup.yaml` configurent un serveur et un client sans coder
  de FQDN en dur. Les hôtes de rôle sont validés contre l'inventory provisionné
  au runtime. Rétro-compatible : sans `roles`, lab mono-hôte comme avant.

## [0.1.2] - 2026-07-15

### Ajouté

- **provision** : après `terraform apply`, `dsoxlab provision` attend désormais
  que chaque hôte soit réellement joignable — `sshd` démarré, compte `student`
  créé et cloud-init terminé (`cloud-init status --wait`) — avant de rendre la
  main. Cela supprime l'échec « unreachable » (dark) qui frappait le tout premier
  `dsoxlab run` juste après le provisioning : plus besoin de relancer à la main.
  Un `HostReadyTimeout` retombe sur un avertissement (la VM démarre peut-être
  encore).

### Corrigé

- **version** : `__version__` est désormais lu depuis les métadonnées du paquet
  installé au lieu d'une chaîne codée en dur, pour que `dsoxlab --version` reste
  aligné sur `pyproject.toml` (il était figé à `0.1.0`).

## [0.1.1] - 2026-07-15

### Corrigé

- **incus** : `provision --host X` ne crée plus le disque additionnel des
  *autres* hôtes, et `destroy --host X` supprime désormais le disque additionnel
  de cet hôte. Une variable Terraform `target_hosts` restreint le `for_each` du
  volume extra, et `host_targets` cible le volume propre à l'hôte pour que
  `-target` le nettoie.
  ([#1](https://github.com/stephrobert/dsoxlab/issues/1))

## [0.1.0] - 2026-07-15

Première version publique.

### Ajouté

- CLI basée sur Typer (`dsoxlab`) pilotant des labs pratiques répartis dans
  plusieurs dépôts, via un contrat déclaratif (`meta.yml` + `lab.yaml`).
- Découverte du catalogue qui scanne le `meta.yml` du dépôt courant et chaque
  `lab.yaml`.
- Trois runtimes : `shell`, `incus` (conteneurs) et `kvm` (Terraform +
  libvirt), chacun opt-in et auto-descriptif.
- Templates de provisioning pour Incus, KVM/libvirt et Outscale (HCL Terraform
  et cloud-init).
- Validation au niveau du système via `pytest` + `pytest-testinfra`, incluant
  les tests de persistance après reboot.
- Scoring et suivi de progression persistés dans une base SQLite XDG locale,
  avec des indices à coût variable.
- Validateurs de structure et de métadonnées (`dsoxlab validate-structure`).
- Diagnostics de l'environnement (`dsoxlab doctor [--fix]`).
- Interface utilisateur bilingue (anglais/français) pilotée par `DSOXLAB_LANG`.

[Unreleased]: https://github.com/stephrobert/dsoxlab/compare/v0.1.12...HEAD
[0.1.12]: https://github.com/stephrobert/dsoxlab/compare/v0.1.11...v0.1.12
[0.1.11]: https://github.com/stephrobert/dsoxlab/compare/v0.1.10...v0.1.11
[0.1.10]: https://github.com/stephrobert/dsoxlab/compare/v0.1.9...v0.1.10
[0.1.9]: https://github.com/stephrobert/dsoxlab/compare/v0.1.8...v0.1.9
[0.1.8]: https://github.com/stephrobert/dsoxlab/compare/v0.1.7...v0.1.8
[0.1.7]: https://github.com/stephrobert/dsoxlab/compare/v0.1.6...v0.1.7
[0.1.6]: https://github.com/stephrobert/dsoxlab/compare/v0.1.5...v0.1.6
[0.1.5]: https://github.com/stephrobert/dsoxlab/compare/v0.1.4...v0.1.5
[0.1.4]: https://github.com/stephrobert/dsoxlab/compare/v0.1.3...v0.1.4
[0.1.3]: https://github.com/stephrobert/dsoxlab/compare/v0.1.2...v0.1.3
[0.1.2]: https://github.com/stephrobert/dsoxlab/compare/v0.1.1...v0.1.2
[0.1.1]: https://github.com/stephrobert/dsoxlab/compare/v0.1.0...v0.1.1
[0.1.0]: https://github.com/stephrobert/dsoxlab/releases/tag/v0.1.0
