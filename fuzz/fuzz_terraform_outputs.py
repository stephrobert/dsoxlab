#!/usr/bin/env python3
"""Fuzz harness for the Terraform outputs the inventory is built from.

Terraform outputs are untrusted for a third reason again: they are produced by
an **external binary** whose version, providers and output schema all move
without dsoxlab knowing. `terraform output -json` wraps every value in
`{"name": {"value": …, "type": …}}`, but a state written by another version, a
provider that renamed an output, or a hand-edited state all reach the same
reader.

**The target is the consumption, not the parsing.** `read_terraform_outputs`
does I/O and one `json.loads` whose failure is already caught; fuzzing it would
mostly measure `json.loads`. What reaches the user as a traceback is what
`build_inventory` does with the decoded document, so that is what is fuzzed
here, with a `meta.yml` describing two hosts and a target, i.e. the shape a
`runtime: vm` lab actually goes through.

Contract: `build_inventory` may reject a document it cannot honour, but only by
the exceptions listed below. Anything else is a crash for the learner, at the
moment they run a lab, with no clue that the cause is a stale Terraform state.

Run it — scratch dir FIRST, seed corpus second (see fuzz_lab_yaml.py):
    mkdir -p /tmp/fuzz-tfout
    uv run --group fuzz python fuzz/fuzz_terraform_outputs.py \
        /tmp/fuzz-tfout fuzz/corpus/terraform_outputs/ -atheris_runs=50000

See fuzz/fuzz_lab_yaml.py for why instrumentation is scoped to dsoxlab only and
why the seed corpus is what makes this harness effective.
"""

from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

import atheris

with atheris.instrument_imports(include=["dsoxlab"]):
    from dsoxlab.infra.inventory import InfraNotProvisioned, build_inventory
    from dsoxlab.models.repo import RepoMetadata

#: Rejeter un document qu'on ne peut pas honorer est légitime ; le faire par une
#: exception que personne n'attend ne l'est pas.
#:
#: `InfraNotProvisioned` en fait partie, et le harnais l'a appris à sa première
#: exécution, sur la graine `{}` : un document sans adresse est le cas NORMAL du
#: premier lancement ou de l'après-`destroy`, et la CLI le rend en une phrase.
#: Une exception dédiée pour un état attendu, c'est exactement le patron que ce
#: dépôt applique, et un harnais qui l'aurait comptée comme un crash aurait
#: réclamé de le défaire.
CONTRACT_EXCEPTIONS = (KeyError, ValueError, InfraNotProvisioned)

_TMPDIR = Path(tempfile.mkdtemp(prefix="dsoxlab-fuzz-tfout-"))
_META_YML = _TMPDIR / "meta.yml"
_META_YML.write_text(
    """\
repo:
  id: fuzz
  category: demo
infra:
  provider: kvm
  network: fuzz-net
  cidr: 10.99.0.0/24
  hosts:
    - name: un.lab
      distro: alma10
    - name: deux.lab
      distro: debian13
""",
    encoding="utf-8",
)
_REPO_META = RepoMetadata.from_yaml(_META_YML)


def test_one_input(data: bytes) -> None:
    """Feed one fuzzer-generated outputs document to build_inventory."""
    # Raw decode, not FuzzedDataProvider — see fuzz_lab_yaml.py: the provider
    # would reinterpret the seed files and make the corpus inert.
    try:
        document = data.decode("utf-8")
    except UnicodeDecodeError:
        return

    try:
        outputs = json.loads(document)
    except (json.JSONDecodeError, RecursionError):
        return
    if not isinstance(outputs, dict):
        # `read_terraform_outputs` annotates its result as a mapping, and every
        # caller obtains it from there. A non-mapping is out of scope for this
        # harness, not a defect it should report.
        return

    try:
        build_inventory(
            _REPO_META,
            terraform_outputs=outputs,
            target_fqdn="un.lab",
            roles={"server": "deux.lab"},
        )
    except CONTRACT_EXCEPTIONS:
        return
    except RecursionError:
        raise


def main() -> None:
    atheris.Setup(sys.argv, test_one_input)
    atheris.Fuzz()


if __name__ == "__main__":
    main()
