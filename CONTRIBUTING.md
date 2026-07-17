# Contributing to dsoxlab

**Language:** [English](./CONTRIBUTING.md) · [Français](./CONTRIBUTING.fr.md)

Thanks for your interest in improving `dsoxlab`. This document explains how to
set up the project, the conventions we follow, and the rules that keep the
engine healthy.

The project is bilingual for its users, but **the contribution language is
English**: issues, pull requests, code comments and commit messages are written
in English so everyone can take part.

## Table of contents

- [Ground rules](#ground-rules)
- [Development setup](#development-setup)
- [Quality gates](#quality-gates)
  - [Workflow scanners](#workflow-scanners)
  - [Fuzzing the untrusted contract](#fuzzing-the-untrusted-contract)
- [Pre-commit hooks](#pre-commit-hooks)
- [Internationalization (i18n)](#internationalization-i18n)
- [Commit conventions](#commit-conventions)
- [Pull requests](#pull-requests)
- [Reporting bugs and requesting features](#reporting-bugs-and-requesting-features)

## Ground rules

These are non-negotiable. A change that breaks one of them will not be merged.

1. **The engine stays domain-agnostic.** Nothing under `src/dsoxlab/` may
   contain domain-specific logic (Linux, Ansible, Kubernetes, …). If you find
   yourself writing `if category == "linux"`, the logic belongs in the lab
   repository's `meta.yml`/`lab.yaml` contract, not in the engine.
2. **One CLI, one entry point.** `src/dsoxlab/cli.py` is the only entry point.
   Orchestration shell scripts live in the lab repositories, never here.
3. **Strict typing.** `mypy --strict` must stay green. Annotate everything; do
   not propagate untyped dictionaries.
4. **Portability.** No hardcoded personal paths or hosts. Use `pathlib.Path`
   and the XDG variables (`XDG_DATA_HOME`, `XDG_CONFIG_HOME`).
5. **Every user-facing string is translated.** No hardcoded strings in
   `cli.py` or `reporting/`. See [i18n](#internationalization-i18n).

## Development setup

Requirements: **Python 3.11+** and [uv](https://docs.astral.sh/uv/).

```bash
git clone https://github.com/stephrobert/dsoxlab.git
cd dsoxlab
uv sync                      # create the venv and install dev dependencies
uv tool install --editable . # optional: expose `dsoxlab` on your PATH
```

Test against a real lab repository to validate the agnostic design. Use **at
least two**, from different domains — that is the only way to prove the engine
carries no domain-specific logic:

```bash
cd ~/Projets/linux-dsoxlab-training && dsoxlab list-labs
cd ~/Projets/ansible-training && dsoxlab list-labs
```

## Quality gates

Run these before opening a pull request. CI runs the same checks.

```bash
uv run ruff check src/dsoxlab tests fuzz   # lint + security (flake8-bandit S rules)
uv run mypy src/dsoxlab                    # type-check (strict)
uv run pytest                              # tests
```

### Workflow scanners

If you touch anything under `.github/workflows/`, four scanners gate the build
and must stay at **zero finding**. They analyse the workflow YAML, so they run
without any project dependency:

```bash
actionlint                                    # syntax, invalid permission scopes, shellcheck
zizmor --offline .github/workflows/           # workflow vulnerabilities
poutine analyze_local . --fail-on-violation   # CI/CD exploitation chains
plumber analyze                               # trust graph + repository settings
```

The rules they enforce, and which are worth knowing before you write a line of
YAML:

- **Every action is pinned to a full 40-character commit SHA**, followed by a
  `# vX.Y.Z` comment. Never `@v4`, never `@main`: a tag is mutable, so it is a
  supply-chain hole.
- **`step-security/harden-runner` is the first step of every job.**
- `permissions: {}` at workflow level, minimal permissions per job.
- `actions/checkout` with `persist-credentials: false`, a pinned runner
  (`ubuntu-24.04`, not `ubuntu-latest`), a `timeout-minutes` and a `name:`.
- **Never interpolate `${{ … }}` into a `run:` block.** Pass the value through
  an `env:` block instead, or zizmor flags a template injection.
- A new third-party action must be added to `trustedGithubActions` in
  `.plumber.yaml`. If its creator is not Marketplace-verified, acknowledge it in
  `.poutine.yml` **by its exact purl** — never by disabling the rule, which
  would blind it to every other action.

One trap deserves its own line: **the required status checks match job names
exactly**. Renaming a job silently stops the old check from ever being
satisfied, and pull requests hang forever. Rename only if you update the branch
protection in the same move.

### Fuzzing the untrusted contract

`lab.yaml` and `meta.yml` come from lab-provider repositories: they are the
engine's untrusted input. `discovery/scanner.py` catches
`(KeyError, ValueError, yaml.YAMLError)` and skips the offending lab with a
warning — **anything raised outside that tuple escapes the handler and crashes
the CLI** on an unrelated command.

The harnesses in `fuzz/` assert that contract, and a short seeded run gates CI.
Run a longer campaign locally when you touch a parser:

```bash
uv sync --group fuzz
mkdir -p /tmp/fuzz-lab
uv run --group fuzz python fuzz/fuzz_lab_yaml.py \
    /tmp/fuzz-lab fuzz/corpus/lab_yaml/ \
    -dict=fuzz/dict/yaml_contract.dict -atheris_runs=100000
```

Pass the scratch directory **first**: libFuzzer writes what it finds into the
first corpus directory, and `fuzz/corpus/` is a curated seed set. A crash writes
a `crash-*` reproducer you can replay by passing it as the only argument. If you
add a field to the contract, add a seed for it — random bytes never rebuild a
keyword by chance, so the corpus and `fuzz/dict/yaml_contract.dict` are what
make the fuzzer reach your code.

## Pre-commit hooks

This repository ships public, so a set of [pre-commit](https://pre-commit.com/)
hooks guards every commit against leaking secrets or private keys and against
pushing artifacts that do not belong in the tree. Install them once after
cloning:

```bash
uv run pre-commit install --install-hooks
```

On each **commit** they run: hygiene checks (trailing whitespace, end-of-file,
YAML/JSON/TOML validity, large files, merge conflicts), private-key detection,
a TruffleHog secret scan, `ruff` (lint + security, autofix) and `mypy --strict`.
The full `pytest` suite runs on **push**. Run everything by hand with:

```bash
uv run pre-commit run --all-files
```

## Internationalization (i18n)

When you add or change a user-facing string:

- Add the key to **both** `src/dsoxlab/i18n/strings/en.py` **and**
  `src/dsoxlab/i18n/strings/fr.py`.
- English is the source language; the French value must be a faithful
  translation with correct diacritics.
- Verify both languages:

  ```bash
  DSOXLAB_LANG=en dsoxlab <command>
  DSOXLAB_LANG=fr dsoxlab <command>
  ```

When you add, remove or change a command or option, update **simultaneously**:
the command `help=_("…")` in `cli.py`, the EN + FR keys, and the matching
`fullhelp_commands` section in both languages. Never leave `fullhelp`
describing a command that no longer exists.

## Commit conventions

We use Conventional Commits with a module scope:

```
<type>(<module>): <short description>
```

Types: `feat`, `fix`, `docs`, `refactor`, `chore`, `test`, `ci`. Examples:

- `feat(discovery): support multi-repo via ~/.config/dsoxlab/config.yaml`
- `fix(runtimes/kvm): make snapshot revert idempotent when snapshot is absent`
- `docs(readme): document the incus runtime`

Keep commits focused and the history readable. Before a grouped commit, check
`git log --oneline -5` to match the style.

## Pull requests

- Branch from an up-to-date `main`, keep the scope tight, and fill in the PR
  template. Delete the branch once merged.
- Ensure lint, type-check and tests are green — plus the workflow scanners if
  you touched `.github/workflows/`.
- When behavior changes, update **both** `CHANGELOG.md` and `CHANGELOG.fr.md`.
  The project is bilingual: an English-only entry is an incomplete entry.
- When behavior changes, also bump the version in `pyproject.toml` and refresh
  `uv.lock` (`uv lock`). There is nothing to bump in `src/dsoxlab/__init__.py`:
  `__version__` is read from the installed package metadata, precisely so it
  cannot drift from `pyproject.toml`.
- If you add a command or option, confirm the i18n checklist above is done.

## Reporting bugs and requesting features

Use the GitHub issue templates. For bugs, include the `dsoxlab --version`
output, your OS, the exact command, and what you expected versus what happened.
For security issues, follow [SECURITY.md](./SECURITY.md) instead of opening a
public issue.
