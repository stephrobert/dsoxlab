# ADR-0011: A check has three outcomes, and `unknown` has its own exit code

**Status:** accepted
**Date:** 2026-08-24 (0.1.84, issues #172 and #176; `unknown` developed as 0.1.73, `--strict` as 0.1.79)

**Language:** [English](./0011-three-outcomes-for-a-check.md) · [Français](./0011-three-outcomes-for-a-check.fr.md)

## Context

`doctor` checks had two outcomes, `ok` and `failed`. A probe that could not
measure had to be one or the other. Issue #172: the libvirt pool check called
`virsh -c qemu:///system` directly, without the `sudo -n` prefix detection that
`infra/libvirt.py` built for that case. On any machine where the system URI
requires privileges, the probe failed every time, and that failure was
rendered `ok`: a check permanently green exactly where `provision` was going to
die on "Pool Not Found". The whole #172 to #179 batch had this one shape: a
check that, unable to measure, concluded that all was well.

There are two symmetric lies. The first is red displayed in front of a command
that works; the second, more insidious, is green displayed for want of having
measured.

Separately, `doctor` exited 0 whatever the state of its checks. That is the
right call for a human (a diagnosis is not a failure), but it made the command
unusable as an automated gate: a script had to parse the JSON to learn whether
anything was missing (issue #176).

## Decision

**Three outcomes: `ok`, `failed`, `unknown`.** An unreadable `/proc/meminfo` or
a silent libvirt pool is neither the reassuring green of an unearned "ok" nor
the accusing red of an unproven failure. A check in `unknown` does not enter
`DoctorReport.failing` (it proves no failure), and it never paints the top-level
verdict red. But its token tells a program and a human alike that nothing is
proven the other way either. It is exposed by `doctor --json` and rendered as
"? not measured".

**`doctor --strict` turns the diagnosis into an exit code, with two codes rather
than one**, because the two situations call for different gestures:

| Mode | Code | When |
| --- | --- | --- |
| `doctor` | `0` | always, unchanged |
| `doctor --strict` | `9` | a required check failed |
| `doctor --strict` | `10` | a required check could not be measured |

`9` gets repaired, `10` gets measured again. An environment whose probe did not
complete is not validated for all that, which is exactly what an image build
must not mistake for a success. `9` wins when both coexist: a certainty
outweighs an ignorance.

The rejected alternatives: folding `unknown` into `failed` (red for what we do
not know), folding it into `ok` (the #172 defect), or one non-zero code for
both (a script could not tell "repair" from "measure again").

## Consequences

- The default does not move, and `--strict` changes nothing else: the table and
  the document are still rendered **before** the code lands, so a caller
  receiving a non-zero code can still read what went wrong.
- Every new check must be able to return `unknown` when its probe does not
  complete. "A check that could not look never concludes green" is the first
  rule of [the design principles](../design-principles.md).
- Codes 9 and 10 belong to the exit-code contract: they do not change meaning.
- `tests/test_doctor_strict.py` holds the codes.

## What would reverse it

Nothing in sight. The state token `choice_required` already exists next to the
three outcomes, for a check that waits for a choice of the user (rendered
"to be chosen"): it does not reopen the question, since it concludes neither green
nor red either. Folding `unknown` back into `ok` or `failed` would reintroduce
the defect this decision exists to prevent.
