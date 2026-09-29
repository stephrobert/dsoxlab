# Design principles

**Audience:** anyone adding a check, a command or an exit path to dsoxlab —
human or agent. It is also what lets a review say *no* in one sentence: "this
check returns `ok` when its probe fails" is a complete reason.

**Language:** [English](./design-principles.md) · [Français](./design-principles.fr.md)

Every rule below was already being applied without being written down, and every
one of them was discovered **the day it was violated**. That is why each comes
with its incident: a principle without its bug gets argued about, a principle
with its bug gets respected.

The third column is the part worth reading twice. It names the test that holds
the rule — and where it says *not guarded yet*, that is an honest gap, not an
oversight to hide.

---

## Measuring

**Un contrôle qui n'a pas pu regarder ne conclut jamais au vert.**

| Invariant | What revealed it | Held by |
| --- | --- | --- |
| A probe that could not look does not conclude green. A check has **three** outcomes — `ok`, `failed`, `unknown` — and `unknown` gets its own exit code (`10`) because a script can conclude nothing from a measurement that never happened | issue #172: an unreadable libvirt pool was reported as fine. The whole #172→#179 batch had this single shape | `tests/test_doctor_strict.py`, `tests/test_note_sans_mesure.py` |
| Zero tests executed is not a score of zero. A `conftest.py` that raises on import, an unreachable machine, a missing dependency — all yield `total == 0`, which is an absence of measurement, not a failure | issue #168: the 0 was being written to the database as a grade | `tests/test_note_sans_mesure.py` |
| **An address is not a machine.** A host present in the Terraform state is not a host that answers | `dsoxlab start` announced "already provisioned, nothing to rebuild" right after a `provision` that had exited 8 on "the infrastructure exists but is not usable as it stands". It decided on the state alone. Fixed in 0.2.2: it probes port 22 | `tests/test_start_sequence.py` |
| **Provisioned is not usable.** Terraform returning 0 says the resources exist, not that the lab can run | issues #170, #178 — hence exit code `8`, and `dsoxlab status` naming which host stays silent | `tests/test_host_ready_timeout.py`, `tests/test_codes_de_sortie.py` |
| **A command executed is not a state reached.** We never check that a command was typed; we check the state of the system | the labs' state machine, and `pytest-testinfra` as the validation tool | the catalogues' own test suites |
| **Checking is not parsing.** `ast.parse` accepts a Python module whose variable a bad substitution deleted: the file is valid and raises `NameError` on first call. Same gap between `terraform validate` and `terraform apply` | written in the project's working rules before it had a name | `tests/test_contrat_honore.py` (behaviour, not shape) |
| **A workflow that has never run is a workflow that does not work**, whatever static analysis approves of it | `actionlint`, `zizmor` and `poutine` all passed on the appliance workflow. It took three releases to make it succeed: `/mnt` is owned by root, Packer refuses a pre-existing output directory, `/dev/kvm` is not openable by the `runner` account | *not guarded yet* — only a real run guards this one, which is what issue #243 is about |
| **A check that does not use the recipient's reader checks nothing** | issue #279: the appliance's OVA was verified with `tar`, `xmllint` and `sha256sum` — three tools that read a *file* — and imported under VirtualBox, which does not verify the manifest. VMware reads a *stream*, stops at its end marker, and hashed 64 512 fewer bytes than our manifest declared. The disk was intact; only the two readings disagreed | `tests/test_ova_flux_vmdk.py`, and the build now refuses to ship an image whose file digest is not also its stream digest |

---

## Saying it

**Un échec qui ne se dit pas est pire qu'un échec.**

| Invariant | What revealed it | Held by |
| --- | --- | --- |
| A failure that does not say so is worse than a failure. Every failure path gets a code **and** a message | issues #170, #173, #179: `destroy` exited successfully leaving machines up, `doctor` printed "ok" over an unusable terraform, a failed snapshot was swallowed into a `logger.warning` | `tests/test_codes_de_sortie.py`, `docs/exit-codes.md` |
| **A marker of work done is only written when the work succeeded.** Otherwise it condemns the machine in silence | the appliance's first boot marked itself done even when the network was absent and nothing had been installed — with no way left to recover | `packer/scripts/30-premier-demarrage.sh` accumulates failures and exits 1 without the marker; *not guarded by a test* |
| **Human output is not the machine interface.** `--json` carries a stable `key` and a `state` token, and only then a translated label. Copying displayed text into a field makes an integration unusable while looking complete | the `--json` work: nobody can tell green from red without parsing French or English | `tests/test_json_output.py`, `tests/test_json_schemas.py` |
| **The log is written in English**, and it is not interface text | the log mixed French and English; it is the file `dsoxlab support` collects, searched word for word and compared between machines with different locales | `tests/test_journal_en_anglais.py` |
| **Every displayed string goes through `_()`**, in both languages at once | the debt settled in 0.1.34 ran both ways: French messages showed under `DSOXLAB_LANG=en`, and every progress-bar label stayed English under `DSOXLAB_LANG=fr` | `tests/test_i18n_coverage.py`, `tests/test_cles_i18n_existantes.py` |

---

## The contract

| Invariant | What revealed it | Held by |
| --- | --- | --- |
| **A declared fixture that is missing is not a partial workdir.** All or nothing: validation precedes any copy, and names every offender at once | issue #177 — a half-filled `challenge/work` looks like it works, and the learner then hunts for the error in their own work. Seven labs of `terraform-training` were unplayable on 2026-07-28, all marked done | `tests/test_fixtures_declarees.py`, `tests/test_shell_fixtures.py` |
| **A catalogue is untrusted input. A value from the contract is data, never an instruction.** The whole model is written once, in [the security model](./security.md) | a `doc_url` in `javascript:` reached `webbrowser.open()`; a `title` carrying unbalanced Rich markup made `list-labs` and `show` exit with a traceback | `tests/test_securite_urls.py`, `tests/test_securite_terminal.py`, `tests/test_securite_identifiants.py` |
| **The parser is permissive, the validator is strict.** A `lab.yaml` keeps loading; `validate-structure` is the lint that tells the author. A lint is not a security barrier — it is neither automatic nor required before using a catalogue | v1 guarantees a lab does not vanish because a field is new; and the security checks are replayed at the point of use for exactly that reason | `tests/test_yaml_contract.py`, `tests/test_validator_voit_tout.py` |
| **Documentation that drifts is worse than absent**: it makes people write falsehoods with confidence | the command table described a `cleanup.sh` the contract forbids; the persistence section pointed at a database that never existed (issue #86) | `tests/test_documentation_synchrone.py`, `tests/test_doc_auteur_couvre_les_controles.py` |

---

## What the project promises

These are commitments to whoever integrates dsoxlab. They were settled in
practice long before being written here, which is the point of writing them.

### The input contract (`meta.yml` / `lab.yaml`), version 1

- **Adding an optional field is always allowed**, and requires nothing of
  existing catalogues.
- **Removing a field, or changing what one means, is not.** That would require
  `schema_version: 2`, and an engine that reads a version it does not know says
  so and names the file — it does not make the lab disappear.
- **The parser stays tolerant** on values: a malformed field raises inside the
  parser contract (`KeyError`, `ValueError`, `yaml.YAMLError`), so a bad lab is
  skipped with a warning instead of crashing the CLI.
- **`runtime.type` aliases `kvm` and `incus` are kept** for backward
  compatibility, and treated exactly like `vm`. No removal is planned; a new lab
  writes `vm`.

### The machine output

- `reporting/machine.py` carries `SCHEMA = 1`, which evolves **independently of
  the package version**. Adding a field keeps compatibility; a field that
  changes meaning or disappears increments it.
- The evidence document is named differently on purpose:
  `"schema": "dsoxlab-evidence-v1"`, a **string**, because that document leaves
  dsoxlab and `{"schema": 1}` does not say what it is the schema 1 *of*.
- Its fields are built from a **positive allowlist**. See
  [the machine output](./machine-output.md) for what may never appear in it.

### Exit codes

The codes listed in [exit codes](./exit-codes.md) **do not change meaning**. A
code has no schema, no version and no message: a script reading `7` today must
read `7` tomorrow. New failure paths get new codes.

---

## Adding to this document

Two rules, and the second is the one that keeps it honest.

**One invariant, one incident.** If you cannot name what went wrong, it is a
preference, and preferences belong in a review comment rather than here.

**Name the test, or say there is none.** The third column is what turns a list of
good intentions into a map of what is actually guarded — and what is not. A rule
with no test is a rule waiting for its regression.
