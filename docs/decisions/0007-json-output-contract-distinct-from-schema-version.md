# ADR-0007: `--json` is a contract of its own, versioned apart from `schema_version`

**Status:** accepted
**Date:** 2026-08-20 (0.1.46, when `schema_version` arrived next to the existing `SCHEMA`)

**Language:** [English](./0007-json-output-contract-distinct-from-schema-version.md) · [Français](./0007-json-output-contract-distinct-from-schema-version.fr.md)

## Context

Any integration (an editor extension, a web dashboard, a tracking script) needs
to read the state of the catalogue and of the progression. Without a machine
output it would have to parse the Rich output: tables whose width depends on
the terminal, colours, line breaks. The slightest display adjustment would
break the integration, and the display is made to move.

dsoxlab therefore exposes two public interfaces, in opposite directions:

- `meta.yml` and `lab.yaml`, what dsoxlab **reads** from a catalogue. Without a
  version number, a field changing meaning could be neither announced, nor
  detected, nor refused: it showed up as a lab disappearing from the catalogue,
  without a word. That is the most expensive symptom to diagnose in the whole
  project.
- the `--json` documents, what dsoxlab **writes** for other programs.

## Decision

**`--json` is a contract**, held by three rules (`reporting/machine.py`):

1. **Nothing but JSON on standard output.** In machine mode the ambient messages
   (active context, tips, update notice) go to standard error: an "ℹ" at the
   head of the stream would make the document unreadable for the caller.
2. **The format is versioned.** Every document carries a `schema`, so that a
   consumer knows whether it speaks the same language before reading the rest.
3. **A verdict is read without translating.** A check carries a stable **key**
   and a **state** token (`ok`, `failed`…), and only *then* a translated label.
   Copying the displayed text into a field would make the interface unusable
   while looking complete: nobody can tell green from red without parsing French
   or English.

Machine mode **never** changes the verdict nor the exit code of a command: it
changes its shape.

**`reporting/machine.py: SCHEMA` and `schema_version` are two contracts.**
`SCHEMA` versions what dsoxlab writes; `schema_version` versions what it reads.
Two contracts, two audiences, two rhythms of evolution: they must never be
coupled, nor bumped together out of reflex. `SCHEMA` also evolves independently
of the package version.

The rejected alternative was a single version number for "the dsoxlab format".
A catalogue author and a dashboard author would then be told of changes that do
not concern them, and a bump made for one would look like a break to the other.

## Consequences

- Adding a field keeps `schema` where it is. Changing what a field means,
  renaming it, removing it, or changing the meaning of a `state` or `kind`
  token increments it.
- Translated text (`label`, `message`, `detail`, `notes`) and the raw output of
  another tool (`check.output`) are explicitly **not** part of the contract.
- The evidence document is named differently on purpose:
  `"schema": "dsoxlab-evidence-v1"`, a string, because that document leaves
  dsoxlab, and `{"schema": 1}` does not say what it is the schema 1 *of*.
- For the input side, the default of an absent `schema_version` does **not**
  follow `SUPPORTED_SCHEMA_VERSION`: the day v2 exists, a silent file stays a v1
  file, written before the version existed.
- [The machine output](../machine-output.md) and [the v1 contract](../contract-v1.md)
  publish both rules; `tests/test_json_output.py` and
  `tests/test_schema_version.py` hold them.

## What would reverse it

Nothing foreseeable merges the two: their readers are different people. What
could change is the *shape* of the output contract (a different transport than
standard output, for instance), which would get a new `schema` value, not a
shared number.
