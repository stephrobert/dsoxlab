# The declarative contract, version 1

**Audience:** catalog authors. The workflow around this reference is
[For the catalog author](./catalog-author.md).

**Language:** [English](./contract-v1.md) · [Français](./contract-v1.fr.md)

`meta.yml` and `lab.yaml` are the public interface of dsoxlab. They are what a
catalog author writes, and the only thing that ties their repository to the
tool. This page freezes what version 1 of that interface guarantees.

Two JSON Schemas describe the same contract for your editor and your CI:
[`schemas/meta.schema.json`](../schemas/meta.schema.json) and
[`schemas/lab.schema.json`](../schemas/lab.schema.json). They are checked
against the parser by a test, so they cannot quietly drift from the code.

---

## `schema_version`

Both files accept a `schema_version` integer at their root.

```yaml
schema_version: 1
repo:
  id: my-training
  category: my-domain
```

| Situation | What dsoxlab does |
| --- | --- |
| Field absent (every existing catalog) | Read as version **1**. Nothing to change. |
| `schema_version: 1` | Read as version 1. |
| `schema_version:` left blank | Read as version 1: an empty value is an absence. |
| A version newer than the tool understands, in `lab.yaml` | The lab is **left out**, and a message names the file, the version and the fix. The rest of the catalog is served normally. |
| A version newer than the tool understands, in `meta.yml` | The command **stops**. `meta.yml` describes the whole catalog: reading it wrong would make everything downstream untrustworthy. |
| Anything that is not a YAML integer ≥ 1 | Refused, and `dsoxlab validate-structure` names the file and the value. |

The read is deliberately strict where the rest of the contract is lenient:
`"1"`, `1.0` and `true` are refused. A version number is not a measurement you
round — `1.5` would silently become `1`, and silence is exactly what this field
exists to remove.

`dsoxlab validate-structure` reads `schema_version` **straight from disk**,
before discovery. That matters: every other check iterates over labs that were
already loaded, so a file the parser rejects normally slips through validation
without a word. This one sees it.

> **Not to be confused with the JSON output version.** `dsoxlab list-labs
> --json` emits a document carrying its own `schema` field. That one versions
> what dsoxlab **writes** for other programs; `schema_version` versions what
> dsoxlab **reads** from a catalog. Two contracts, two audiences, two rhythms.
> They are never bumped together out of reflex.

---

## `meta.yml` — repository root

Only `repo.id` and `repo.category` are required. A repository whose labs are all
`shell` has no `infra:` block at all, and that is a supported case, not an
omission.

### `repo` (required)

| Field | Required | Type | Notes |
| --- | --- | --- | --- |
| `id` | **yes** | string | Slug of the repository. Namespaces the state directory and the service containers. |
| `category` | **yes** | string | Free-form. Becomes the default `section` of every lab. dsoxlab knows no list of domains. |
| `title` | no | string | Human-readable name. |
| `blog_url` | no | string | Home page of the online course. |
| `description` | no | string | One paragraph. |

### `infra` (optional — required by `runtime: vm`)

| Field | Required | Type | Default | Notes |
| --- | --- | --- | --- | --- |
| `provider` | no | string **or** list of strings | `kvm` | Providers packaged with the tool: `kvm`, `incus`, `outscale`. A list means the learner chooses. |
| `network` | no | string | — | Network the VMs join, dedicated to this repository. |
| `cidr` | no | string | — | Subnet of that network. |
| `hosts` | no | list of mappings | `[]` | The VMs. See below. |
| `providers` | no | mapping | `{}` | Per-provider overrides, read by the matching Terraform module. Free-form values: each provider has its own variables. See below for the ones the packaged templates read. |

Provider resolution, first rule wins: `DSOXLAB_PROVIDER`, then the session
context set by `dsoxlab use --provider`, then a bare string or a single-item
list. Unresolved is not an error — only infrastructure commands require one.

### `infra.providers.<provider>`

Free-form, and passed to the Terraform module of that provider as-is. One key
is worth naming, because a fresh machine needs it:

| Field | Provider | Required | Type | Default | Notes |
| --- | --- | --- | --- | --- | --- |
| `storage_pool` | `kvm` | no | string | `default` | libvirt pool the volumes are created in. |

The default is what a stock libvirt install does *not* always give you: on a
fresh Ubuntu 24.04, `virsh pool-list --all` is empty, and `provision` stops on a
raw `Pool Not Found` from Terraform. Two ways out, and both are supported:
create the `default` pool (`dsoxlab doctor` prints the four commands), or point
this key at a pool you already own. Never edit the packaged template.

```yaml
infra:
  provider: kvm
  providers:
    kvm:
      storage_pool: labs-pool
```

### `infra.hosts[]`

| Field | Required | Type | Default | Notes |
| --- | --- | --- | --- | --- |
| `name` | **yes** | string | — | FQDN. Every `runtime.targets[].host` and every `roles` value of a lab must appear here. |
| `distro` | no | string | — | Drives the image and the cloud-init. Packaged today: `alma10`, `alma9`, `ubuntu26`, `ubuntu24`, `ubuntu22`, `debian13`, `debian12`. |
| `role` | no | string | — | Free-form, exposed as an Ansible host_var. |
| `ram_mb` | no | integer | `1024` | |
| `vcpu` | no | integer | `1` | |
| `disk_gb` | no | integer | `10` | |
| `extra_disk_gb` | no | integer | `0` | Second disk, for labs that need a real block device (partitioning, LVM, RAID). |
| `ip` | no | string | — | **Legacy.** Addresses come from the provider and are injected into the generated inventory. Do not declare them. |

### `sections[]` (optional)

| Field | Required | Type | Notes |
| --- | --- | --- | --- |
| `id` | **yes** | string | Slug of the section. |
| `title` | no | string | Shown as the bloc name. |
| `description` | no | string | One short line. |
| `labs` | no | list of strings | Paths relative to `<repo>/labs/`, in teaching order. |

`sections` orders and names the blocs. It never decides whether a lab exists:
that is settled by the presence of `labs/**/lab.yaml`, and the match is on the
path, never on the lab id.

### `meta.<lang>.yml`

A `meta.fr.yml` next to `meta.yml` overrides `repo.title`, `repo.description`,
`sections[].title` and `sections[].description` for that language, **and
nothing else**. Any other key in it is ignored — including `labs`: the teaching
order lives in `meta.yml` and is never translated.

Sections are matched by **`id`**, never by position: a section inserted at the
top of `meta.yml` would otherwise shift every translation below it, silently.

```yaml
# meta.yml — the base file is English, as everywhere in the contract
sections:
  - id: getting-started
    title: Discover the tool
```

```yaml
# meta.fr.yml
sections:
  - id: getting-started
    title: Découvrir l'outil
```

This is the same per-file convention as `lab.<lang>.yaml` and
`course.<lang>.yaml`. A per-field language suffix (`title_en:`) is **not** part
of the contract and is ignored: `dsoxlab validate-structure` reports it.

---

## `lab.yaml` — one per lab

### Root

| Field | Required | Type | Default | Notes |
| --- | --- | --- | --- | --- |
| `id` | **yes** | string | — | Unique in the repository. The CLI key. |
| `title` | **yes** | string | — | English title. |
| `level` | **yes** | string | — | Free-form, never validated against a list. |
| `skills` | **yes** | list of strings | — | Must not be empty. |
| `distros` | **yes** | list of strings | — | Must not be empty. |
| `doc_url` | **yes** | string | — | `http(s)` only. |
| `section` | no | string | `repo.category` | Declared, it is **always** kept — including when the value happens to name a technical domain. |
| `description` | no | string | `""` | |
| `track` | no | list of strings | `[]` | |
| `difficulty` | no | string | `beginner` | Never validated, only displayed. |
| `estimated_time` | no | string | `30m` | Only displayed. |
| `certification_tags` | no | list of strings | `[]` | Free-form: the tool stays domain-agnostic. |
| `lab_type` | no | enum | `lab` | `lab`, `challenge` or `capstone`. |
| `exam_passing_score` | no | integer | `0` | Pass mark of a mock exam, as a **percentage** of the lab scale. See below. |
| `bloc` | no | integer | derived | Normally **not written**: derived from `meta.yml` `sections[].labs[]`. |
| `bloc_order` | no | integer | derived | Same remark. |
| `runtime` | no | mapping | shell defaults | See below. |
| `validation` | no | mapping | see below | Purely declarative. |

`id`, `title` and `level` are required by the **parser**: without them the file
is not a lab at all. `skills`, `distros` and `doc_url` are required by
`dsoxlab validate-structure`: the file parses without them, but the lab is not
publishable.

### `exam_passing_score`

A `lab_type: capstone` is a mock exam, and an exam without a pass mark is not
one. Declare the bar, and dsoxlab renders a verdict:

```yaml
lab_type: capstone
exam_passing_score: 70   # per cent of the lab scale
```

| Where | What you get |
| --- | --- |
| `dsoxlab show` | The pass mark, before the learner starts. |
| `dsoxlab submit` | `Exam passed` or `Exam failed`, with the percentage and the bar. |
| `dsoxlab scores` | A **Verdict** column, on catalogs that have at least one exam. |

It is a **percentage**, not a number of points. The scale of a lab is the
`points` of its `challenge/hints.yaml` (100 by default, but free), so an
absolute threshold would mean something different from one lab to the next.

The comparison is exact: `score × 100 ≥ passing_score × scale`. A run worth
69.5 % of the scale fails a 70 % bar. A pass mark is not rounded in the
candidate's favour.

Left out, or set to `0`, the lab is not an exam and no verdict is ever
rendered — which is the case of every lab that is not a capstone or a drill.
`dsoxlab validate-structure` refuses a value outside `1..100`.

### `runtime`

| Field | Required | Type | Default | Notes |
| --- | --- | --- | --- | --- |
| `type` | no | enum | `shell` | `shell`, `vm`, and the backward-compatible aliases `kvm` and `incus`. Write `vm` in new labs. |
| `targets` | for `vm` | list of mappings | `[]` | Must not be empty for `vm`. |
| `default` | no | string | — | Must match one `targets[].name`. |
| `snapshot_required` | no | boolean | `false` | Binding, not informational. See below. |
| `session` | no | enum | `target` | `target` = SSH session on the host; `local` = local subshell. Only meaningful for `vm`. |
| `workdir` | for `shell` | string | `challenge/work` | Must not be empty for `shell`. Ignored for `vm`. |
| `fixtures` | no | list of strings | `[]` | Paths relative to `<lab>/fixtures/`, preserved under `workdir`. |
| `services` | no | list of mappings | `[]` | Containers the lab needs while it runs. |
| `topology` | no | string | `local` | **Deprecated.** Nothing reads it any more. |

A fixture **not listed** is **not copied**, even if it sits in `fixtures/`. An
absolute path, or one containing `..`, is refused: a fixture never writes
outside the workdir.

#### `runtime.snapshot_required`

This field **binds the tool**. Declaring `true` changes three commands:

| Command | With `snapshot_required: true` |
| --- | --- |
| `run` | Takes a checkpoint **before** `setup.yaml`, and **fails** if it cannot. The lab does not start without the safety net it asks for. |
| `reset` | Rolls the machine back to the checkpoint instead of replaying `cleanup.yaml`, then replays `setup.yaml`. |
| `clean` | Drops the checkpoint, and the overlay file it created with it. |

A lab that can live without a safety net declares `false`, which is the
default and what every lab in every catalogue declares today.

**What a dsoxlab checkpoint captures — and what it does not.** On the `kvm`
provider it is an **external disk snapshot** (`virsh snapshot-create-as
--disk-only --atomic`), never an internal one: the packaged Terraform template
boots its machines in UEFI, and libvirt refuses internal snapshots on pflash
firmware. Three consequences the contract states rather than leaves to be
discovered:

- **the disk is captured, the memory is not.** Rolling back reboots the
  machine from a consistent disk state; it does not put it back in the second
  before. For a lab that is the right trade-off, but a lab whose exercise
  depends on a running process must replay it, not expect it back;
- **a checkpoint creates an overlay file** next to the disk. `clean` and
  `destroy` remove it; nothing else does, so a lab that takes a checkpoint and
  is never cleaned leaves one behind until the infrastructure is destroyed;
- **rolling back is not `virsh snapshot-revert`.** dsoxlab stops the machine,
  empties the overlay and restarts it. The checkpoint survives, so it can be
  used again; but it must still be the disk's top layer, and dsoxlab refuses to
  roll back when it is not, rather than dropping the wrong file.

#### `runtime.targets[]`

| Field | Required | Type | Notes |
| --- | --- | --- | --- |
| `name` | **yes** | string | Short CLI id, passed to `--target`. |
| `host` | **yes** | string | FQDN, must appear in `meta.yml` `infra.hosts[].name`. |
| `label_en` | no | string | |
| `label_fr` | no | string | |
| `roles` | no | mapping | Extra hosts by role. Each role becomes the Ansible group `lab_<role>`. |

#### `runtime.services[]`

| Field | Required | Type | Default | Notes |
| --- | --- | --- | --- | --- |
| `name` | **yes** | string | — | Unique in the lab. Also the **hostname** other services reach it by. |
| `image` | **yes** | string | — | Image, tag included. dsoxlab launches exactly what you declare. |
| `ports` | no | list of strings | `[]` | Docker `-p` mappings, `host:container`. |
| `run_args` | no | list of strings | `[]` | Raw extra `docker run` flags. |
| `env` | no | mapping | `{}` | `-e NAME=value`. |
| `ready_tcp` | no | integer | `0` | **Host** port to wait on. On a published port this alone lies: Docker's proxy accepts before the service listens. |
| `ready_exec` | no | string or argv | `[]` | Probe run **inside** the container, retried until it succeeds. The only trustworthy readiness signal. |
| `ready_timeout` | no | integer | `90` | Seconds, for both probes. |
| `post_start` | no | list of strings or argv | `[]` | Commands run inside the container once ready. **Replayed on every start**, so they must be idempotent. |

### `validation`

| Field | Required | Type | Default |
| --- | --- | --- | --- |
| `functional` | no | boolean | `true` |
| `security` | no | boolean | `false` |
| `persistence_after_reboot` | no | boolean | `false` |

Purely declarative. dsoxlab never reads this block to decide anything: the tests
are what prove.

### `lab.<lang>.yaml`

A `lab.fr.yaml` next to `lab.yaml` overrides `title` and `description` for that
language, **and nothing else**. Any other key in it is ignored, and
`validate-structure` says so. An `id` is tolerated there without being read: it
names the lab for whoever opens the file.

---

## Enumerated values in v1

| Field | Values |
| --- | --- |
| `lab_type` | `lab`, `challenge`, `capstone` |
| `runtime.type` | `shell`, `vm`, `kvm`, `incus` |
| `runtime.session` | `target`, `local` |
| `schema_version` | `1` |

Everything else is free-form on purpose: `level`, `difficulty`, `section`,
`skills`, `distros`, `track`, `certification_tags` and `repo.category` belong to
the catalog, not to the engine. A closed list there would make dsoxlab know
about a technical domain, which it must not.

---

## What version 1 guarantees, and what would break it

**Stable.** Every field above keeps its name, its type and its meaning for the
whole life of v1. A file valid under v1 stays readable by every dsoxlab that
claims to support v1.

**Allowed without changing the version:**

- adding an **optional** field. An older dsoxlab ignores it, exactly as it
  already ignores any unknown key;
- adding a value to an enumerated list, when the value is optional to use;
- relaxing a constraint (a field that becomes optional).

**Requires a version 2:**

- removing a field, or renaming one;
- making an optional field required;
- changing the type or the meaning of an existing field;
- removing a value from an enumerated list;
- changing a default.

Unknown keys are **ignored by the parser**, **rejected by the JSON Schemas**
(`additionalProperties: false`), and **reported by `dsoxlab
validate-structure`**. That combination is on purpose, and each part answers a
different need:

- the **engine** stays tolerant, so a v1 tool survives a v1.1 catalog. That
  will not change: it is what makes the version scheme work at all;
- your **editor** underlines `skils:` as you type it;
- `validate-structure` fails on it, because tolerated is not the same as
  intended. Four keys written in good faith lived in the real catalogs and were
  read by nobody, including an `exam_passing_score` in eleven exam labs: their
  author believed they were setting a pass mark, and nothing set one. At the
  root of a `lab.yaml`, an unknown key is a typo or a disappointed expectation,
  almost never a deliberate extension.

The check covers `meta.yml`, `lab.yaml` and their translation files, and it
descends into every block the contract describes. It does **not** descend into
the free-form mappings — `runtime.targets[].roles`,
`runtime.services[].env`, `infra.providers.<provider>` — whose keys belong to
the catalog.

If a schema or `validate-structure` flags a key you believe in, the key is not
in the contract — check this page.

---

## Migration path to a future v2

None exists today: `1` is the only version dsoxlab reads, and no catalog
declares the field. Here is the path it will take, stated now so it is not
improvised later.

1. **A v2 is announced in the CHANGELOG** with the exact list of what changed,
   before any tool enforces it.
2. **The tool learns v2 before catalogs use it.** A dsoxlab that reads v2 keeps
   reading v1 files unchanged. Both versions coexist for at least one minor
   release.
3. **You upgrade the tool first**, then the catalog: `uv tool upgrade dsoxlab`.
   That order is not a preference. A v2 file read by a v1 tool is left out; a v1
   file read by a v2 tool still works.
4. **You migrate file by file.** `schema_version` is per file, not per
   repository: a catalog can hold v1 and v2 labs at once. This is why a lab the
   tool cannot read is skipped rather than fatal — otherwise nobody could ever
   publish the first v2 lab without breaking every learner not yet upgraded.
5. **`dsoxlab validate-structure` is the command that helps.** It reads
   `schema_version` from disk, before discovery, so it reports every file that
   is behind or ahead in one pass — including the ones no other check can see.

---

## Using the schemas

### In your editor

Put this line at the top of the file. The YAML extension of VS Code, and any
editor running `yaml-language-server`, will then complete fields and underline
mistakes as you type.

In `lab.yaml`:

```yaml
# yaml-language-server: $schema=https://raw.githubusercontent.com/stephrobert/dsoxlab/main/schemas/lab.schema.json
id: my-lab
title: My lab
```

In `meta.yml`:

```yaml
# yaml-language-server: $schema=https://raw.githubusercontent.com/stephrobert/dsoxlab/main/schemas/meta.schema.json
repo:
  id: my-training
  category: my-domain
```

The comment is a YAML comment: dsoxlab ignores it, and so does every other
tool that does not look for it.

### In CI, without installing dsoxlab

The URLs are plain files, so any JSON Schema validator can fetch them. This is
the point of publishing them: a catalog repository can check its own YAML
without depending on the Python tool.

### Which URL to use

Two forms, and they answer different questions.

| Form | URL | Use it when |
| --- | --- | --- |
| Moving | `https://raw.githubusercontent.com/stephrobert/dsoxlab/main/schemas/lab.schema.json` | You are authoring, and you want the schema to follow the contract as it evolves. This is the `$id` of the schema itself. |
| Pinned | `https://raw.githubusercontent.com/stephrobert/dsoxlab/v0.1.46/schemas/lab.schema.json` | You are in CI, and you want a result that does not change under you. Replace `v0.1.46` with the release you target. |

**Why `raw.githubusercontent.com` and not a domain of our own.** A schema URL
has one job: resolve, forever, to exactly the bytes it resolved to yesterday.
A tag on a public repository does that with no infrastructure to run, no
certificate to renew and no redirect to forget, and it is versioned by the
release itself — the tag that carries the code carries the schema that
describes it. A dedicated domain would add a service to keep alive for a file
that never changes, and a service that dies takes every author's editor with
it. The cost is a URL nobody would call pretty, and a dependency on GitHub
staying up, which the repository already has.

**Why `$id` points at `main` rather than at a tag.** `$id` is the identity of
the schema, not of a release. Re-stamping it on every tag would mean the same
schema had a different identity in each version, which is what `$id` exists to
prevent. Pinning belongs in the line you write in your file, where you can
choose it; identity belongs in the schema, where you cannot.
