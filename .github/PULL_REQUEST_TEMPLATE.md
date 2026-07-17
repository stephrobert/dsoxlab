# Summary

<!-- What does this PR change, and why? -->

## Type of change

- [ ] Bug fix
- [ ] New feature
- [ ] Refactor
- [ ] Documentation
- [ ] Chore / tooling
- [ ] Security / supply chain

## Checklist

Only the **Always** block applies to every PR. The other blocks are conditional:
if a block does not apply, say so (`N/A`) rather than leaving it blank — a blank
box reads as "forgotten", an explicit `N/A` reads as "considered".

### Always

- [ ] `uv run ruff check src/dsoxlab tests fuzz` passes (lint + flake8-bandit)
- [ ] `uv run mypy src/dsoxlab` passes (strict)
- [ ] `uv run pytest` passes
- [ ] The engine stays domain-agnostic — no domain-specific logic in
      `src/dsoxlab/` (no `if category == "linux"`)
- [ ] No hardcoded personal path or host; `pathlib.Path` throughout
- [ ] Manually tested against **two** lab repositories, to prove the agnostic
      design (e.g. `linux-dsoxlab-training` and `ansible-training`)

### When behavior changes — otherwise N/A

- [ ] **Both** `CHANGELOG.md` and `CHANGELOG.fr.md` updated (the project is
      bilingual; an EN-only entry is an incomplete entry)
- [ ] Version bumped in `pyproject.toml` and `uv.lock` refreshed (`uv lock`).
      `__version__` is derived from the package metadata — there is nothing to
      bump in `src/dsoxlab/__init__.py`.

### When a command or option is added, removed or changed — otherwise N/A

- [ ] Keys added to **both** `i18n/strings/en.py` and `i18n/strings/fr.py`
- [ ] `help=_("…")` in `cli.py` and the `fullhelp_commands` section updated in
      EN **and** FR — `fullhelp` must never describe a command that no longer
      exists
- [ ] Checked with `DSOXLAB_LANG=en` and `DSOXLAB_LANG=fr`

### When `.github/workflows/` is touched — otherwise N/A

These are CI gates: they fail the build, so run them before pushing.

- [ ] `actionlint` clean
- [ ] `zizmor --offline .github/workflows/` reports no findings
- [ ] `poutine analyze_local . --fail-on-violation` clean
- [ ] Every action pinned to a **full 40-character commit SHA** with a
      `# vX.Y.Z` comment — never `@v4`, never `@main`
- [ ] `step-security/harden-runner` is the job's first step
- [ ] No job renamed, or the required status checks updated accordingly — they
      match job names **exactly**, and a renamed job silently stops being
      required
- [ ] A new third-party action is added to `trustedGithubActions` in
      `.plumber.yaml` (and acknowledged per purl in `.poutine.yml` if its
      creator is not Marketplace-verified)

### When the declarative contract (`meta.yml` / `lab.yaml`) changes — otherwise N/A

- [ ] The contract section of `README.md` reflects the change
- [ ] `fuzz/corpus/` seeds and `fuzz/dict/yaml_contract.dict` cover any new field
- [ ] A malformed value of the new field still raises inside the parser contract
      — `(KeyError, ValueError, yaml.YAMLError)` — so a bad lab is skipped with a
      warning instead of crashing the CLI

## Related issues

<!-- e.g. Closes #123 -->
