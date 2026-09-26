# The appliance: a ready-to-play virtual machine

**Audience:** anyone on Windows or macOS who wants to play labs without
installing anything, and anyone who prefers a throwaway machine to their own.

**Language:** [English](./appliance.md) · [Français](./appliance.fr.md)

The appliance is a Debian 13 virtual machine with dsoxlab, Ansible, Terraform
and a desktop already in place. You import it, you start it, you play.

![The dsoxlab appliance: `dsoxlab doctor` in a terminal on the XFCE
desktop](./assets/appliance-bureau.png)

*The appliance running in VirtualBox, a few minutes after import: `dsoxlab
doctor` on the desktop, 86 labs discovered, and the only choice left to make —
the hypervisor — named together with the command that settles it.*

**On Linux it is the wrong answer**, and this page says so plainly: downloading
half a gigabyte to avoid `uv tool install dsoxlab` makes no sense. It exists for
the systems where that command is not an option.

## Download

The images are attached to the GitHub Releases of **minor versions** (0.2.0,
0.3.0…), not to every patch: republishing half a gigabyte to change one line
would cost a lot and gain nothing. The one attached to the latest minor release
is the current one — the image itself pins no version of dsoxlab, and installs
the latest at first boot.

| File | For | Tested |
| --- | --- | --- |
| `dsoxlab-appliance-<version>.ova` | VirtualBox — Windows, Linux, Intel Mac | yes: import, boot, desktop |
| the same `.ova` | VMware Workstation and Fusion | not directly; the OVF validates against the DMTF schema and declares what VMware expects (`vmx-13`, LsiLogic, E1000, `streamOptimized`) |
| `dsoxlab-appliance-<version>.qcow2` | QEMU/KVM, libvirt, Proxmox | yes |
| `SHA256SUMS` | checking what you downloaded | — |

Both images are **x86-64**. See [Apple Silicon](#apple-silicon-m1-m4) below.

**Only the last two sets of images are kept.** Older minor releases keep their
page, their changelog and their Python distributions, but their `.ova` and
`.qcow2` are removed — roughly 900 MB each, for images that pin no dsoxlab
version and therefore offer nothing but weight once the next one exists. Take
the latest; there is no reason to want an older one.

## Import and start

In VirtualBox: **File → Import Appliance**, pick the `.ova`, accept. On the
command line, `VBoxManage import dsoxlab-appliance-<version>.ova`.

The machine advertises 4 vCPU and 8 GB. Lower it if your machine is smaller — 2
vCPU and 4 GB are enough for `shell` labs — in **Settings → System**.

For `vm` labs, though, **keep the 8 GB**: the lab machines run *inside* the
appliance, and `dsoxlab doctor` compares the memory available to what the
catalog declares. Measured with the Linux catalog, which declares 5120 MB: at
4 GB, `doctor` refuses to start and says exactly what is missing.

First login, on the console or in the desktop:

| | |
| --- | --- |
| user | `student` |
| password | `dsoxlab` |

**The password must be changed at that first login**: the build password is
public, it lives in this repository. The machine asks for it on its own.

## What the first boot does

The image pins nothing, so the first boot builds what would have gone stale:

1. it installs the **latest published dsoxlab**;
2. it installs the **hypervisors** (KVM, libvirt, Incus) — *only* if the host
   exposes nested virtualization, which it checks rather than assumes;
3. it installs the **XFCE desktop** and Firefox;
4. it **reboots**, because group membership and the graphical target only take
   effect at the next boot.

Count a few minutes, depending on your connection. The console shows every step.

**If something fails, the machine says so and starts over at the next boot.** It
does not mark itself as configured: a half-installed appliance that believes it
is complete is worse than one that admits it is not. The usual cause is no
network in the virtual machine — check its network adapter, then restart it.

## Playing `vm` labs: nested virtualization

Labs of type `shell` work everywhere. Labs of type `vm` start real machines
*inside* the appliance, which requires the host to allow it:

- **VirtualBox**: `VBoxManage modifyvm <name> --nested-hw-virt on`, appliance
  powered off. In the interface, **Settings → System → Processor → Enable
  Nested VT-x/AMD-V**.
- **VMware**: *Virtualize Intel VT-x/EPT or AMD-V/RVI*.
- **QEMU/libvirt**: the host's `kvm_intel`/`kvm_amd` module must have
  `nested=1`, and the CPU model must be passed through (`host-passthrough`).

You do not have to guess whether it worked:

```console
$ dsoxlab doctor
```

names what this machine can do and what is missing, and says in so many words
that nested virtualization is enabled on the **host** hypervisor, this machine
powered off.

![dsoxlab provisioning a lab's machines from the appliance's
terminal](./assets/appliance-lab-vm.png)

*`dsoxlab start` on a `vm` lab, inside the appliance: sixteen required checks
green, then Terraform bringing up the lab's three machines — VMs inside the
VM.*

## Apple Silicon (M1-M4)

**The appliance does not run on an Apple Silicon Mac**, and saying otherwise
would waste your afternoon. Both images are x86-64; Parallels, VMware Fusion
and UTM virtualize arm64 on these machines and do not emulate another
architecture at a usable speed. UTM can emulate x86-64 through QEMU's
interpreter, at roughly a tenth of native speed — enough to watch a boot, not
to play a lab.

An arm64 image is the obvious answer, and it is planned rather than done, for
two reasons worth knowing:

- GitHub's hosted arm64 runners **do not expose `/dev/kvm`**, so the CI would
  have to build that image under emulation, for hours.
- Nested virtualization on Apple Silicon only exists from the **M3** with macOS
  15 or later. So even with an arm64 image, `vm` labs would stay out of reach
  on most Macs; only `shell` labs would run.

Until then, on an Apple Silicon Mac, install the tool:
`uv tool install dsoxlab`. Every `shell` lab works, which is the whole
Terraform catalog and a good part of the others.

## What is inside

Debian 13, minimal, plus what a lab workstation needs: `git`, `curl`, `vim`,
`python3`, `man`, Ansible, Terraform, and after the first boot dsoxlab, the
hypervisors and the desktop. Documentation and locales other than English and
French are excluded from the packages, which is most of what keeps the image
under half a gigabyte.

The recipe is in [`packer/`](../packer/), built by the CI on a GitHub-hosted
runner. It is reproducible: nothing is hand-made in the image.

## Known limits

- **One user, one machine.** The appliance is not a shared classroom server; a
  trainer serving several learners wants [the trainer's page](./trainer.md).
- **The disk is 20 GB.** Enough for a catalog and a few lab VMs, not for a
  Kubernetes cluster of three nodes. Enlarge it in your hypervisor if needed.
- **No automatic update.** `uv tool upgrade dsoxlab` updates the tool; the image
  itself is only rebuilt at minor versions.
