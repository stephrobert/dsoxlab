# Exit codes

**Audience:** you are writing something that *calls* dsoxlab — a CI step, a
build script, a wrapper. A code is what you branch on when there is no
document to read.

**Language:** [English](./exit-codes.md) · [Français](./exit-codes.fr.md)

An exit code is the hardest contract this tool exposes. A JSON document can gain
a field; a translated sentence can change its wording. A code, once a script
reads it, cannot move without breaking that caller silently — and without saying
a word, because a code carries no message.

So they all live in one place, `src/dsoxlab/exit_codes.py`, as an `ExitCode`
enum. Two tests hold the file honest: no value may be used twice, and every code
must appear on this page **and** on its French counterpart. A code that is not
documented is a contract nobody can read.

## The table

| Code | Name | What it means | What it calls for |
| --- | --- | --- | --- |
| `0` | — | the command did what was asked | nothing |
| `1` | `ECHEC` | the command ran, and the answer is no: unknown lab id, failing test, host that does not answer, no active context | read the message; the answer is about your work, not your setup |
| `2` | `IMPOSSIBLE` | the command could not run: infrastructure not provisioned, provider not packaged, declared fixture missing from disk, required restore point unobtainable, expected file not found | **prepare** something — this is not a mistake in your work |
| `3` | `TERRAFORM_ABSENT` | Terraform is not installed, so `provision` and `destroy` have no way to act | install it; a pipeline can automate this |
| `4` | `TERRAFORM_ECHOUE` | Terraform answered, and it failed | read its output; dsoxlab names the causes it recognises, such as a full or missing storage pool |
| `5` | `ORPHELINS` | a `provision` left orphan domains — defined on the hypervisor, absent from the state — or found some before starting | run the `virsh undefine` line the message prints |
| `6` | `ORPHELINS_NON_RETIRES` | a `destroy` could not remove those orphans | remove them by hand, then re-run `destroy` |
| `7` | `VERROU` | another dsoxlab command already holds this repository's lock | **retry** — this is the only code where retrying is right. The message names the process holding it |
| `8` | `HOTES_INJOIGNABLES` | a `provision` returned without every targeted host answering | `dsoxlab status` says which one and why; often more time or more vCPU |
| `9` | `DOCTOR_REQUIS_KO` | `doctor --strict`: a **required** check failed, and that is established | **repair** what the table names |
| `10` | `DOCTOR_INDETERMINE` | `doctor --strict`: a required check could not be measured | **measure again** — nothing is concluded, so nothing is validated |
| `127` | `EXECUTABLE_INTROUVABLE` | an expected executable is not in `PATH` | install it. 127 is the code the shell itself returns here, so a script already knows how to read it |
| `130` | `INTERROMPU` | `128 + SIGINT`, a Ctrl-C | the message gives the gesture to resume |

## Reading the table as a script

Three distinctions were made on purpose, and they are the reason this page
exists.

**`7` is the only retryable code.** Its cause is temporary by nature: another
invocation is writing. Every other code describes a state that will not change on
its own.

**`9` and `10` are separate because the gestures differ.** The first gets
repaired, the second gets measured again. An environment whose probe did not
complete is not validated for all that, and an automated build must not mistake
that for a success. When both coexist, `9` wins: a certainty outweighs an
ignorance.

**`1` and `2` split "no" from "cannot".** `check` on a failing lab exits `1` —
the tool worked, the answer is negative. `run` on a lab whose declared fixture is
missing exits `2` — nothing was measured, because the lab could not even start.

## Where the codes are not

`doctor` without `--strict` exits **0 whatever it finds**, deliberately: for a
human, a diagnosis is not a failure. The verdict lives in the `ok` field of
`--json`. It is `--strict`, not `--json`, that turns the diagnosis into `9` or
`10`.

`--json` never changes a verdict either. A command that exits `1` still prints
its document first, so a caller receiving a non-zero code can read what went
wrong. See [machine-readable output](./machine-output.md).

## Adding a code

1. Add the member to `ExitCode`, with a comment saying what it means.
2. Add a row here **and** in `exit-codes.fr.md`.
3. Raise it as `typer.Exit(ExitCode.YOUR_CODE)`, never as a bare number.

`tests/test_codes_de_sortie.py` fails if step 2 is skipped, and if any bare
literal above `4` is passed to `typer.Exit` in `src/dsoxlab/`.
