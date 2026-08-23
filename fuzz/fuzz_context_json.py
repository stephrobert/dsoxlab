#!/usr/bin/env python3
"""Fuzz harness for the local session context.

`.dsoxlab-context.json` is untrusted for a different reason than `lab.yaml` and
`meta.yml`: it does not come from a lab-provider repository, it comes from the
learner's own disk. It is written by `dsoxlab use`, edited by hand when someone
is curious, truncated when a laptop is closed mid-write, and left behind by an
older version of the tool.

**This harness has no contract exception, and that is the point.**
`read_context` promises to return an empty context whenever the file is absent,
unreadable or malformed: losing the context costs the learner one `dsoxlab use`,
where an exception costs the whole CLI, without even naming the file to delete.
So any exception at all is a failure here, unlike the YAML harnesses where
`ValueError` is the documented rejection signal.

Run it — scratch dir FIRST, seed corpus second (see fuzz_lab_yaml.py):
    mkdir -p /tmp/fuzz-context
    uv run --group fuzz python fuzz/fuzz_context_json.py \
        /tmp/fuzz-context fuzz/corpus/context_json/ -atheris_runs=50000

See fuzz/fuzz_lab_yaml.py for why instrumentation is scoped to dsoxlab only and
why the seed corpus is what makes this harness effective.
"""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path

import atheris

with atheris.instrument_imports(include=["dsoxlab"]):
    from dsoxlab.config import read_context

_TMPDIR = Path(tempfile.mkdtemp(prefix="dsoxlab-fuzz-context-"))


def test_one_input(data: bytes) -> None:
    """Feed one fuzzer-generated document to read_context."""
    # Bytes are written raw, without decoding first: a context file of arbitrary
    # bytes is exactly the case that used to slip through, because
    # UnicodeDecodeError descends from ValueError and not from OSError.
    try:
        (_TMPDIR / ".dsoxlab-context.json").write_bytes(data)
    except OSError:
        return

    # No `except` for a contract: read_context must not raise, ever.
    read_context(_TMPDIR)


def main() -> None:
    atheris.Setup(sys.argv, test_one_input)
    atheris.Fuzz()


if __name__ == "__main__":
    main()
