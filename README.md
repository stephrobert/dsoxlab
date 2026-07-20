# dsoxlab — DevSecOps XL Labs CLI

[![CI](https://github.com/stephrobert/dsoxlab/actions/workflows/ci.yml/badge.svg)](https://github.com/stephrobert/dsoxlab/actions/workflows/ci.yml)
[![OpenSSF Scorecard](https://img.shields.io/ossf-scorecard/github.com/stephrobert/dsoxlab?label=OpenSSF%20Scorecard)](https://securityscorecards.dev/viewer/?uri=github.com/stephrobert/dsoxlab)
[![Plumber compliance](https://score.getplumber.io/github.com/stephrobert/dsoxlab.svg)](https://score.getplumber.io/github.com/stephrobert/dsoxlab)
[![License: Apache 2.0](https://img.shields.io/badge/License-Apache%202.0-blue.svg)](./LICENSE)
[![Python](https://img.shields.io/badge/python-3.11%2B-blue.svg)](https://www.python.org/)
[![Code style: ruff](https://img.shields.io/badge/lint-ruff-orange.svg)](https://github.com/astral-sh/ruff)

**Read this in another language:** [Français](./README.fr.md)

`dsoxlab` is a **domain-agnostic CLI framework** that drives hands-on
learning labs spread across **multiple repositories**. Each repository
declares its own catalog through a root `meta.yml` file and one `lab.yaml`
per lab.

The framework serves Linux, Ansible, Kubernetes or Terraform labs equally
well — anything that honors the declarative contract. It provisions the
environment, runs infrastructure-level validation (`pytest` +
`pytest-testinfra`), scores progress, and stores history locally. Nothing
about a specific domain lives in the engine.

> Companion to the tutorials on
> [blog.stephane-robert.info](https://blog.stephane-robert.info).

<p align="center">
  <img src="https://raw.githubusercontent.com/stephrobert/dsoxlab/main/docs/demo.gif" alt="dsoxlab in action: list-labs and show" width="820">
</p>

---

## Why dsoxlab

- **One engine, many catalogs.** A single CLI drives every training
  repository. Add a new domain by writing a `meta.yml`, not by patching the
  tool.
- **Validation proves, it does not trust.** Labs are graded on the actual
  **state of the system** (`pytest-testinfra`) and, when it matters, on
  **persistence after reboot** — the trap that fails RHCSA/LFCS candidates.
- **Multiple runtimes.** Run a lab in a plain **shell**, an **Incus**
  container, or a full **KVM/libvirt** virtual machine, chosen per lab.
- **Progress that sticks.** Scores, hint costs and history are persisted in a
  local SQLite database following the XDG spec.
- **Bilingual UX.** Every user-facing string ships in English and French
  (`DSOXLAB_LANG=en|fr`).

---

## Installation

Requires **Python 3.11+** and [uv](https://docs.astral.sh/uv/).

```bash
# From the Git repository (development / editable mode)
git clone https://github.com/stephrobert/dsoxlab.git
cd dsoxlab
uv tool install --editable .

# Verify
dsoxlab --version
dsoxlab doctor
```

`dsoxlab doctor --fix` diagnoses (and repairs where possible) the local
toolchain expected by the runtimes: SSH, Terraform, libvirt/Incus, and the
embedded `pytest` stack.

---

## Quickstart

Labs live in their own repositories, published separately from the engine.
Clone one first, then run `dsoxlab` from inside it:

```bash
# 1. Clone a lab catalog (e.g. linux-dsoxlab-training)
git clone https://github.com/stephrobert/linux-dsoxlab-training.git
cd linux-dsoxlab-training

# 2. The active context is detected automatically from the repo's meta.yml
dsoxlab list-labs
dsoxlab show linux.depanner.service-crash-loop
dsoxlab guide linux.depanner.service-crash-loop   # read the course in your browser
dsoxlab run linux.depanner.service-crash-loop
dsoxlab check linux.depanner.service-crash-loop
```

### Reading the course

The course itself is not bundled in the lab repository: each lab declares a
`doc_url` pointing to the trainer's site. `dsoxlab guide` opens that page in a
real browser tab, so it renders exactly as published, with its images, code
blocks and navigation.

```bash
dsoxlab guide                 # the active lab
dsoxlab guide <id>            # a specific lab
dsoxlab guide <id> --print    # print the URL instead (useful over SSH)
```

The URL carries campaign parameters (`utm_source=dsoxlab`, `utm_medium=lab`,
`utm_campaign=<lab_id>`), so a trainer can see which labs actually drive readers
to which guides. A link opened from a local interface carries no usable referrer,
so without this marking those reads would be indistinguishable from direct traffic.

Switch language on the fly:

```bash
DSOXLAB_LANG=fr dsoxlab fullhelp
DSOXLAB_LANG=en dsoxlab fullhelp
```

---

## The declarative contract

A lab-hosting repository describes its catalog with two levels of files.

### 1. `meta.yml` at the repository root

Repository metadata, infrastructure topology (KVM/Incus), section ordering.

```yaml
repo:
  id: linux-training
  category: linux
  title: "Linux Training — RHCSA + LFCS 2026"
  blog_url: "https://blog.stephane-robert.info/docs/admin-serveurs/linux/"

infra:
  network: lab-linux
  hosts:
    - { name: alma-rhcsa-1.lab, ip: 10.10.30.11, distro: alma10 }
    - { name: alma-rhcsa-2.lab, ip: 10.10.30.12, distro: alma10 }
    - { name: ubuntu-lfcs-1.lab, ip: 10.10.30.21, distro: ubuntu24 }

sections:
  - id: depanner
    title: "Troubleshooting"
    labs:
      - depanner/services-processus/service-crash-loop
      - depanner/stockage-fs/disque-plein-mais-pas-de-fichiers
```

### 2. `lab.yaml` per lab (under `labs/<category>/<section>/<lab>/`)

Lab-specific metadata (skills, runtime, distros, validation).

```yaml
id: depanner-service-crash-loop
title: "Identify and fix a crash-looping systemd service"
section: linux
level: l2
track: [depanner, rhcsa]
skills: [systemd, journalctl, debug]
difficulty: intermediate
estimated_time: 30m
runtime:
  type: kvm
  host: alma-rhcsa-1.lab
distros: [rhel10, ubuntu24.04]
doc_url: https://blog.stephane-robert.info/docs/admin-serveurs/linux/depanner/services-processus/service-crash-loop/
validation:
  functional: true
  security: false
  persistence_after_reboot: true
```

An optional `lab.fr.yaml` may override `title` and `description` for French
only.

`dsoxlab validate-structure` checks that the whole contract holds: the root
`meta.yml` is well-formed, every referenced lab exists with a valid
`lab.yaml`, each `runtime.host` maps to a declared host, and all referenced
scripts and test files are present.

---

## Command reference

| Command | Purpose |
| --- | --- |
| `dsoxlab use [section[/level]]` | Set the active context; `--reset` clears it, `--provider` selects the infra provider |
| `dsoxlab list-labs` | List labs of the current repo (filter by `--section`/`--level`/`--type`/`--bloc`) |
| `dsoxlab show <id>` | Show a lab's details |
| `dsoxlab course [section]` | Display a course section, or the table of contents |
| `dsoxlab guide [id]` | Open the lab's online guide in a browser (`--print` shows the URL) |
| `dsoxlab run <id>` | Prepare and start the lab environment |
| `dsoxlab challenge <id>` | Show the challenge mission for a lab |
| `dsoxlab hint <id>` | Reveal a hint (deducted from the score) |
| `dsoxlab check <id>` | Run the `pytest` validation and record the score |
| `dsoxlab submit <id>` | Final submission: run tests, record score, close the session |
| `dsoxlab scores` | Show run history (local SQLite) |
| `dsoxlab progress` | Progression by bloc (labs done, average score, challenges) |
| `dsoxlab next` | Recommend the next lab or challenge to tackle |
| `dsoxlab reset <id>` | Reset the lab to its initial state |
| `dsoxlab clean <id>` | Run the lab's `cleanup.sh` |
| `dsoxlab provision` | Provision the lab infrastructure (`terraform apply`) |
| `dsoxlab destroy` | Destroy the lab infrastructure (`terraform destroy`) |
| `dsoxlab status` | Check SSH connectivity to all hosts in `meta.yml` |
| `dsoxlab ssh <host>` | Open an interactive SSH session on a lab host |
| `dsoxlab validate-structure` | Validate the contract (`meta.yml` + every `lab.yaml`) |
| `dsoxlab doctor [--fix]` | Diagnose (and repair) the local environment |
| `dsoxlab install` | Install the shell wrapper and auto-completion |
| `dsoxlab instructor bootstrap` | Instructor tooling (e.g. generate the lab SSH key) |
| `dsoxlab fullhelp` | Full multilingual guide (EN/FR) |

Run `dsoxlab <command> --help` for the options of any command.

---

## Runtimes

| Runtime | Backend | Typical use |
| --- | --- | --- |
| `shell` | Local shell | Quick, single-host exercises with no VM overhead |
| `incus` | Incus containers | Isolated, fast-booting Linux environments |
| `kvm` | Terraform + libvirt | Full VMs with reboot/persistence testing |

Each runtime is opt-in and self-describing (`is_available()`), so the engine
never hard-depends on a backend the user has not installed. Provisioning
templates (Terraform HCL, cloud-init) live under `dsoxlab.templates` and
support Incus, KVM/libvirt and Outscale.

---

## Architecture

```text
src/dsoxlab/
├── cli.py            ← Typer entry point (+ i18n command group)
├── config.py         ← LAB_HOME, active context, .dsoxlab-context.json
├── i18n/             ← get_lang(), _(), en.py + fr.py
├── models/           ← typed schemas of the declarative contract
├── discovery/        ← scan meta.yml + every lab.yaml of the current repo
├── services/         ← business orchestration (get_lab, run_lab, check_lab…)
├── sessions/         ← SQLite persistence (results + hint_requests)
├── runtimes/         ← BaseRuntime, ShellRuntime, IncusRuntime, KvmRuntime
├── infra/            ← Terraform, Ansible, inventory, snapshots
├── validators/       ← contract validation (meta.yml + lab.yaml)
├── reporting/        ← Rich terminal output
├── utils/            ← centralized subprocess wrapper
└── templates/        ← provisioning templates (HCL, cloud-init)
```

The engine stays independent of any single repository layout: `discovery/`
works on whatever tree the `meta.yml` declares.

---

## Persistence

- **Local sessions:** `.dsoxlab-context.json` in the current repo (gitignored
  by each lab repository).
- **Scores and hints:** `~/.local/share/dsoxlab/progress.db` (XDG). The global
  lab id is `<category>.<section>.<lab>`, so the schema stays universal.
- **User config:** `~/.config/dsoxlab/config.yaml` (optional).

Override the locations with the standard `XDG_DATA_HOME` / `XDG_CONFIG_HOME`
environment variables.

---

## Development

```bash
uv sync                                     # install dev dependencies
uv run pre-commit install --install-hooks   # enable the git hooks
uv run ruff check src/dsoxlab               # lint + security
uv run mypy src/dsoxlab                     # type-check (strict)
uv run pytest                               # tests
```

See [CONTRIBUTING.md](./CONTRIBUTING.md) for the workflow, the commit
conventions, and the non-negotiable rules (the engine must stay
domain-agnostic, every user-facing string goes through `_()` in both
languages).

---

## Security

Security posture is enforced, not aspirational — every workflow is scanned by
its own tooling on each push and pull request:

- **Hardened GitHub Actions.** Every action is pinned to a full commit SHA, the
  default token has no permissions (jobs opt into least privilege), and
  `checkout` never persists credentials.
- **[zizmor](https://github.com/zizmorcore/zizmor)** statically analyzes the
  workflows on every PR (`ci.yml`).
- **[Plumber](https://getplumber.io)** validates the CI/CD against a trust
  policy (`.plumber.yaml`) at a 100% compliance threshold, and publishes the
  score badge (`plumber.yml`).
- **[OpenSSF Scorecard](https://securityscorecards.dev)** tracks the
  supply-chain posture (`scorecard.yml`).
- **PyPI Trusted Publishing (OIDC).** Releases carry no long-lived token and
  ship [PEP 740](https://peps.python.org/pep-0740/) attestations (`release.yml`).
- **Pre-commit secret scanning.** TruffleHog and private-key detection run
  locally before every commit (see [CONTRIBUTING.md](./CONTRIBUTING.md)).

To report a vulnerability, follow [SECURITY.md](./SECURITY.md).

## License & attribution

Licensed under the **Apache License 2.0** — see [LICENSE](./LICENSE) and
[NOTICE](./NOTICE).

You may use, share and adapt this project, including commercially, **provided
you give appropriate credit to Stephane Robert and link back to
<https://blog.stephane-robert.info>**, and indicate whether changes were made.
Apache-2.0 keeps those same two obligations — attribution and stating your
changes — and adds an express patent grant.

Up to and including **0.1.12**, dsoxlab was distributed under Creative Commons
Attribution 4.0 (CC BY 4.0). That grant is irrevocable, so those releases remain
available under CC BY 4.0. From **0.1.13** onwards the project is Apache-2.0:
Creative Commons licences are not designed for software, and this one left the
patent question open while marking the package as `Other/NOASSERTION` on PyPI.

© 2026 Stephane Robert.
