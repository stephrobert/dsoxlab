# ADR-0014: The catalogue table is measured on the published repositories, never typed

**Status:** accepted
**Date:** 2026-11-14 (0.9.2)

**Language:** [English](./0014-catalog-table-measured-on-published-repos.md) · [Français](./0014-catalog-table-measured-on-published-repos.fr.md)

## Context

`src/dsoxlab/templates/catalogues.yml` is what `dsoxlab catalog list` shows a
learner, and the README table was built from it. It went stale three times: on
2026-10-10 it announced three catalogues when six existed, on 2026-10-17 six when
twelve existed, and on 2026-11-14 the README announced 414 labs across 12
catalogues, 64 of them for Kubernetes, when the published repositories carried
699 labs across 18 catalogues, 111 for Kubernetes. Seven public catalogues were
missing from the manifest, so `catalog list` never offered them (publier-service,
proxmox, gitlab-ci, bdd, certificats, artefacts and mlops).

The cause was the same each time: a figure written by hand, and a check that
looked only at the local disk, and only when the manifest itself changed.

## Decision

- The manifest carries **no figure** any more: only the identity of a catalogue
  (id, repository, descriptions).
- `scripts/gen-catalogues.py` counts `labs/**/lab.yaml` on the default branch of
  each **published** repository, the one a learner clones, through the GitHub
  API, and rewrites the table of both READMEs.
- It refuses a private or archived repository listed in the manifest, and names
  any public repository of the same owners that carries labs without being
  listed.
- A check that could not look never concludes green: without network, or on a
  truncated git tree, it exits **2** instead of concluding.
- The pre-push hook runs it on **every** push, not only when the manifest
  changes, since it is the catalogues that move; CI runs the same hook with the
  job token, which only lifts the anonymous rate limit of 60 requests per hour.

The rejected alternative was to keep the figures in the manifest and compare
them with the local disk: that is the check that let the table drift three
times, because the local disk is not what a learner clones.

## Consequences

- A push needs network access to GitHub; offline, the hook exits 2 rather than
  approving.
- A catalogue that publishes no lab yet (certificats, measured on 2026-11-14)
  stays in the manifest and out of the table.
- The token is only used to read **public** repositories: a private repository
  is never offered, even if the token can see it.

## What would reverse it

Catalogues no longer published on GitHub, or a manifest that stops being what
`catalog list` reads. The measurement would then move to wherever learners
clone from; the rule (no hand-written figure) stays.
