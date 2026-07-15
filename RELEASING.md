# Releasing dsoxlab

**Language:** [English](./RELEASING.md) · [Français](./RELEASING.fr.md)

Releases are published to [PyPI](https://pypi.org/project/dsoxlab/) by the
`release.yml` workflow using **Trusted Publishing** (OIDC) — no API token is
ever stored in the repository.

## One-time setup

1. **PyPI trusted publisher.** On PyPI, add a *pending* trusted publisher for the
   `dsoxlab` project (Account → Publishing, or the project's *Publishing*
   settings):
   - Owner: `stephrobert`
   - Repository: `dsoxlab`
   - Workflow: `release.yml`
   - Environment: `pypi`

2. **GitHub environment.** Create an environment named `pypi` in the repository
   settings (Settings → Environments). Optionally add required reviewers and
   restrict it to tags matching `v*` so every publish is gated by an approval.

## Cutting a release

1. Bump the version in `pyproject.toml` and `src/dsoxlab/__init__.py`.
2. Move the `Unreleased` entries in [CHANGELOG.md](./CHANGELOG.md) under a new
   `## [X.Y.Z]` heading and update the comparison links.
3. Commit through a pull request and merge to `main`.
4. Tag the release and push the tag:

   ```bash
   git tag -a vX.Y.Z -m "vX.Y.Z"
   git push origin vX.Y.Z
   ```

Pushing the tag triggers `release.yml`, which:

- builds the sdist and wheel with `uv build` and checks them with `twine`,
- publishes to PyPI via OIDC, attaching PEP 740 build attestations.

## Versioning

dsoxlab follows [Semantic Versioning](https://semver.org/). Breaking changes to
the declarative contract (`meta.yml` / `lab.yaml`) or the CLI bump the major
version once the project reaches 1.0.
