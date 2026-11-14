# ADR-0013: Refuse to touch a state that holds hosts this `meta.yml` does not declare

**Status:** accepted
**Date:** 2026-11-14 (0.9.1, issue #357)

**Language:** [English](./0013-refuse-out-of-contract-hosts.md) · [Français](./0013-refuse-out-of-contract-hosts.fr.md)

## Context

The Terraform state is named by `repo.id`, not by path
(`~/.local/state/dsoxlab/<catalog-id>/terraform/<provider>/`). Two checkouts of
one repository (two clones, two git worktrees) therefore share one state. When
one of them declares a host the other ignores, an `apply` without `-target`
from the second takes that host out of the `for_each`, and Terraform
**destroys** it. The checkout declaring fewer hosts used to destroy the other's
machines on its first `provision`, without a word, a VM in the middle of a lab
included.

## Decision

`provision` (with or without `--host`) and `destroy --optional-hosts` name every
machine of the state that is neither a common nor an optional host of this
`meta.yml`, and **refuse** with exit code **12** (`HOTES_HORS_CONTRAT`).
`provision --prune` destroys them on purpose, naming them. `destroy` names them
before asking, even with `--yes`.

Refusing was chosen over the two other options:

- **Keeping them silently in `var.hosts`** is impossible: this `meta.yml` does
  not know their size or distribution.
- **Destroying them after a warning** still loses a VM that another session may
  be using in the middle of a lab.

A refusal costs one command; a lost VM costs the other person's work.

The refusal holds **even with `--host`**, which would not destroy them: the gap
is there, and the next `provision` without `--host` would take them. Better
said at first contact, before anything has been built.

## Consequences

- A new exit code, 12, joins the contract of [exit codes](../exit-codes.md).
- An unreadable state yields an empty list: Terraform will fail by itself on
  that same file, before planning anything.
- The same guard protects the removal of optional hosts
  ([ADR-0012](./0012-optional-hosts-stable-index.md)), since that removal goes
  through an `apply` without `-target` too.

## What would reverse it

A state named per checkout (by path) rather than per `repo.id`. Two checkouts
would then no longer share machines at all, but they would also stop sharing the
lock and the work-dir that [ADR-0002](./0002-per-catalog-flock-lock.md) relies
on, so that is a larger decision than this one.
