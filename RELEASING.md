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

1. Bump the version in `pyproject.toml`, then refresh the lockfile with
   `uv lock`. There is **nothing to bump** in `src/dsoxlab/__init__.py`:
   `__version__` is read from the installed package metadata precisely so it
   cannot drift from `pyproject.toml`.
2. Move the `Unreleased` entries under a new `## [X.Y.Z]` heading in **both**
   [CHANGELOG.md](./CHANGELOG.md) and [CHANGELOG.fr.md](./CHANGELOG.fr.md), and
   update the comparison links at the bottom of each file. The project is
   bilingual: an English-only entry is an incomplete entry.
3. Commit through a pull request and merge to `main`.
4. **Wait for CI to be green on `main`.** The tag builds from that commit, and
   PyPI is final: a version number can never be republished.
5. **Run the local check** before tagging:

   ```bash
   python3 scripts/check-release.py
   ```

   It replays the steps above offline: clean tree, `main` up to date, tag
   consistent with `pyproject.toml`, CHANGELOG section present in both
   languages, `uv.lock` aligned, version still free on PyPI, CI green. It
   prints the exact command to run once everything passes. The workflow
   guard only speaks after the tag is pushed, and it then has to be deleted
   on both sides.

6. Tag the release and push the tag:

   ```bash
   git tag -a vX.Y.Z -m "vX.Y.Z"
   git push origin vX.Y.Z
   ```

Pushing the tag triggers `release.yml`, which:

- builds the sdist and wheel with `uv build` and checks them with `twine`,
- records **SLSA build provenance** for both artifacts
  (`actions/attest-build-provenance`),
- publishes to PyPI via OIDC, attaching PEP 740 build attestations,
- creates the **GitHub Release** with the CHANGELOG section for the tag, the
  distributions, and `provenance.intoto.jsonl`.

Two details of that pipeline are deliberate. The `publish` job runs no project
code and holds `id-token: write` only; and `github_release` runs after PyPI
succeeds, so no Release ever advertises a version that failed to upload.

`provenance.intoto.jsonl` is attached as a release asset on purpose: it is a
*distinct* artifact from the attestation recorded on GitHub's API, and it is the
one OpenSSF Scorecard's Signed-Releases control looks for. That control scores
the **five most recent** releases, so it only reaches its maximum once five
consecutive releases carry the asset.

## Verifying a release

Anyone can verify that a published artifact really came from this repository's
workflow, and from which commit:

```bash
gh release download vX.Y.Z --repo stephrobert/dsoxlab --pattern '*.whl'
gh attestation verify dsoxlab-X.Y.Z-py3-none-any.whl --repo stephrobert/dsoxlab
```

## Versioning

dsoxlab follows [Semantic Versioning](https://semver.org/). Breaking changes to
the declarative contract (`meta.yml` / `lab.yaml`) or the CLI bump the major
version once the project reaches 1.0.
