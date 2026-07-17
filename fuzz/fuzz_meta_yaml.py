#!/usr/bin/env python3
"""Fuzz harness for the meta.yml parser.

`meta.yml` is the second untrusted document a lab-provider repository hands to
`dsoxlab`: it drives the catalogue topology (sections, ordering) and — for
`runtime: vm` labs — the infrastructure description (hosts, network, provider)
that feeds Terraform.

`RepoMetadata.from_yaml` documents `ValueError` as its rejection signal for a
malformed contract (missing `repo.id` / `repo.category`), and the CLI composes a
readable error from it. Provider ambiguity deliberately does NOT raise here: it
is deferred to `infra.require_provider()`. Anything raised outside the contract
below reaches the user as a traceback.

Run it — scratch dir FIRST, seed corpus second (see fuzz_lab_yaml.py):
    mkdir -p /tmp/fuzz-meta
    uv run --group fuzz python fuzz/fuzz_meta_yaml.py \
        /tmp/fuzz-meta fuzz/corpus/meta_yml/ -atheris_runs=50000

See fuzz/fuzz_lab_yaml.py for why instrumentation is scoped to dsoxlab only and
why the seed corpus is what makes this harness effective.
"""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path

import atheris
import yaml

with atheris.instrument_imports(include=["dsoxlab"]):
    from dsoxlab.models.repo import RepoMetadata

CONTRACT_EXCEPTIONS = (KeyError, ValueError, yaml.YAMLError)

_TMPDIR = Path(tempfile.mkdtemp(prefix="dsoxlab-fuzz-meta-"))
_META_YML = _TMPDIR / "meta.yml"


def test_one_input(data: bytes) -> None:
    """Feed one fuzzer-generated document to RepoMetadata.from_yaml."""
    # Raw decode, not FuzzedDataProvider — see fuzz_lab_yaml.py: the provider
    # would reinterpret the seed files and make the corpus inert.
    try:
        document = data.decode("utf-8")
    except UnicodeDecodeError:
        return

    try:
        _META_YML.write_text(document, encoding="utf-8")
    except (UnicodeEncodeError, OSError):
        return

    try:
        RepoMetadata.from_yaml(_META_YML)
    except CONTRACT_EXCEPTIONS:
        return
    except RecursionError:
        raise


def main() -> None:
    atheris.Setup(sys.argv, test_one_input)
    atheris.Fuzz()


if __name__ == "__main__":
    main()
