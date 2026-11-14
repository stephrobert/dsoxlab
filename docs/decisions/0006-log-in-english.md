# ADR-0006: The log is written in English; the interface is translated

**Status:** accepted
**Date:** 2026-08-24 (0.1.84, issue #140; developed as 0.1.83)

**Language:** [English](./0006-log-in-english.md) · [Français](./0006-log-in-english.fr.md)

## Context

Every string displayed to the user goes through `_()`, in English and French.
The log (`~/.local/state/dsoxlab/dsoxlab.log`) is something else: it is the file
`dsoxlab support` collects and that a user pastes into a bug report.

The log mixed French and English. That is not a matter of aesthetics. Measured
before being fixed: **41 French messages against 4 English ones**.

`logger.*` calls are **deliberately excluded** from the i18n guard
(`tests/test_i18n_coverage.py`), and that exclusion still holds: a log message
is not interface text, it does not go through `_()`, and translating it at run
time would make two reports incomparable depending on the locale of whoever
produced them. But the exclusion justified not **translating** the log, not
leaving it inconsistent.

## Decision

The log speaks one language, and it is **English**. The interface stays
translated.

English wins for three reasons, in order of weight:

1. a log message is searched **word for word** in a search engine;
2. it is compared between two machines with different locales;
3. it is read by someone who **diagnoses**, not by someone who learns, and it
   already sits next to the output of terraform, ansible and virsh, which is
   English.

The rejected alternatives: translating the log at run time (two incomparable
reports), or leaving each message in the language its author happened to write
(the state that was measured).

## Consequences

- `tests/test_journal_en_anglais.py` holds the rule. Without it, the rule would
  come undone line by line, which is exactly what happened to the interface
  before its own guard existed.
- The detector uses a short list of words that exist only in French, so that it
  produces **zero** false positives, at the price of missing some French. It is
  a guard, not a proofreader.
- The rule is written where a contributor meets it: the PR template, and
  [the design principles](../design-principles.md).
- The same reasoning later put the published evidence document in English
  (`docs/machine-output.md`): what is published does not follow the locale of
  whoever produced it.

## What would reverse it

A log that stops being a diagnostic artefact shared outside the machine (for
instance if `support` no longer collected it). As long as it is pasted into
issues and compared across machines, one language beats two.
