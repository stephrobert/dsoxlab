# dsoxlab for the trainer

**Audience:** you run the infrastructure the labs need — machines, providers,
accounts, snapshots. Writing the labs is [another page](./catalog-author.md);
playing them is [a third one](./learner.md).

**Language:** [English](./trainer.md) · [Français](./trainer.fr.md)

---

## Only `vm` labs need any of this

A catalog made of `shell` labs needs no infrastructure at all: the exercise runs
on the learner's own machine, `dsoxlab provision` is never called, and the
`meta.yml` carries no `infra:` block. That is a supported catalog, not an
incomplete one.

Everything below applies to catalogs that declare `runtime.type: vm`.

---

## The infrastructure is packaged in the tool

Terraform modules (`kvm`, `incus`, `outscale`) and cloud-init templates
(AlmaLinux, Ubuntu, Debian) live **inside dsoxlab**. A catalog ships **no**
Terraform and **no** cloud-init: it declares `infra:` in its `meta.yml` and puts
its public key in `ssh/id_ed25519.pub`.

`dsoxlab provision` copies the templates to
`~/.local/state/dsoxlab/<catalog-id>/`, generates
`.dsoxlab.auto.tfvars.json` from the `meta.yml`, and runs Terraform there. The
state never lands in the lab repository.

```yaml
# meta.yml
infra:
  provider: kvm                 # or a list of candidates
  network: lab-linux            # libvirt network of this catalog
  cidr: 10.10.10.0/24
  hosts:
    - name: alma-1.lab
      distro: alma10
      ram_mb: 2048
      vcpu: 2
      disk_gb: 20
      extra_disk_gb: 5          # second disk (/dev/vdb), for LVM or RAID labs
```

Do not declare IP addresses: they come from Terraform outputs, and the inventory
is generated from them. The field-by-field reference, including the
`infra.providers.<provider>` overrides, is in
[the v1 contract](./contract-v1.md).

Each catalog that provisions machines should own its libvirt network, so two
catalogs never collide on the same subnet.

---

## Getting started

```bash
dsoxlab instructor bootstrap    # generate <catalog>/ssh/id_ed25519 if missing,
                                # and check terraform + ansible-runner
dsoxlab doctor                  # what this catalog needs, and what is missing
dsoxlab provision               # terraform apply on the current provider
dsoxlab status                  # can we reach every declared host, and if not, why
dsoxlab ssh <host>              # an interactive session on one of them
dsoxlab destroy                 # tear it down
```

`provision --host <fqdn>` targets a single machine and is repeatable; without
it, the whole plan is applied. Shared resources (the network, the base images)
are handled by Terraform's dependency graph either way.

`dsoxlab doctor` sorts its findings into **two tables**: what is *required for
this catalog*, and what is merely *informational*. The sort depends on three
facts only — does the catalog have `vm` labs, which provider is active, which
providers it declares — never on the domain. A hypervisor this catalog does not
use never shows up in red.

---

## Choosing a provider

First rule that matches wins: `DSOXLAB_PROVIDER` in the environment, then
`active_provider` in the context file (set by `dsoxlab use --provider`), then a
`meta.yml` declaring a single provider. Several candidates and no explicit
choice is not an error in itself: only the infrastructure commands refuse to
proceed, and they say so.

```bash
dsoxlab use --provider kvm      # persistent, for this catalog
DSOXLAB_PROVIDER=incus dsoxlab provision   # one command only
```

Each provider keeps its own Terraform state, under
`~/.local/state/dsoxlab/<catalog-id>/terraform/<provider>/`. Switching provider
therefore does not destroy what the other one holds — which is convenient, and
also how one forgets a running fleet. `dsoxlab status` is the cheap habit.

---

## Two accounts, and why it matters to the labs

cloud-init creates the same two accounts on every node, both hardened the same
way (member of `wheel`/`sudo`, `sudo NOPASSWD:ALL`, SSH key only, no login
password, `ssh_pwauth: false`):

| Account | Role |
| --- | --- |
| `ansible` | The **service** account for automation. This is what dsoxlab and the labs' playbooks connect as (`ansible_user: ansible`, and the same in the generated `ssh_config`) |
| `student` | The **human** account, on the machine the learner drives |

The separation is deliberate: traceability and revocation. The consequence for
lab authors is concrete — anything that restricts login (`AllowUsers`,
`remote_user`) must name **`ansible`**, never `student`, or the next dsoxlab
command locks itself out.

---

## Snapshots

`snapshot_required: true` in a lab's `runtime` **commits the tool**, it does not
inform it:

- `run` takes a **disk** restore point before playing `setup.yaml`, and
  **fails** if it cannot — a lab that asks for a safety net does not start
  without one;
- `reset` returns the machine to that point instead of replaying
  `cleanup.yaml`;
- `clean` removes the restore point, and the overlay file it created with it.

Memory state is not captured: recovery restarts from a coherent disk, not from
the second before.

---

## Machines that outlive their state

A failed `provision` can leave domains defined on the hypervisor but outside the
Terraform state. Reprovisioning on top of them would produce a fleet nobody
tracks, so dsoxlab refuses instead, and two exit codes say which side failed:

| Code | Meaning |
| --- | --- |
| `5` | `provision` found orphan domains and stopped. The message names the command that removes them |
| `6` | `destroy` could not remove them. Something on the hypervisor still holds them |

`destroy` removes those orphans too, after confirmation (`--yes` skips it), and
exits non-zero if any remains. A `destroy` that reports success while machines
are still up is the failure mode this replaced.

---

## Where everything is kept

Terraform state, the write lock, the generated inventory and `ssh_config`: all
of it is listed on [Where dsoxlab writes](./files.md). Two points a trainer
should keep in mind:

- **The generated `ssh_config` is a cache** (`~/.cache/dsoxlab/<catalog-id>/`).
  It is regenerated on demand, but also purgeable: anything pointing at it (an
  `Include`, an IDE profile) must survive its disappearance. The fragment
  written to `~/.ssh/config.d/<catalog-id>.conf` is the stable one.
- **One catalog, one lock.** A second concurrent command that writes exits with
  code `7` and names the first. Two clones of the same catalog share the lock,
  because they share the Terraform state.

---

## Going further

- [The v1 contract, field by field](./contract-v1.md)
- [Where dsoxlab writes](./files.md)
- [Writing the labs](./catalog-author.md)
