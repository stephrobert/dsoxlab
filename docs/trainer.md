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

## Supported versions

| Component | Supported | How it was established |
| --- | --- | --- |
| **libvirt** | **8.0 or later** | Each of the three was provisioned for real, and the VM had to answer over SSH — not merely "Terraform did not complain". **8.0** in an Ubuntu 22.04 VM, where the defect of [#234](https://github.com/stephrobert/dsoxlab/issues/234) was first reproduced word for word; **9.0** in a Debian 12 VM, which nobody had ever tried; **10.0** on the reference machine, with a real `vm` lab from the Linux catalogue. Nothing below 8.0 has been tried, and that is the only reason a floor remains. |
| `dmacvicar/libvirt` provider | `~> 0.9` | The constraint the packaged template declares. No floor is known inside that range, so none is enforced. |

The floor was briefly 9.0, in 0.1.91, because the EFI firmware dsoxlab left
libvirt to select did not survive the Terraform provider reading the XML back.
That cause is gone: the template now **names** its loader, discovered through
`virsh domcapabilities`. Keeping the floor would have punished machines for a
defect that no longer exists — a threshold that outlives its reason excludes
without protecting anything.

`dsoxlab doctor` checks the libvirt floor and refuses a version below it, naming
the cause. It also prints the provider version actually pinned for this catalog,
which is what `terraform init` wrote in the state and not what the template asked
for: two machines honouring `~> 0.9` can be running different versions. That
version now appears in `dsoxlab support` too, so an issue carries it without
anyone having to ask.

Anything below the floor is not a hard block on the tool: only `provision` is
concerned, and a catalog whose labs are all `shell` never calls it.

---

## Running dsoxlab inside a virtual machine

A `vm` lab needs `/dev/kvm`. Inside a virtual machine, that means **nested
virtualization**, and nested virtualization is a property of the **host**, not of
the guest: nothing installed in the guest can produce it. It is enabled outside,
with the guest powered off.

| Host | Where it is enabled |
| --- | --- |
| **KVM / libvirt / Incus** | `/sys/module/kvm_intel/parameters/nested` (or `kvm_amd`) must read `Y`. Set `options kvm_intel nested=1` in `/etc/modprobe.d/` to make it permanent. |
| **VMware Workstation / Fusion** | *Virtualize Intel VT-x/EPT* in the VM's processor settings, machine powered off. |
| **VirtualBox** | Nested VT-x/AMD-V, which depends on the CPU — and is unavailable on a Windows where Hyper-V or WSL2 already holds the hypervisor. |
| **macOS on Apple Silicon** | Neither VirtualBox nor KVM exists; the packaged images are x86_64, so this is a separate road (UTM/QEMU), not a setting to flip. |

`dsoxlab doctor` names this case rather than leaving you to guess. When `/dev/kvm`
is missing it first asks where it is running, through `systemd-detect-virt` and,
failing that, the `hypervisor` flag of `/proc/cpuinfo`. Inside a virtual machine
it says nested virtualization is unavailable and names the hypervisor it detected;
on a physical machine it sends you to the BIOS or UEFI setup. It used to offer
both at once, which meant telling half its readers to visit a BIOS their machine
does not have.

Sizing, if the guest is to run the `vm` labs of a full catalog: **4 vCPU and 8 GB
for the guest itself**, measured, not estimated — the three hosts of the Linux
catalog allocate 5120 MB between them, and the CPU is what decides whether they
all answer inside the 180-second window. A guest with 2 vCPU has been seen
reporting a host ready at 181 seconds.

A catalog whose labs are all `shell` needs none of this: it never calls
`provision`, and `doctor` keeps every hypervisor check in the informational table.

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
