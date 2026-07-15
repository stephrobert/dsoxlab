# Changelog

**Language:** [English](./CHANGELOG.md) · [Français](./CHANGELOG.fr.md)

All notable changes to this project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

- Nothing yet.

## [0.1.1] - 2026-07-15

### Fixed

- **incus**: `provision --host X` no longer creates the additional disk of
  *other* hosts, and `destroy --host X` now removes that host's own additional
  disk. A `target_hosts` Terraform variable scopes the extra-volume `for_each`,
  and `host_targets` targets the host's own volume so `-target` cleans it up.
  ([#1](https://github.com/stephrobert/dsoxlab/issues/1))

## [0.1.0] - 2026-07-15

Initial public release.

### Added

- Typer-based CLI (`dsoxlab`) driving hands-on labs across multiple lab
  repositories through a declarative contract (`meta.yml` + `lab.yaml`).
- Catalog discovery that scans the current repository's `meta.yml` and every
  `lab.yaml`.
- Three runtimes: `shell`, `incus` (containers) and `kvm` (Terraform +
  libvirt), each opt-in and self-describing.
- Provisioning templates for Incus, KVM/libvirt and Outscale (Terraform HCL and
  cloud-init).
- Infrastructure-level validation with `pytest` + `pytest-testinfra`, including
  persistence-after-reboot checks.
- Scoring and progress tracking persisted in a local XDG SQLite database, with
  variable-cost hints.
- Structure and metadata validators (`dsoxlab validate-structure`).
- Environment diagnostics (`dsoxlab doctor [--fix]`).
- Bilingual (English/French) user interface driven by `DSOXLAB_LANG`.

[Unreleased]: https://github.com/stephrobert/dsoxlab/compare/v0.1.0...HEAD
[0.1.0]: https://github.com/stephrobert/dsoxlab/releases/tag/v0.1.0
