# ADR-0010: A lab whose container engine is unreachable is `degraded`, and says why

**Status:** accepted; corrects half of the original decision
**Date:** 2026-08-24 (0.1.84, issue #179; developed as 0.1.78)

**Language:** [English](./0010-degraded-lab-when-engine-unreachable.md) · [Français](./0010-degraded-lab-when-engine-unreachable.fr.md)

## Context

`dsoxlab status` computes the state of a lab in one place
(`services/lab_state.py`, 0.1.68): `not_started`, `ready`, `in_progress`,
`validated`, and `degraded` when a declared service no longer runs. `degraded`
wins over everything, because it is the only state calling for an immediate
gesture. A service that was never started is **not** degraded: that is the
normal case before the first `run`, and confusing the two would turn every
service lab red.

The original decision had two halves. A lab that declares no service ignores
Docker entirely. And when `docker_available()` was false, `_services_degrades`
returned an empty list, meaning "nothing to report". The second half made "Docker
**was** there and its daemon went down" indistinguishable from "Docker was never
installed". In the first case the lab really is unplayable (`run` already fails
on it explicitly, with exit code 2), yet `status` announced `ready`, or even
`validated` when a score existed from an earlier session.

## Decision

- A lab that **declares** services and whose engine does not answer is
  `degraded`, **whatever the score already obtained**. The engine is asked
  before the score is read, so that `status` never announces "validated" on a
  lab that can no longer be played.
- The two causes are told apart (`MOTEUR_ABSENT`: docker is not installed;
  `MOTEUR_MUET`: the client is there, the daemon does not answer), because they
  call for opposite gestures: install a package, versus start a daemon and check
  the account may talk to it.
- A lab that declares **no** service still ignores the engine entirely, without
  even paying for a probe. That was the sound half of the original decision; it
  is kept and tested on its own. A catalogue without services must not pay for
  a call, nor turn red because Docker is missing from a machine that does not
  need it.

## Consequences

- `status` and `status --json` carry `degraded` with a translated detail that
  names the cause.
- The order of the questions in `calculer` is the order of what prevails: a
  degradation first, the score next, then the work, then the mere preparation.
- `tests/test_moteur_injoignable.py` and `tests/test_lab_state.py` hold both
  halves.

## What would reverse it

A container engine other than Docker, or several engines. The rule (an engine
that does not answer makes a service lab `degraded`, and the cause is named)
would stay; only the probe would change.
