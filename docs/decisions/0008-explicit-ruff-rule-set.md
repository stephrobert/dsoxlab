# ADR-0008: The Ruff rule set is declared in full, never inherited from the default

**Status:** accepted
**Date:** 2026-08-20 (0.1.49)

**Language:** [English](./0008-explicit-ruff-rule-set.md) · [Français](./0008-explicit-ruff-rule-set.fr.md)

## Context

The `[tool.ruff.lint]` section of `pyproject.toml` said "E/F are active by
default" and settled for an `extend-select` adding `S`. Ruff 0.16 widened its
default set: the same command, on the same code, went from **0 to 123 errors**,
none of which belonged to `E`, `F` or `S`. Nobody had decided that change of
scope; it arrived with a version bump. A configuration that relies on a
linter's default gets moved by it.

## Decision

`select` **replaces** the default instead of extending it. `pyproject.toml` is
the only authority on what this project applies, and a future Ruff version can
no longer answer in its place. Each selected family carries, on its own line, a
comment saying what it catches.

Families **deliberately left out**, each measured on this code on 2026-08-20
(counts in parentheses):

- **TRY (86).** TRY003 (69) refuses error messages written in place, when this
  declarative contract draws its value from sentences that name the faulty file
  and field. TRY004 (13) would demand a `TypeError` where the contract
  coercions raise `ValueError`; yet `discovery/scanner.py` and the fuzz harness
  catch exactly `(KeyError, ValueError, YAMLError)`. Obeying would make the CLI
  crash on an ill-typed `lab.yaml` instead of setting it aside.
- **PLR (71).** Arbitrary thresholds (number of arguments, of branches).
- **PLC (88).** Import and comparison style, with no class of defect behind it.
- **N (11).** N818 would rename eleven public exceptions (`HostReadyTimeout`…)
  that lab repositories import: an API break for a naming convention.
- **INP (2).** Targets the tests of the packaged demonstration lab, which are
  pedagogical CONTENT, not a Python package.
- **PERF (5).** Micro-optimisation of a CLI; the loops it targets carry comments
  that a comprehension would swallow.
- **ANN, D, ARG, EM, FBT, TID, TC, SLF, T20, ERA, COM.** Either redundant with
  mypy strict, or purely stylistic.

## Consequences

- A Ruff upgrade can add rules only when someone adds them to `select`.
- Every family left out has its measurement written down, so reopening the
  question starts from numbers rather than from taste.
- The rules ignored inside selected families (`S603`, `S607`, `S101`, `E501`,
  `RUF001` to `RUF003`) stay commented line by line in `pyproject.toml`, since
  each comment explains one line.
- In the same release, the 19 `subprocess.run` calls that omitted `check=` were
  reviewed one by one; all 19 were deliberate and now say `check=False` with a
  comment. One of them read its exit code nowhere: that was the `doctor`
  Terraform bug fixed in 0.1.49. `PLW1510` now holds that rule.

## What would reverse it

Nothing makes the default safe again: the reason is that it moves. What changes
over time is the *content* of `select` and of the left-out list. A family moves
in when its measured findings on this code are real defects; the counts above
go stale, and should be re-measured before being cited again.
