# ADR-0004: Upstream images are mutable, on purpose

**Status:** accepted
**Date:** 2026-08-24 (0.1.84)

**Language:** [English](./0004-mutable-upstream-images.md) · [Français](./0004-mutable-upstream-images.fr.md)

## Context

The seven image URLs of the packaged Terraform templates point at **mutable**
paths: `latest` at AlmaLinux, `current` at Ubuntu and Debian. No checksum is
pinned.

**What mutable costs.** An upstream image can change under our feet: a
regression from the publisher, a cloud-init that moves, a package withdrawn. The
reproducibility of a `provision` is therefore not guaranteed over time.

**What pinning would cost, and why it is worse here.** Ubuntu and Debian
republish their cloud images every few weeks, security fixes included. A pinned
checksum would have to be bumped every time; left undone, it would serve
learners an increasingly stale image, with its known vulnerabilities. The
hardening would then become the vector of the very problem it claims to
address.

## Decision

The mutable paths are kept, and no checksum is pinned. This is a decision, not
an oversight.

What makes the risk acceptable here:

- the URLs are HTTPS, on the official domains of the three distributions
  (`cloud-images.ubuntu.com`, `cloud.debian.org`, `repo.almalinux.org`): trust
  rests on TLS and on the publisher, as for any `apt install`;
- a lab VM is **disposable**: it lives for one exercise, holds no data, and
  `destroy` removes it;
- it is **not exposed**: the libvirt network is local to the learner's machine.

## Consequences

- A `provision` replayed months apart may not boot the same image. A regression
  upstream shows up in labs, not in dsoxlab's own CI.
- Learners always receive the publisher's latest security fixes without anyone
  having to bump a checksum.

## What would reverse it

If dsoxlab one day serves VMs beyond training (the track of
`ROADMAP-VM-GENERALISTE`), the calculation flips: a machine that lasts and
carries work deserves a pinned image. The gesture then: take the `SHA256SUMS`
each distribution publishes next to its image, keep it in a versioned file, and
verify it after download. This is not done today because it is not yet
justified, not because it would be hard.
