# Infrastructure without labs

**Audience:** anyone who needs throwaway machines and has no exercise to write.
Not the learner, who never opens a `meta.yml`, and not the catalog author, whose
page is [catalog-author.md](./catalog-author.md).

**Language:** [English](./infra-only.md) · [Français](./infra-only.fr.md)

dsoxlab drives teaching labs, but its infrastructure layer does not know that.
`provision`, `destroy`, `ssh` and `infra status` read `meta.yml` and nothing
else: no progress database, no scoring, no hints, no lab discovery. You can
therefore use dsoxlab as a **provisioner of throwaway VMs**, without writing a
single exercise.

Typical uses: replaying a tutorial on a clean machine before publishing it,
reproducing a bug on three distributions, getting a cluster that a container
cannot stand in for because the test needs a real kernel, systemd or a firewall.

## The whole file

A `meta.yml` at the root of a directory, and that is all:

```yaml
repo:
  id: my-stack
  title: "Throwaway VMs"

infra:
  provider: kvm
  network: lab-stack
  cidr: 10.10.90.0/24
  hosts:
    - name: db.lab
      distro: debian13
      ram_mb: 2048
    - name: app.lab
      distro: ubuntu24
```

No `labs/` directory, no `repo.category`, no Terraform, no cloud-init: the
templates for the three providers (kvm, incus, outscale) are packaged inside the
tool. `repo.id` is the only required field; it namespaces the Terraform state and
the generated inventory.

Then:

```bash
dsoxlab provision        # terraform apply, then wait for SSH on every host
dsoxlab infra status     # who answers, and why the silent ones do not
dsoxlab ssh db.lab       # a shell on a node
dsoxlab destroy          # including machines left outside the state
```

## What applies, and what does not

| Command | On a stack with no lab |
| --- | --- |
| `provision`, `destroy`, `ssh`, `infra status` | work fully |
| `doctor` | works, and marks terraform, the hypervisor and outbound access **required** as soon as `infra.hosts` is not empty |
| `validate-structure` | passes, and says nothing about `repo.category` while no lab exists |
| `list-labs`, `show` | print "no lab found", which is not an error |
| `run`, `check`, `submit`, `scores`, `progress`, `next`, `hint`, `course`, `challenge`, `guide` | have no object: they all need a lab |

No `.dsoxlab.db` is created as long as no command writes progress.

## Where the state lives

Nothing is written into your directory except `.dsoxlab-context.json`, which
holds the active provider. Everything else is out of the way:

- Terraform state: `~/.local/state/dsoxlab/<repo-id>/terraform/<provider>/`
- Inventory and generated `ssh_config`: `~/.cache/dsoxlab/<repo-id>/`
- Write lock: `~/.local/state/dsoxlab/<repo-id>/dsoxlab.lock`
- Log: `~/.local/state/dsoxlab/dsoxlab.log`

Two accounts are created on every node by cloud-init, both key-only and
passwordless for sudo: `ansible`, the automation service account and the one
dsoxlab connects with, and `student`, the human account. Anything that restricts
logins must target `ansible`.

The `ssh/id_ed25519.pub` public key of the directory is the one deployed. Create
the pair with `dsoxlab instructor bootstrap` if you do not have one.

## Its limits

**Containers are not available this way.** `runtime.services` is declared *per
lab*, in `lab.yaml`, and its lifecycle hangs off `run`, `check` and `clean`.
There is no container stack at `meta.yml` level. For containers, you need a lab.

**Addresses derive from position.** The IP and MAC of a host come from its index
in `infra.hosts`. Inserting a host in the middle reassigns the ones that follow,
and libvirt refuses to update an existing network. Add at the end of the list.

**Two KVM stacks must not run at once.** MAC addresses carry no repository
prefix, so two directories give the same address to their VMs of equal index,
and one of the two stays unreachable.

## Mixing the two

Nothing forbids a stack from also carrying labs: they are then ordinary labs,
with scoring, progress and hints. If you only want to carry test suites without
turning them into exercises, know that dsoxlab will still treat them as labs.

## To go further

- [The v1 contract](./contract-v1.md), field by field
- [Where dsoxlab writes](./files.md)
- [Command reference](./commands.md)
