<picture>
  <source media="(prefers-color-scheme: dark)" srcset="docs/assets/brand/dsoxlab-lockup-dark.svg">
  <img src="docs/assets/brand/dsoxlab-lockup-light.svg" alt="dsoxlab" width="240">
</picture>

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

Requires **Python 3.11+**.

```bash
uv tool install dsoxlab      # or: pipx install dsoxlab
dsoxlab --version
```

That is the whole installation. Nothing to clone, nothing to build.

---

## Your first lab, in five minutes

You do not need a catalog to start. `dsoxlab demo` installs a one-lab
demonstration catalog whose subject is dsoxlab itself: the loop you will repeat
on every other lab.

```bash
dsoxlab demo                    # installs it and prints what to do next
cd ~/.local/share/dsoxlab/demo

dsoxlab course premiers-pas     # the lesson
dsoxlab run premiers-pas        # drops you in the lab's work directory
dsoxlab challenge premiers-pas  # the mission
dsoxlab check premiers-pas      # the tests, and the score
```

No VM, no container, no Docker: it runs anywhere dsoxlab runs.

---

## Then, a real catalog

Labs live in their own repositories, published separately from the engine.
Clone one, then run `dsoxlab` from inside it:

```bash
git clone https://github.com/stephrobert/linux-dsoxlab-training.git
cd linux-dsoxlab-training

dsoxlab doctor                  # what this catalog needs, and what is missing
dsoxlab list-labs
dsoxlab run <lab-id>
dsoxlab check <lab-id>
```

`dsoxlab doctor` only reports what *this* catalog needs: a shell-only catalog
never asks for a hypervisor. `dsoxlab doctor --fix` repairs what can be repaired
safely. If something goes wrong, `dsoxlab support` produces an anonymised
diagnostic report ready to paste into an issue.

### Installing from source (contributors)

```bash
git clone https://github.com/stephrobert/dsoxlab.git
cd dsoxlab
uv tool install --editable .
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

### Reading long courses

`course` and `challenge` go through the pager as soon as their output is
taller than the terminal, so a course of several hundred lines stays readable
without depending on the terminal's scrollback. Pipes and redirections are
never paged: they always receive the full text.

```bash
DSOXLAB_PAGER='bat --plain' dsoxlab course   # pick your pager (default: less -R)
dsoxlab course --no-pager                    # dump everything at once
dsoxlab course > course.txt                  # never paged: plain text
```

---

## The declarative contract

A lab-hosting repository describes its catalog with two levels of files.

The contract is **versioned**. Both files accept a `schema_version` integer at
their root; leaving it out means version 1, so no existing catalog has anything
to change. A file declaring a version this dsoxlab does not read is named in a
message rather than vanishing from the catalog. Field by field, with the
evolution rule and the migration path to a future v2:
**[the v1 contract reference](docs/contract-v1.md)**.

Two JSON Schemas describe the same contract for your editor and your CI:
[`schemas/lab.schema.json`](schemas/lab.schema.json) and
[`schemas/meta.schema.json`](schemas/meta.schema.json). Put this line at the top
of a file and any editor running `yaml-language-server` (the YAML extension of
VS Code, among others) completes fields and underlines mistakes as you type:

```yaml
# yaml-language-server: $schema=https://raw.githubusercontent.com/stephrobert/dsoxlab/main/schemas/lab.schema.json
id: my-lab
title: My lab
```

Swap `main` for a release tag (`v0.1.46`) to pin the schema in CI. A test
confronts both schemas with the parser, in both directions, so they cannot
quietly drift from the code.

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

#### Optional `runtime.fixtures`: the starting files of a `shell` lab

A `shell` lab lists the files it hands to the learner. Each entry is a path
**relative to `<lab>/fixtures/`**, and that path is **preserved** under the
workdir: intermediate directories are created for you, so a lab can ship a local
Terraform module without its `main.tf` colliding with the root one.

```yaml
runtime:
  type: shell
  workdir: challenge/work
  fixtures:
    - versions.tf
    - main.tf
    - modules/stockage/main.tf   # lands in <workdir>/modules/stockage/main.tf
```

Two things to know. A file **not listed here is not copied**, even if it sits in
`fixtures/` — the runtime iterates over this list, not over the directory. And a
path that is absolute or contains `..` is refused with a warning, so a fixture
never writes outside the workdir.

#### Optional `runtime.services`: containerized sidecars

Services of a repository share a Docker network, each reachable by its declared
`name`: a lab with an application and its database writes `DB_HOST: db`. On
Docker's default bridge there is no name resolution between containers, so such
a lab could not be declared at all.

A lab can declare containers that must be up while it runs. dsoxlab starts them
on `run`/`check`/`submit` and stops them on `clean`. The mechanism is
domain-agnostic: it launches exactly the image you declare and knows nothing
about what runs inside. A cloud-API emulator for a Terraform lab is one use;
a database for an app lab is another.

```yaml
runtime:
  type: shell
  workdir: challenge/work
  services:
    - name: cloud                 # required, unique within the lab
      image: some/emulator:1.2.3  # required, the exact image to run
      ports: ["4566:4566"]        # optional, docker -p mappings
      run_args: ["-u", "root"]    # optional, extra docker run flags
      env: { DEBUG: "1" }         # optional, -e VAR=value
      ready_tcp: 4566             # optional, HOST port to wait on. Beware: on a
                                  # published port Docker's proxy accepts before
                                  # the service listens, so this alone lies.
      ready_exec: check-health    # optional but recommended: probe run INSIDE the
                                  # container, retried until it succeeds. This is
                                  # the only trustworthy readiness signal.
      post_start:                 # optional: initialise the service once ready
        - seed --from fixtures    # (schema, secrets, repository…). Run through
                                  # `docker exec`, no shell. Replayed on every
                                  # start, so it must be idempotent.
      ready_timeout: 90           # optional, seconds before giving up (default 90)
```

Containers are named `dsoxlab-<repo-id>-<service>` so they never collide
across repos. Docker must be reachable; if it is not, the lab fails fast rather
than running against a missing service.

`dsoxlab validate-structure` checks that the whole contract holds: the root
`meta.yml` is well-formed, every referenced lab exists with a valid
`lab.yaml`, each `runtime.host` maps to a declared host, and all referenced
scripts and test files are present.

---

## Command reference

<!-- BEGIN COMMANDES : généré par scripts/generer-doc.py, ne pas éditer -->

| Command | Purpose |
| --- | --- |
| `dsoxlab challenge` | Display the challenge mission for this lab (challenge/README.md). |
| `dsoxlab check` | Run tests, calculate score (hints deducted) and record result. |
| `dsoxlab clean` | Remove all resources created by the lab. |
| `dsoxlab course` | Display a course section, or the table of contents if no section is given. |
| `dsoxlab demo` | Install a demonstration catalog and play a first lab, with nothing to clone and nothing to provision. |
| `dsoxlab destroy` | Destroy the lab infrastructure (terraform destroy), including machines left outside the state. |
| `dsoxlab doctor` | Diagnose the environment (runtimes, tools, detected labs). |
| `dsoxlab fullhelp` | Show the complete platform guide (concepts, workflow, commands). |
| `dsoxlab guide` | Open the lab's online guide in your web browser. |
| `dsoxlab hint` | Show the next challenge hint (deducts points from final score). |
| `dsoxlab install` | Install the dsoxlab wrapper in ~/.local/bin and shell auto-completion. |
| `dsoxlab instructor bootstrap` | Generate the lab SSH key (if missing) and check that terraform/ansible-runner are installed. |
| `dsoxlab list-labs` | List all available labs (filtered by active context if set). |
| `dsoxlab next` | Recommend the next lab or challenge to complete in the active context. |
| `dsoxlab progress` | Show progression by bloc (labs completed, average score, challenges and capstones). |
| `dsoxlab provision` | Provision the lab infrastructure (terraform apply on the current provider). |
| `dsoxlab reset` | Reset the lab to its initial state (clean + restart). |
| `dsoxlab run` | Prepare and start the lab environment. |
| `dsoxlab scores` | Show recorded scores history. |
| `dsoxlab show` | Show details and status of a lab. |
| `dsoxlab ssh` | Open an interactive SSH session on a lab host. |
| `dsoxlab status` | Check SSH connectivity to all hosts declared in meta.yml, and name the cause when one stays silent. |
| `dsoxlab submit` | Final submission: run tests, record score, then type 'exit' to leave the session. |
| `dsoxlab support` | Produce an anonymised diagnostic report, ready to paste into an issue. |
| `dsoxlab use` | Sets the active context (section and/or default level). Use --reset to clear it. |
| `dsoxlab validate-structure` | Check structure and metadata of all labs. |

<!-- END COMMANDES -->

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

Everything dsoxlab keeps lives in four places, and **progress is per
catalog**, never global: two catalogs side by side each keep their own history.

| What | Where | Override |
| --- | --- | --- |
| Scores and hints | `<catalog>/.dsoxlab.db` (SQLite) | none, it is the repo |
| Session context | `<catalog>/.dsoxlab-context.json` | none, it is the repo |
| Log, Terraform state | `~/.local/state/dsoxlab/` | `XDG_STATE_HOME` |
| Demonstration catalog | `~/.local/share/dsoxlab/demo/` | `XDG_DATA_HOME` |

The first two belong in each catalog's `.gitignore`.

There is **no user configuration file**: nothing is read from
`~/.config/dsoxlab/`. What can be set goes through the contract (`meta.yml`),
the active context (`dsoxlab use`) or an environment variable
(`DSOXLAB_PROVIDER`, `DSOXLAB_LANG`, `DSOXLAB_LOG`,
`DSOXLAB_HOST_READY_TIMEOUT`).

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

The mark and its files are documented in [docs/brand.md](./docs/brand.md);
**the name and the logo are not covered by the Apache 2.0 licence**.

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
