# dsoxlab for the catalog author

**Audience:** you are writing labs, in your own repository. You want to know
what dsoxlab reads, what it refuses, and where it will silently ignore you.

**Language:** [English](./catalog-author.md) · [Français](./catalog-author.fr.md)

The field-by-field reference is [the v1 contract](./contract-v1.md). This page
is the workflow around it: how a catalog is laid out, in which order to check
it, and the traps that cost the most time.

---

## What a catalog is

A repository with a root `meta.yml` and one `lab.yaml` per lab under `labs/`.
Nothing else ties it to dsoxlab: no dependency to install, no plugin to write.
Removing dsoxlab must still leave the labs playable by hand
(`ansible-playbook setup.yaml` then `pytest`) — that is the test of
non-coupling, and it is what keeps the engine domain-agnostic.

```text
my-training/
├── meta.yml                    ← catalog: identity, topology, section ordering
├── meta.fr.yml                 ← optional: French titles and descriptions
├── ssh/id_ed25519.pub          ← only if the catalog declares vm labs
└── labs/
    └── my-domain/l1/first-lab/
        ├── lab.yaml            ← required
        ├── README.md           ← required
        ├── scenario.md         ← required
        ├── setup.yaml          ← required for runtime vm (Ansible)
        ├── cleanup.yaml        ← required for runtime vm (Ansible)
        ├── fixtures/           ← optional, for runtime shell
        └── challenge/
            ├── README.md       ← the mission shown by `dsoxlab challenge`
            ├── hints.yaml      ← optional: the hints and their cost
            └── tests/
                └── test_functional.py   ← required, exact name
```

`challenge/tests/test_functional.py` is the only test file name the structure
validator requires. Add others next to it if you like — pytest collects the
directory.

---

## The order of operations

**`dsoxlab list-labs` first, `dsoxlab validate-structure` second.** Not the
other way round, and this is the single most useful thing on this page.

A `lab.yaml` that raises while being parsed makes its lab **disappear in
silence**: the scanner logs a warning and moves on. `validate-structure` then
iterates over the labs that were *successfully discovered*, so it validates the
survivors and says nothing about the casualty. A lab missing from `list-labs` is
almost always a `lab.yaml` that raises.

The warning does reach `~/.local/state/dsoxlab/dsoxlab.log` (and `dsoxlab
support` collects it), so the diagnosis is one command away once you know where
to look.

One exception, since 0.1.46: a `schema_version` this dsoxlab cannot read is
announced on screen and names the file, instead of vanishing.

---

## What `validate-structure` checks

Three families, all local and offline by default:

**Structure.** `lab.yaml`, `README.md`, `scenario.md`, `challenge/tests/` and
`challenge/tests/test_functional.py`. A `vm` lab also needs `setup.yaml` and
`cleanup.yaml`, a non-empty `runtime.targets[]`, and a `runtime.default` that
matches one of those targets. A `shell` lab needs a non-empty `runtime.workdir`.

**Metadata.** `id`, `title`, `level` and `doc_url` non-empty, `skills` and
`distros` non-empty, `doc_url` in `http(s)`, `lab_type` within
`lab | challenge | capstone`, and `exam_passing_score` within 1..100 when
declared.

**Content.** Every relative link in the lab's Markdown resolves to a file that
exists; the announced total matches the score actually computed; a document
translated on one side only is reported; `runtime.targets[].host` and the
`roles` map to hosts declared in `meta.yml`; and no file of a `solution/`
directory is readable in clear text (a catalog without `solution/` is not at
fault, it made another choice).

`--check-urls` adds the only network control: each `doc_url` must answer.

**What it cannot check:** that a lab listed in `meta.yml` exists on disk. The
validator walks what discovery already loaded. Hence the order above.

---

## The traps

**1. `runtime.type` is `vm`, not `kvm` or `incus`.** Those two are tolerated
aliases and behave identically. The real backend comes from `meta.yml:
infra.provider`. Write `vm`.

**2. `runtime.host` does not exist.** No code reads it, so it is ignored in
silence. The FQDN belongs in `runtime.targets[].host`.

**3. Discovery goes by path, never by `id`.** A lab exists if and only if
`labs/**/lab.yaml` exists. `meta.yml` only **orders** labs and **names** the
blocks; the match compares the path relative to `labs/` against
`sections[].labs[]`. The `id` is only a CLI key.

**4. Zero bash is enforced.** The validator **rejects** `cleanup.sh`,
`runtime/kvm.sh`, `runtime/incus.sh`, `runtime/shell.sh` and `Makefile` inside a
lab directory. Preparation is declarative (`lab.yaml`) or Ansible
(`setup.yaml`).

**5. An undeclared fixture is not copied, and nothing says so.** The shell
runtime iterates over `runtime.fixtures`, **not** over the `fixtures/`
directory. A lab that ships files without listing them opens on an empty work
directory, and the learner has nothing to work with. Check it by hand:

```bash
dsoxlab run <id>
ls <lab>/challenge/work      # must list exactly what fixtures declares
```

The declared path is preserved: `modules/storage/main.tf` lands under
`<workdir>/modules/storage/main.tf`, intermediate directories included. An
absolute path, or one containing `..`, is refused with a warning.

**6. A key outside the contract is reported, not refused.** Since 0.1.54
`validate-structure` names any key the engine will never read, along with the
closest one it does read at the same level. The parser stays tolerant on
purpose — that is a v1 guarantee — so this is a lint, not a load failure.

---

## Tests that prove

A lab is graded by pytest with `pytest-testinfra`, and both ship inside dsoxlab:
a catalog installs no test tooling of its own.

Write assertions on the **state of the system**, never on the commands typed.
For a `vm` lab, the catalog's `conftest.py` builds the testinfra hosts from the
inventory dsoxlab generates:

```python
from dsoxlab.infra.inventory import build_inventory, read_terraform_outputs, write_ssh_config
```

That is the only import a catalog makes from dsoxlab, and it exists so no lab
ever hardcodes an IP address. The host to inspect is named by
`DSOXLAB_TARGET_HOST`, which `dsoxlab check --target <name>` sets: without
reading it, a multi-distro lab always tests its default host.

Three Ansible groups are injected at run time: `labenv` (every host of the
`meta.yml`, carrying the host vars), `lab_target` (the resolved target — this is
what a lab's playbooks must address) and one `lab_<role>` per entry of `roles`.

---

## Translations

| File | Overrides |
| --- | --- |
| `lab.fr.yaml` | `title` and `description` of that lab, and nothing else |
| `meta.fr.yml` | `repo.title`, `repo.description`, `sections[].title` and `sections[].description`, matched **by `id`** |
| `course.fr.yaml` | the section titles of the course |

The base files carry English, since English is the tool's default language.

`course.yaml` is what lets `dsoxlab course` show **one section at a time**, with
`--next`, `--prev` and `--section`, and remember where the learner stopped:

```yaml
sections:
  - id: navigation
    title: Moving around the tree
    file: course/01-navigation.md
```

Without it, `course` falls back to `scenario.md` + `README.md` shown in one
block — which is why long courses are long.

---

## Schemas, in your editor and in CI

Two JSON Schemas describe the same contract, and a test confronts them with the
parser in both directions so they cannot drift:
[`schemas/meta.schema.json`](../schemas/meta.schema.json) and
[`schemas/lab.schema.json`](../schemas/lab.schema.json).

```yaml
# yaml-language-server: $schema=https://raw.githubusercontent.com/stephrobert/dsoxlab/main/schemas/lab.schema.json
id: my-lab
title: My lab
```

Any editor running `yaml-language-server` then completes fields and underlines
mistakes as you type. In CI, validate without installing dsoxlab:

```bash
uvx check-jsonschema \
  --schemafile https://raw.githubusercontent.com/stephrobert/dsoxlab/main/schemas/lab.schema.json \
  $(find labs -name lab.yaml)
```

Pin a release tag instead of `main` in the URL to freeze the schema.

---

## Going further

- [The v1 contract, field by field](./contract-v1.md)
- [Where dsoxlab writes](./files.md)
- [Infrastructure, for the trainer](./trainer.md)
