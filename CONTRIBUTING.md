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

Test against a real lab repository to validate the agnostic design (at least
two, e.g. `linux-training` and `ansible-training`):

```bash
cd ~/Projets/linux-training && dsoxlab list-labs
```

## Quality gates

Run these before opening a pull request. CI runs the same checks.

```bash
uv run ruff check src/dsoxlab   # lint + security (flake8-bandit S rules)
uv run mypy src/dsoxlab         # type-check (strict)
uv run pytest                   # tests
```

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

Types: `feat`, `fix`, `docs`, `refactor`, `chore`, `test`. Examples:

- `feat(discovery): support multi-repo via ~/.config/dsoxlab/config.yaml`
- `fix(runtimes/kvm): make snapshot revert idempotent when snapshot is absent`
- `docs(readme): document the incus runtime`

Keep commits focused and the history readable. Before a grouped commit, check
`git log --oneline -5` to match the style.

## Pull requests

- Branch from `main`, keep the scope tight, and fill in the PR template.
- Ensure lint, type-check and tests are green.
- Update the documentation and `CHANGELOG.md` when behavior changes.
- If you add a command or option, confirm the i18n checklist above is done.

## Reporting bugs and requesting features

Use the GitHub issue templates. For bugs, include the `dsoxlab --version`
output, your OS, the exact command, and what you expected versus what happened.
For security issues, follow [SECURITY.md](./SECURITY.md) instead of opening a
public issue.
