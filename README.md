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

`dsoxlab` turns **declarative exercises into reproducible, runnable and
verifiable environments**. A catalog states what it offers through a root
`meta.yml` and one `lab.yaml` per lab; the engine provisions what each lab
asks for, opens it, and proves the result with tests that read the **state of
the system** rather than the commands typed into it.

Nothing about a specific domain lives in the engine: it serves Linux, Ansible,
Kubernetes or Terraform labs equally well, and any other catalog that honors
the declarative contract. It also scores progress and keeps the history
locally, per catalog.

> Originally built for the tutorials on
> [blog.stephane-robert.info](https://blog.stephane-robert.info), and usable
> without them.

<p align="center">
  <img src="https://raw.githubusercontent.com/stephrobert/dsoxlab/main/docs/demo.gif" alt="dsoxlab in action: list-labs and show" width="820">
</p>

---

## Install and play, in five minutes

Requires **Python 3.11+**. Nothing to clone, nothing to build.

```bash
uv tool install dsoxlab      # or: pipx install dsoxlab
dsoxlab demo                 # installs a one-lab demonstration catalog
cd ~/.local/share/dsoxlab/demo

dsoxlab course premiers-pas     # the lesson
dsoxlab run premiers-pas        # drops you into the lab's work directory
dsoxlab challenge premiers-pas  # the mission
dsoxlab check premiers-pas      # the tests, and the score
```

The demonstration lab is about dsoxlab itself, and needs no VM, no container
and no Docker: it runs anywhere dsoxlab runs.

---

## Documentation

Three readers, three doors. Every page names its audience in its first lines.

| I want to… | Read |
| --- | --- |
| Install dsoxlab, play labs, understand my score | **[For the learner](docs/learner.md)** |
| Write my own catalog of labs | **[For the catalog author](docs/catalog-author.md)**, then [the v1 contract](docs/contract-v1.md) field by field |
| Run the machines the labs need | **[For the trainer](docs/trainer.md)** |
| Know where dsoxlab writes on my disk | [Where dsoxlab writes](docs/files.md) |
| See every command | [Command reference](docs/commands.md), generated from the CLI |

In the terminal, `dsoxlab fullhelp` prints the whole platform guide, in English
or in French.

---

## Why dsoxlab

- **One engine, many catalogs.** A single CLI drives every training
  repository. Add a new domain by writing a `meta.yml`, not by patching the
  tool.
- **Validation proves, it does not trust.** Labs are graded on the actual
  **state of the system** (`pytest-testinfra`) and, when it matters, on
  **persistence after reboot** — the trap that fails RHCSA/LFCS candidates.
- **Two runtimes.** A lab runs either in a **shell** on your own machine, or in
  a **vm** provisioned for you. Which backend serves that VM (KVM/libvirt,
  Incus, Outscale) is the catalog's decision, not the lab's.
- **Progress that sticks, per catalog.** Scores, hint costs and history are
  persisted inside the catalog itself, so two catalogs never mix their
  histories.
- **Bilingual UX.** Every user-facing string ships in English and French
  (`DSOXLAB_LANG=en|fr`).

---

## Contributing

```bash
git clone https://github.com/stephrobert/dsoxlab.git
cd dsoxlab
uv tool install --editable .
```

See [CONTRIBUTING.md](./CONTRIBUTING.md) for the development setup, the quality
gates and the non-negotiable rules (the engine stays domain-agnostic, every
user-facing string goes through `_()` in both languages).

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
