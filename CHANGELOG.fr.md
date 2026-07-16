# Journal des modifications

**Langue :** [English](./CHANGELOG.md) · [Français](./CHANGELOG.fr.md)

Toutes les modifications notables du projet sont documentées dans ce fichier.

Le format s'appuie sur [Keep a Changelog](https://keepachangelog.com/fr/1.1.0/),
et le projet suit le [versionnage sémantique](https://semver.org/lang/fr/).

## [Unreleased]

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

[Unreleased]: https://github.com/stephrobert/dsoxlab/compare/v0.1.0...HEAD
[0.1.0]: https://github.com/stephrobert/dsoxlab/releases/tag/v0.1.0
