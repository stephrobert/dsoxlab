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

### Every key, and what it means

The validator names each anomaly by a stable key. A test keeps this table in
step with the code: adding a check without documenting it here fails the suite.

| Key | What it means |
| --- | --- |
| `struct_missing_file` | a required file is absent |
| `struct_missing_dir` | `challenge/tests/` is absent |
| `struct_vm_targets_empty` | a `vm` lab declares no `runtime.targets` |
| `struct_default_unknown` | `runtime.default` names a target `targets[]` does not define |
| `struct_shell_workdir_empty` | a `shell` lab declares no `runtime.workdir` |
| `struct_session_unknown` | `runtime.session` is neither `target` nor `local` |
| `metadata_field_empty` | a required field is empty |
| `metadata_list_empty` | `skills` or `distros` is an empty list |
| `metadata_doc_url_scheme` | `doc_url` is not http(s) |
| `metadata_lab_type_invalid` | `lab_type` is outside the enumeration |
| `metadata_exam_score_invalid` | `exam_passing_score` is out of range |
| `content_broken_links` | a relative link points at nothing |
| `content_missing_english` | a document is translated on one side only |
| `content_scoring_points_mismatch` | the tasks total a different number of points than announced |
| `content_scoring_count_mismatch` | the header announces a different number of graded tasks |
| `content_scoring_tasks_vs_tests` | graded tasks and tests do not line up |
| `content_target_host_unknown` | a target's host is absent from `infra.hosts[]` |
| `content_role_host_unknown` | a `roles` entry names an unknown host |
| `content_solution_plaintext` | a file under `solution/` is readable in the clear |
| `content_fixture_missing` | a fixture is declared but absent from `fixtures/` |
| `content_fixture_undeclared` | a file sits in `fixtures/` without being declared |
| `content_fixture_escapes` | a fixture path is absolute or contains `..` |
| `content_doc_url_no_scheme` | `doc_url` carries no URL scheme |
| `content_doc_url_scheme` | `doc_url` uses a scheme other than http(s) |
| `schema_version_too_new` | the file declares a `schema_version` this dsoxlab cannot read |

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

**5. `fixtures/` and `runtime.fixtures` must say the same thing.** The shell
runtime iterates over `runtime.fixtures`, **not** over the `fixtures/`
directory — so the two can disagree, and both directions used to fail silently.
Since 0.1.84 neither does:

| Situation | What happens |
| --- | --- |
| declared, missing from disk | `run` **fails** (exit 2) and names every offender at once |
| present on disk, undeclared | `validate-structure` reports it (`content_fixture_undeclared`) |
| path escaping the workdir | reported, and refused at run time (`content_fixture_escapes`) |

Validation happens **before** any copy, so it is all or nothing: a half-filled
work directory looks like it works, and the learner then hunts for a mistake
that is not theirs. This defect made **7 labs unplayable on 2026-07-28**, all
marked done — it hid all the better because the tooling that checks the answer
keys copies the whole directory, so the solution went green while the learner's
path was broken.

Hidden files (`.gitkeep`) are exempt: they version an empty directory, and
flagging them would be a false positive every author learns to ignore.

The declared path is preserved: `modules/storage/main.tf` lands under
`<workdir>/modules/storage/main.tf`, intermediate directories included.

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
