# Architecture decisions

**Audience:** anyone about to change one of dsoxlab's durable choices, or
wondering why it was made that way. Contributors and reviewers first.

**Language:** [English](./README.md) · [Français](./README.fr.md)

An ADR (*architecture decision record*) writes down **one** decision: the
context that forced it, what was decided, what it costs, and what would make it
wrong. It is the answer to "why this choice?", kept where it can be found,
instead of in a long comment in the middle of the module that applies it.

[The design principles](../design-principles.md) say **what is true** and which
test holds it. These pages say **why it was chosen** over the alternatives. The
two point at each other.

---

## The format

Every record has the same short, fixed shape:

- **Status** and **Date** (the release that carried the decision);
- **Context**: what forced a choice, with the measurements of the time;
- **Decision**: what was chosen, and what was rejected;
- **Consequences**: what it costs and what it gives;
- **What would reverse it**: the conditions under which it should be reopened.

Two rules keep them useful:

- **Measurements keep their date.** A figure without its date is a memory, not
  a fact. Moving reasoning here never summarizes it.
- **The code keeps one line and a pointer** (`# See docs/decisions/0002-…md`).
  A comment that explains a single line stays where it is; only the
  architecture reasoning moves here. `tests/test_decisions.py` checks that every
  record has its sections and its French twin, and that every pointer to
  `docs/decisions/` in the repository leads to an existing file.

A decision that is reversed is not deleted: its status changes, and a new record
says what replaced it.

---

## The decisions

| # | Decision | Date |
| --- | --- | --- |
| [0001](./0001-two-runtimes.md) | Two runtimes, with the providers underneath | 2026-07-15 |
| [0002](./0002-per-catalog-flock-lock.md) | One write lock per catalogue, a `flock` whose file is never deleted | 2026-08-21 |
| [0003](./0003-explicit-ansible-core.md) | `ansible-core` is a declared dependency, despite its 100 MB | 2026-08-19 |
| [0004](./0004-mutable-upstream-images.md) | Upstream images are mutable, on purpose | 2026-08-24 |
| [0005](./0005-non-blocking-first-boot-packages.md) | First-boot packages do not block, but a bad finish is said | 2026-08-24 |
| [0006](./0006-log-in-english.md) | The log is written in English; the interface is translated | 2026-08-24 |
| [0007](./0007-json-output-contract-distinct-from-schema-version.md) | `--json` is a contract of its own, versioned apart from `schema_version` | 2026-08-20 |
| [0008](./0008-explicit-ruff-rule-set.md) | The Ruff rule set is declared in full, never inherited from the default | 2026-08-20 |
| [0009](./0009-missing-fixture-fails-run.md) | A fixture that cannot be copied fails `run`, all or nothing | 2026-08-24 |
| [0010](./0010-degraded-lab-when-engine-unreachable.md) | A lab whose container engine is unreachable is `degraded`, and says why | 2026-08-24 |
| [0011](./0011-three-outcomes-for-a-check.md) | A check has three outcomes, and `unknown` has its own exit code | 2026-08-24 |
| [0012](./0012-optional-hosts-stable-index.md) | Optional hosts get a stable index and leave through an `apply` without `-target` | 2026-11-14 |
| [0013](./0013-refuse-out-of-contract-hosts.md) | Refuse to touch a state that holds hosts this `meta.yml` does not declare | 2026-11-14 |
| [0014](./0014-catalog-table-measured-on-published-repos.md) | The catalogue table is measured on the published repositories, never typed | 2026-11-14 |

Numbers follow the order in which the records were written, not the order of the
decisions: the first eight were already written somewhere in the code when this
directory was created (issue #203).

## Adding one

Copy an existing record, take the next number, write both languages, add a line
to this table and to its French twin, and replace the long comment in the code
by one line and a pointer.
