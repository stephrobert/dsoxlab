# Summary

<!-- What does this PR change and why? -->

## Type of change

- [ ] Bug fix
- [ ] New feature
- [ ] Refactor
- [ ] Documentation
- [ ] Chore / tooling

## Checklist

- [ ] `uv run ruff check src/dsoxlab` passes
- [ ] `uv run mypy src/dsoxlab` passes (strict)
- [ ] `uv run pytest` passes
- [ ] The engine stays domain-agnostic (no domain-specific logic in `src/dsoxlab/`)
- [ ] New/changed user-facing strings are added to **both** `i18n/strings/en.py` and `i18n/strings/fr.py`
- [ ] New/changed command or option is reflected in its `help=_()`, the i18n keys, and `fullhelp` (EN + FR)
- [ ] `CHANGELOG.md` updated when behavior changes
- [ ] Manually tested against at least one lab repository

## Related issues

<!-- e.g. Closes #123 -->
