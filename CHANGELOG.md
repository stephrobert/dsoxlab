# Changelog

**Language:** [English](./CHANGELOG.md) · [Français](./CHANGELOG.fr.md)

All notable changes to this project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [0.1.13] - 2026-07-17

### Changed

- **Licence : CC BY 4.0 → Apache-2.0.** Creative Commons
  [advises against its licences for software](https://creativecommons.org/faq/#can-i-apply-a-creative-commons-license-to-software):
  they carry no patent grant, their terms are written for creative works rather
  than code, and PyPI could only mark the package as `Other/NOASSERTION`. For a
  CLI published on PyPI and imported by third-party lab repositories, that left
  real legal ambiguity for users.

  **Apache-2.0 is the closest software licence to the previous terms.** It keeps
  both obligations CC BY 4.0 imposed — give credit, and state whether you changed
  the files (§4.b) — and adds the express patent grant CC BY 4.0 lacks.
  Attribution now lives in the [NOTICE](./NOTICE) file, which §4.d requires
  derivative works to carry.

  **Releases up to and including 0.1.12 remain under CC BY 4.0**: that grant is
  irrevocable for anyone who received them. Only 0.1.13 onwards is Apache-2.0.

## [0.1.12] - 2026-07-17

### Fixed

- **The build provenance no longer attests a file that is not published.**
  `uv build` drops a one-byte `dist/.gitignore`, and `attest-build-provenance`
  globs dotfiles (unlike the shell glob feeding `gh release create`), so the
  v0.1.11 attestation listed `.gitignore` next to the wheel and the sdist. The
  artifacts are now named explicitly. Harmless in itself, but an attestation
  should name exactly what is published, nothing more.

## [0.1.11] - 2026-07-17

### Fixed

- **A malformed `lab.yaml` or `meta.yml` could crash the CLI instead of being
  skipped.** `discovery/scanner.py` catches `(KeyError, ValueError,
  yaml.YAMLError)` and ignores the offending lab with a warning — but the
  parsers could raise outside that contract, and the exception then surfaced as
  a raw traceback on an unrelated command (`list-labs`, `progress`…). Since a
  `lab.yaml` comes from a *lab-provider repository*, this is the engine's
  untrusted input. Five cases, all found by the new fuzz harnesses:
  - an **empty** `lab.yaml` (or one holding only comments) → `AttributeError`,
    because `yaml.safe_load` returns `None`;
  - a document whose **root is a list or a scalar**, in either file;
  - **`runtime: vm`** written instead of the `runtime:` block, and
    `runtime.targets: true` → `AttributeError` / `TypeError`;
  - **`infra.hosts:` written as a mapping** instead of a list → `TypeError` on
    `h["name"]`, the iteration walking the keys;
  - a **present-but-empty key** such as `vcpu:` or `bloc:` → `int(None)` raises
    `TypeError`, because `.get("vcpu", 1)` returns `None` rather than the
    default when the key exists.

  Every one of these now raises `ValueError` with the file path and the
  offending field, so the lab is skipped and the rest of the catalogue still
  loads. An empty `ip:` no longer yields the literal string `"None"` either.

### Added

- **Fuzz harnesses over the untrusted-YAML contract** (`fuzz/`), run as a short
  regression in CI. They assert the *contract* — any exception outside
  `(KeyError, ValueError, yaml.YAMLError)` fails the run — rather than merely
  executing the parsers. Ships a seed corpus and a libFuzzer dictionary of the
  contract's keywords; `uv sync --group fuzz` installs atheris (kept out of the
  `dev` group).
- **`actionlint` and `poutine` as CI gates**, alongside the existing zizmor job,
  both installed from a release binary whose SHA-256 is verified against the
  published checksums. `poutine --fail-on-violation` makes it a gate, not a
  report. The heavier jobs now wait on all three scanners.
- **`step-security/harden-runner`** as the first step of every job
  (`egress-policy: audit`), and `.poutine.yml` acknowledging three hand-vetted
  actions per purl rather than disabling the rule.
- **Build provenance attached to the GitHub Release** as
  `provenance.intoto.jsonl`. The existing attestation is recorded on GitHub's
  attestation API, which is a *different* artifact from the release asset that
  OpenSSF Scorecard's Signed-Releases control looks for.

## [0.1.10] - 2026-07-16

### Fixed

- **Scores were wrong on labs whose data contains "ERROR", "PASSED" or
  "FAILED"**: `_parse_counts()` counted occurrences of those words in pytest's
  raw output, including inside assertion messages. A lab that filters `ERROR`
  lines (`l1-get-help`, `l1-grep-regex`, `l1-redirections-pipes`,
  `l3-service-diagnose`…) inflated its own total — `dsoxlab check` reported
  `1/5` for a 4-test lab, so the learner's score was under-counted (20 pts
  instead of 25). The summary line pytest produces itself is now the source of
  truth, with a node-id-anchored fallback.

## [0.1.9] - 2026-07-16

### Fixed

- **KVM: two lab repositories can no longer fight over the same base volume.**
  The libvirt base image was named `dsoxlab-base-<distro>.qcow2`, without the
  repository id — but the libvirt pool is *shared* across repositories while
  each repository keeps its **own** Terraform state. So the second repository to
  provision on a distro already used by another failed with
  `storage volume 'dsoxlab-base-alma10.qcow2' exists already`: its state simply
  did not know about the volume the first one had created. Concretely,
  `linux-dsoxlab-training` (alma10) blocked `ansible-training` (alma10) on the
  same host. The volume is now `dsoxlab-base-<repo-id>-<distro>.qcow2`, so lab
  catalogs really do cohabit, as the contract promises with their separate
  libvirt networks. The cloud image is duplicated per repository (sparse, ~600 MB
  to 2 GB) — the price of isolation.

  Terraform gets a new `repo_id` variable, declared by the three providers
  (`kvm`, `incus`, `outscale`) since the tfvars are shared; only `kvm` creates a
  local volume, so only it was affected. Incus pulls public image aliases and
  Outscale uses AMIs: neither could collide.

  **Upgrade impact.** On a repository provisioned with ≤ 0.1.8, the next
  `dsoxlab provision` renames the base volume, which Terraform treats as a
  *replacement*: the VMs get recreated. Nothing is lost — lab VMs are meant to
  be disposable and the learner's work lives in the repository
  (`challenge/`), never on the VM — but any in-progress lab state on the VMs
  goes away. Run `dsoxlab destroy` then `dsoxlab provision` for a clean cycle.

## [0.1.8] - 2026-07-16

### Fixed

- **No more Python traceback when the infrastructure is not provisioned**: a
  learner running a VM lab before `dsoxlab provision` (first run, or after a
  `destroy`) got a raw `ValueError: target_fqdn '...' is not in the list of
  known hosts: []`. This is a normal situation, not a bug — `build_inventory()`
  now raises `InfraNotProvisioned`, rendered by the CLI as one actionable
  sentence (EN+FR) telling the learner to run `dsoxlab provision`. A `main()`
  entry point catches it for every command, so no command can surface a
  traceback for it.
- **`check` no longer records a 0/100 when there is no infrastructure**: pytest
  runs in a subprocess, so the missing-host error could not reach the CLI — the
  run was scored as a learner failure and saved to their history. `check`/
  `submit` now verify the inventory before scoring, and exit without recording.

## [0.1.7] - 2026-07-16

### Added

- **Multi-distro labs are now real**: `check`/`submit` accept `--target/-t` and
  export the resolved target's FQDN to the tests via `DSOXLAB_TARGET_HOST`.
  Until now `runtime.targets[]` was declarative only — a lab could declare an
  Ubuntu target while its tests hard-coded the RHEL host, so selecting Ubuntu
  changed nothing and the contract lied. Tests now ask for the chosen host
  (`lab_target_host()` helper in the repo's `conftest.py`), so one lab can be
  genuinely validated on several distributions.

### Fixed

- **A typo in `--target` no longer records a 0/100**: an unknown explicit
  target is now an error (`unknown_target`, EN+FR) raised before the tests run,
  instead of a failed check saved to the learner's history.
- **A session target no longer breaks labs that don't declare it**: the
  `active_target` persisted by `use --target` is applied only to labs that
  actually declare it; shell and single-target labs silently ignore it.

## [0.1.6] - 2026-07-16

### Fixed

- **KVM inventory after a targeted provision**: `terraform apply -target` does
  not evaluate root outputs, so KVM host IPs (libvirt DHCP) were missing and
  `dsoxlab check` failed with "Aucun host dans l'inventory" for every KVM lab.
  `apply()` now runs `terraform apply -refresh-only` after a targeted apply to
  recompute the `hosts` output map without recreating resources.

### Added

- **Provider conflict detection**: `dsoxlab provision` stops with a helpful
  message (EN + FR) when another provider (incus/KVM) still has active lab
  infrastructure — they share the lab's network name and subnet and cannot run
  at the same time.

## [0.1.5] - 2026-07-15

### Added

- **hints i18n**: the modern hint format (`text_en` / `text_fr`) now also accepts
  base64-encoded values, so hints can be both bilingual and obfuscated in the
  file. The loader tries base64 first and falls back to plain text.

### Changed

- **challenge i18n**: the localized challenge brief is resolved as
  `challenge/README.<lang>.md` (e.g. `README.fr.md`), consistent with
  `scenario.<lang>.md` and the root `README.<lang>.md` — instead of the old
  `README_FR.md` naming.

## [0.1.4] - 2026-07-15

### Fixed

- **progress**: `dsoxlab progress` now shows a clear bloc name (the meta.yml
  section title, e.g. "Fondamentaux (l1)") instead of `?`. Each lab is attached
  to its meta.yml section during discovery (`bloc` + new `bloc_name`), so the
  summary groups by real section instead of an unassigned `bloc=0`.

## [0.1.3] - 2026-07-15

### Added

- **multi-host labs**: a `runtime.targets[].roles` mapping (e.g.
  `roles: {server: alma-rhcsa-2.lab}`) lets a `vm` lab use several hosts at once.
  Each role becomes an Ansible group `lab_<role>` (alongside `lab_target`, the
  primary host where tests run), so `setup.yaml` / `solution.yaml` /
  `cleanup.yaml` can configure a server and a client without hard-coding a FQDN.
  The role hosts are validated against the provisioned inventory at run time.
  Backward compatible: no `roles` means a single-host lab as before.

## [0.1.2] - 2026-07-15

### Added

- **provision**: after `terraform apply`, `dsoxlab provision` now waits for each
  host to become truly reachable — `sshd` up, the `student` account created, and
  cloud-init finished (`cloud-init status --wait`) — before returning. This
  removes the "unreachable" (dark) failure that hit the very first `dsoxlab run`
  right after provisioning, so no manual retry is needed. A `HostReadyTimeout`
  falls back to a warning (the VM may still be booting).

### Fixed

- **version**: `__version__` is now read from the installed package metadata
  instead of a hard-coded string, so `dsoxlab --version` stays in sync with
  `pyproject.toml` (it was stuck at `0.1.0`).

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

[Unreleased]: https://github.com/stephrobert/dsoxlab/compare/v0.1.13...HEAD
[0.1.13]: https://github.com/stephrobert/dsoxlab/compare/v0.1.12...v0.1.13
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
