# ADR-0009: A fixture that cannot be copied fails `run`, all or nothing

**Status:** accepted; reverses an earlier decision
**Date:** 2026-08-24 (0.1.84, issue #177; developed as 0.1.76)

**Language:** [English](./0009-missing-fixture-fails-run.md) · [Français](./0009-missing-fixture-fails-run.fr.md)

## Context

`ShellRuntime` iterates over `runtime.fixtures`, **not** over the contents of
the `fixtures/` directory. The two can therefore disagree, and both possible
gaps caused the same damage without a word:

- a fixture *declared but missing from disk* went to a `logger.warning`;
- a fixture *present but undeclared* was never read.

In both cases `dsoxlab run` created an empty `challenge/work`, exited **0**, and
the learner had nothing to do. This is the defect that made **7 labs of
`terraform-training` unplayable on 2026-07-28**, all marked done. It hid all the
better because the tooling that checks the solutions (`scripts/verify-solutions.py`
and the trainer-mode `conftest.py` of the catalogues) copies the whole
directory: the answer key went green while the learner's path was broken.

The behaviour came from an earlier decision: a typo in one entry should not
deprive the learner of the whole workdir.

## Decision

The earlier decision is **reversed**. A fixture that cannot be copied fails
`run`, which exits with code **2** (`FixtureError`).

It is the missing file that deprives the learner, not the refusal: an authoring
mistake is not something they can fix, and an amputated exercise fails `check`
for reasons they will look for in their own work.

Validation happens **before any copy**: it is all or nothing, because a
half-filled workdir looks like it works. Every offending fixture is named at
once, so an author fixes them in one pass rather than one `run` per fixture. A
path that is absolute or contains `..` is refused the same way: a fixture never
leaves the workdir.

## Consequences

- `validate-structure` compares `fixtures/` against the declaration in both
  directions (declared but missing, present but undeclared, path escaping the
  workdir), in the default offline set, so a catalogue's CI catches the mistake
  before a learner does.
- Hidden files (`.gitkeep`) are exempt: flagging them would be a false positive
  every author would learn to ignore, and a check people learn to ignore checks
  nothing.
- The 7 labs of `terraform-training` have been repaired since, and the three
  catalogues measured were clean on 2026-08-24.
- `tests/test_fixtures_declarees.py` and `tests/test_shell_fixtures.py` hold
  the rule.

## What would reverse it

A fixture that is genuinely optional, which the v1 contract has no way to say.
That would call for a new optional field marking it as such, not for a return to
skipping silently.
