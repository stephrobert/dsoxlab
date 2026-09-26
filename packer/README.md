# The dsoxlab appliance

A ready-to-play VM: dsoxlab, Terraform and Ansible already installed, so nothing
has to be set up by hand.

**Who it is for: Windows and macOS.** On Linux, `uv tool install dsoxlab` is the
answer, and `dsoxlab demo` gives you a first lab with no hypervisor at all —
downloading a gigabyte to avoid one command would make no sense.

## What the image does and does not pin

It **does not pin a dsoxlab version.** The first boot installs the latest
published one. Pinning would make the image stale the day after the next fix, and
would force us to republish a gigabyte for every patch.

It **does not ship the hypervisors either.** The first boot installs KVM and Incus
*only if the host exposes nested virtualization*, checked live rather than assumed.
Without it, `shell` labs work and `vm` labs cannot — and `dsoxlab doctor` says so,
naming the detected hypervisor instead of pointing at a BIOS a virtual machine
does not have.

That is why the image is rebuilt on **minor tags only** (`v0.3.0`, `v0.4.0`), not
on every patch release.

## Building it

```bash
cd packer
packer init .
packer validate -var "image_version=dev" \
  -var "iso_url=https://cdimage.debian.org/debian-cd/current/amd64/iso-cd/debian-13.x.y-amd64-netinst.iso" \
  -var "iso_checksum=sha256:…" .
packer build  -var "image_version=dev" -var "iso_url=…" -var "iso_checksum=…" .
```

The CI does this on a **GitHub-hosted runner**, with no self-hosted machine:
Linux runners expose `/dev/kvm`, so QEMU is accelerated. That is the whole reason
this recipe uses the `qemu` builder rather than `virtualbox-iso`, which would
require VirtualBox and therefore a runner of our own.

Two consequences worth knowing:

- the native output is **qcow2**, which is what trainers and Proxmox want;
- the **OVA is derived** from it by `faire-ova.sh`, using `qemu-img` and `tar`
  only. No `ovftool` — it is proprietary and needs a Broadcom account — and no
  VirtualBox in the build chain.

## What was verified, rather than assumed

Before this recipe was committed, the chain was run end to end locally:

| Step | Evidence |
| --- | --- |
| plugin and config | `packer init` installs qemu v1.1.6; `packer validate` passes |
| accelerated build | a build finishes in about a minute on a throwaway ISO, and `qemu-img check` finds no error in the qcow2 |
| qcow2 → VMDK | `streamOptimized` confirmed, and the raw content comes back with the **same SHA256** after conversion |
| VMDK → OVA | OVF well-formed, manifest verified by `sha256sum -c`, `.ovf` first in the tar |
| OVA → VirtualBox | **`Successfully imported the appliance`** in VirtualBox 7.0, disk attached to the SCSI controller |

Those runs caught two real defects, which is why they were worth doing:

1. without `AddressOnParent` on the disk item, VirtualBox reads an uninitialised
   channel and refuses the import (`channel=-522241808`);
2. a VMDK made from a disk that was **never written** fails at medium creation.
   A real build is not exposed to it — the disk carries a full installation — but
   a test bench is.

## Sizing

The OVF advertises **4 vCPU and 8 GB**, and those numbers are measured, not
guessed: the three hosts of the Linux catalog allocate 5120 MB between them, and
the CPU is what decides whether they all answer inside the 180-second window. A
guest with 2 vCPU has been observed reporting a host ready at 181 seconds.

Reduce them if you only play `shell` labs — you now know what it costs.

## The files

| File | Role |
| --- | --- |
| `dsoxlab-appliance.pkr.hcl` | the build: `qemu` builder, KVM, qcow2 output |
| `http/preseed.cfg` | the automated Debian 13 install |
| `scripts/10-base.sh` | the system: packages every lab machine needs |
| `scripts/20-outils.sh` | `uv`, Terraform, `ansible-core` |
| `scripts/30-premier-demarrage.sh` | what happens on the user's first boot |
| `scripts/90-nettoyage.sh` | what decides the final weight |
| `faire-ova.sh` | derives the importable OVA from the qcow2 |
