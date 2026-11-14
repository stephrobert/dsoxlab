# ADR-0005: First-boot packages do not block, but a bad finish is said

**Status:** accepted
**Date:** 2026-08-24 (0.1.84, issue #178)

**Language:** [English](./0005-non-blocking-first-boot-packages.md) · [Français](./0005-non-blocking-first-boot-packages.fr.md)

## Context

Each cloud-init template sets a `packages:` block installed at the machine's
**first boot**: 15 entries for AlmaLinux, 14 for Debian and Ubuntu (counted on
2026-08-24, recounted unchanged on 2026-11-14). Each is a network dependency, at the most fragile moment of a
lab's life cycle.

**What it costs.** Offline, behind a corporate proxy, or on a slow mirror,
cloud-init ends up `degraded`. The symptom was the worst possible:
`wait_for_hosts_ready` ran `cloud-init status --wait >/dev/null 2>&1 || true`,
so both the state and the return code went to the bin. `provision` announced
hosts **ready**, then the labs failed on missing commands, and nothing linked
the two. It is also what inflates the first boot inside the waiting budget of
`wait_for_hosts_ready`.

## Decision

**Rejected: blocking on a `degraded`.** cloud-init does not say *which* package
failed: it returns a global state. Failing `provision` would treat a missing
`tree` like a missing `lvm2`, when the first prevents no lab and the second
breaks a whole family of them. A block without granularity gets worked around,
and a guard that gets worked around guards nothing.

**Rejected for now: pre-baking images.** That is the real answer: a package
already present is not a network dependency. But building and publishing images
is a project in its own right, with its own life cycle and its own supply chain.
It lives outside this repository.

**Rejected: declaring packages lab by lab.** On paper the fairest solution: each
lab announces what it needs, and `run` checks it. It changes the frozen v1
`lab.yaml` contract, for a benefit the two measures below obtain without
breaking anything.

**Retained: make the failure visible, at the three moments it matters.**

1. **Before.** The `egress` check of `dsoxlab doctor` reaches the image mirrors
   declared by the templates. On a repository that provisions VMs it is
   **required**: a room without outbound access is seen before launching
   anything, not three labs later.
2. **During.** `wait_for_hosts_ready` now reads the return code of
   `cloud-init status --wait` and its `--long` output, instead of throwing them
   into `/dev/null`. A host whose configuration finished badly **says so on
   screen**, with what cloud-init reported.
3. **After.** The message names the host, which makes the recovery gesture
   immediate: `ssh <host>` then `sudo cloud-init status --long` to read the
   detail, and the manual install of the missing package.

Handing back control remains the right decision: what matters to continue is
that cloud-init has **finished**. But finishing badly must be said.

## Consequences

- `provision` does not fail on a `degraded` cloud-init; it warns and names the
  host.
- `egress` is a required `doctor` check on any catalogue that provisions VMs.
- `tests/test_cloud_init_degrade.py` holds the "during" half.

## What would reverse it

The day images are pre-baked, the `packages:` block empties of everything that
is not specific to the machine, and the `egress` check stops being required to
provision. That is the direction of travel, not one more workaround.
