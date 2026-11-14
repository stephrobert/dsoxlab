# ADR-0001: Two runtimes, with the providers underneath

**Status:** accepted
**Date:** 2026-07-15

**Language:** [English](./0001-two-runtimes.md) · [Français](./0001-two-runtimes.fr.md)

## Context

A lab needs somewhere to run. Some exercises run on the learner's own machine
(a shell, Terraform, a container emulator); others need a machine of their own,
reached over SSH. The machines themselves can come from several backends:
KVM/libvirt, Incus, Outscale, and more were planned (Proxmox, AWS, GCP, Azure,
Vagrant).

The early contract named the backend in the lab: `runtime.type: kvm` or
`runtime.type: incus`. That ties a lab to one hypervisor, and every new backend
would have meant a new runtime type, a new adapter and a new value for every
catalogue author to learn.

## Decision

There are **two runtimes, and only two**: `shell` and `vm`.

- `shell` runs on the learner's machine. Its preparation is declarative
  (`runtime.workdir`, `runtime.fixtures`), plus an optional `setup.yaml` played
  on `localhost`.
- `vm` is **provider-agnostic**: the same lab runs on KVM, Incus, Outscale or a
  future backend without modification. Which backend serves the VM is the
  **catalogue's** decision, taken in `meta.yml: infra.provider`, not the lab's.

The `kvm` and `incus` values of `runtime.type` are kept as backward-compatible
aliases, handled by `VmRuntime` exactly like `vm`. No removal is planned; a new
lab writes `vm`.

## Consequences

- `runtimes/` holds two adapters, `ShellRuntime` and `VmRuntime`, selected by
  `RuntimeManager`. The backend-specific part lives in the packaged Terraform
  templates (`templates/terraform/<provider>/`) and in `infra/`, not in a
  runtime.
- Adding a provider is a pull request on dsoxlab only: a template folder that
  respects the contract of `templates/terraform/README.md`. Catalogues switch
  through `meta.yml: infra.provider` or `DSOXLAB_PROVIDER=<provider>`.
- A catalogue with no `infra:` block (all its labs `shell`) never calls
  `provision`. `terraform-dsoxlab-training` is that case, and it is the
  counter-example that catches regressions of domain neutrality.
- The aliases are a permanent cost: every place that branches on the runtime
  type must accept `vm`, `kvm` and `incus` together. A display table that knew
  `kvm` and `incus` but not `vm` once printed "?" on every `vm` lab (fixed in
  0.1.26, 2026-07-23).

## What would reverse it

A kind of environment that is neither a local shell nor a machine reachable
over SSH (for instance a runtime that needs a client library of its own). The
rule then is not to stretch `vm`: isolate it in `runtimes/<name>.py`, make it
opt-in through `is_available()`, and never import its library as a runtime
dependency of the tool.
