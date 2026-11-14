# ADR-0012: Optional hosts get a stable index and leave through an `apply` without `-target`

**Status:** accepted
**Date:** 2026-11-14 (0.9.0, issue #365)

**Language:** [English](./0012-optional-hosts-stable-index.md) · [Français](./0012-optional-hosts-stable-index.fr.md)

## Context

Two high-availability labs of the Kubernetes catalogue want two more control
planes and a load balancer, about **5.6 GB**. Added to `infra.hosts`, they would
have pushed every learner of that catalogue past **16 GB** for the sake of two
labs. Hence `infra.optional_hosts` in `meta.yml`: hosts declared once, started
only by the labs that name them.

Two mechanisms of the packaged templates did not survive hosts that come and go:

- **Addresses derived from the rank in `var.hosts`.** Starting one optional host
  without its neighbour would shift an address from one provision to the next.
  And the libvirt provider fails on **any** in-place update of a running domain:
  measured in 0.8.1 (2026-11-09) with `dmacvicar/libvirt` **0.9.7**, its `.id`
  went from 21 to 22 between the write and the read-back ("Provider produced
  inconsistent result after apply"). A bench on a stopped domain does not see
  it.
- **`terraform destroy -target` to remove one host.** Terraform records
  dependencies at the level of the resource, not of the instance. Measured on a
  three-host park (0.1.24, 2026-07-23): asking for one host planned **7**
  resources for destruction, not 4.

## Decision

**A host's address derives from an explicit index**, `hosts[].index`, its
position in the **full** list of the `meta.yml`, common hosts first, never its
position in the list actually sent to Terraform. The three packaged templates
(kvm, incus, outscale) read it.

**Optional hosts leave through an `apply` without `-target`** whose `var.hosts`
no longer carries them: they leave the `for_each`, and Terraform plans the
destruction of **their instances only**. No `destroy -target`, which takes the
other machines with it.

The flip side is accepted: that `apply` also realigns the rest on the
configuration, as a `provision` would. Common hosts are never destroyed by it,
since they stay in `var.hosts`.

**A `provision` keeps the optional hosts already in the state.** A `provision`
of the catalogue must not destroy the machines a lab started, and removing them
from `var.hosts` would do exactly that. An unreadable state makes all optional
hosts retained: at worst one is created too many, whereas leaving them out would
destroy some.

## Consequences

- For a catalogue without optional hosts, the index equals the former rank: no
  address moves. Measured on 2026-11-14 on the Kubernetes catalogue (three KVM
  machines running): a `terraform plan` on a copy of its state, with the 0.9.0
  templates and variables, showed no change.
- Measured on a real libvirt 10 hypervisor on 2026-11-14 (one common host, two
  optional): `run` of a lab naming the second optional host started it at `.13`
  (its position), not `.12` (its rank among running hosts); a second
  `provision` left a plan with no change and both libvirt domain ids untouched;
  `destroy --optional-hosts` removed it alone. The same run on Incus 7.2, the
  same day, gave the same result once the empty `user.lab.role` key was fixed
  (0.9.1).
- `clean` and `reset` keep optional hosts: rebuilding several machines on every
  try costs minutes. `destroy --optional-hosts` removes them, and only them.
- An `apply` without `-target` would also destroy machines that a **different**
  `meta.yml` sharing the same state declared. That risk is the subject of
  [ADR-0013](./0013-refuse-out-of-contract-hosts.md).

## What would reverse it

A Terraform provider that records dependencies per instance, making a targeted
destroy safe, would remove the need for the `apply` route. The stable index
stays as long as an address is derived from a position at all.
