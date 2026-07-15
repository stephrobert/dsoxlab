# Journal des modifications

**Langue :** [English](./CHANGELOG.md) · [Français](./CHANGELOG.fr.md)

Toutes les modifications notables du projet sont documentées dans ce fichier.

Le format s'appuie sur [Keep a Changelog](https://keepachangelog.com/fr/1.1.0/),
et le projet suit le [versionnage sémantique](https://semver.org/lang/fr/).

## [Unreleased]

### Ajouté

- Rien pour l'instant.

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
