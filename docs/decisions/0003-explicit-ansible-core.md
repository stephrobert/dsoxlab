# ADR-0003: `ansible-core` is a declared dependency, despite its 100 MB

**Status:** accepted
**Date:** 2026-08-19 (0.1.42)

**Language:** [English](./0003-explicit-ansible-core.md) · [Français](./0003-explicit-ansible-core.fr.md)

## Context

`ansible-runner` drives `ansible-core` programmatically (the official Red Hat
API, used by AAP and ansible-navigator). dsoxlab uses it to play the
`setup.yaml` and `cleanup.yaml` of `vm` labs.

The `pyproject.toml` comment long claimed the opposite of the truth:
`ansible-runner` does **not** pull `ansible-core` in transitively. Measured on a
fresh machine, the installed tool weighed 18 MB and its `bin/` contained neither
`ansible` nor `ansible-playbook`. Consequence: every `dsoxlab run` on a `vm` lab
exited with `rc=127`, the shell code for "command not found", which nothing
translated.

The `doctor` check made it worse by testing only that the `ansible_runner`
module imports: it reported OK on a machine where no playbook could run.

An audit run on a fresh Ubuntu 24.04 VM, the same release, measured **six
undocumented steps** between a green `dsoxlab doctor` and the first playable
`vm` lab; this was one of them.

## Decision

`ansible-core` is declared explicitly in `[project] dependencies`, next to
`ansible-runner`.

The rejected alternative was to keep it out and document a manual install for
`vm` catalogues. That is a tool that works only after a command nothing
documents, discovered through a raw `rc=127`.

## Consequences

- `ansible-core` weighs about **100 MB**, including for a catalogue that is
  entirely `shell` and will never use it. That is the price of a tool that works
  at install time rather than after an undocumented command.
- The `doctor` check now tests both halves (the module and the binary), and its
  error message names `ansible-core` rather than sending the user to reinstall
  what they already have.
- `tests/test_ansible_availability.py` reads `pyproject.toml` rather than the
  environment, so the declaration cannot silently disappear.

## What would reverse it

`ansible-runner` declaring `ansible-core` itself, or dsoxlab no longer playing
Ansible playbooks for `vm` labs. Making it an optional extra would only be worth
it if `shell`-only installs became a measured problem; until then the 100 MB is
the accepted cost.
