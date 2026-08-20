#!/usr/bin/env python3
"""Fuzz harness for the lab.yaml parser.

Why this file exists
--------------------
`dsoxlab` reads `lab.yaml` files that come from *lab-provider repositories*, not
from this codebase. That YAML is the engine's main untrusted input: a third
party writes it, and `dsoxlab list-labs` parses every one of them.

`discovery/scanner.py` states the parser's contract explicitly:

    except (KeyError, ValueError, yaml.YAMLError) as exc:
        logger.warning("lab.yaml ignoré (%s) : %s", yaml_path, exc)

A malformed lab is meant to be *skipped*, never to take the CLI down. So any
exception outside that tuple is a real defect: it escapes the scanner's handler
and surfaces to the user as a traceback on an unrelated command.

That is exactly what this harness looks for — it asserts the contract, it does
not merely execute the parser.

Run it — scratch dir FIRST, seed corpus second:
    mkdir -p /tmp/fuzz-lab
    uv run --group fuzz python fuzz/fuzz_lab_yaml.py \
        /tmp/fuzz-lab fuzz/corpus/lab_yaml/ -atheris_runs=50000

libFuzzer writes every input it finds interesting into the *first* corpus
directory given. Passing the scratch dir first keeps `fuzz/corpus/` a
hand-curated set of seeds instead of filling it with thousands of mutations.

Two details that decide whether this harness finds anything at all:

* Instrumentation is scoped to `include=["dsoxlab"]`. Instrumenting everything
  would also instrument PyYAML's compiled C loader (`_yaml`) and segfault the
  harness; instrumenting nothing makes the fuzzer blind, and libFuzzer then
  reports "no interesting inputs were found".
* The seed corpus matters more than the run count here. Random bytes are almost
  never valid YAML, so without seeds the fuzzer never reaches the field logic
  past `safe_load`. The corpus holds real lab.yaml documents to mutate.
"""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path

import atheris
import yaml

# Only dsoxlab's own pure-Python modules are instrumented; PyYAML is imported
# normally so its C extension is left alone.
with atheris.instrument_imports(include=["dsoxlab"]):
    from dsoxlab.models.lab import LabDefinition

# The parser's documented contract: these mean "invalid lab, skip it" and are
# caught by discovery/scanner.py. Anything else is a bug worth reporting.
CONTRACT_EXCEPTIONS = (KeyError, ValueError, yaml.YAMLError)

_TMPDIR = Path(tempfile.mkdtemp(prefix="dsoxlab-fuzz-"))
_LAB_YAML = _TMPDIR / "lab.yaml"


def test_one_input(data: bytes) -> None:
    """Feed one fuzzer-generated document to LabDefinition.from_yaml."""
    # Decode straight from the raw bytes instead of going through
    # atheris.FuzzedDataProvider. The provider *reinterprets* the input, so a
    # seed file would reach the parser as unrelated unicode rather than as the
    # YAML it contains — the corpus would be inert and coverage would flatline.
    try:
        document = data.decode("utf-8")
    except UnicodeDecodeError:
        return  # not YAML's problem: the file layer would reject it first

    try:
        _LAB_YAML.write_text(document, encoding="utf-8")
    except (UnicodeEncodeError, OSError):
        return  # not about the parser — skip this input

    try:
        LabDefinition.from_yaml(_LAB_YAML)
    except CONTRACT_EXCEPTIONS:
        return  # contract honoured: malformed input rejected cleanly
    except RecursionError:
        # Deeply nested YAML. Left in scope on purpose: scanner.py does not
        # catch it either, so it would crash `dsoxlab list-labs` for real.
        raise


def main() -> None:
    atheris.Setup(sys.argv, test_one_input)
    atheris.Fuzz()


if __name__ == "__main__":
    main()
