# Every dsoxlab command

**Audience:** anyone. This page is a reference, not a tutorial — the three
guides ([learner](./learner.md), [catalog author](./catalog-author.md),
[trainer](./trainer.md)) say when to reach for what.

**Language:** [English](./commands.md) · [Français](./commands.fr.md)

The table below is **generated from the CLI itself** by
`scripts/generer-doc.py`, and a test fails when it drifts. Editing it by hand is
pointless: the next run overwrites it.

For the options of a command, `dsoxlab <command> --help`. For the whole platform
guide in the terminal, `dsoxlab fullhelp`.

<!-- BEGIN COMMANDES : généré par scripts/generer-doc.py, ne pas éditer -->

| Command | Purpose |
| --- | --- |
| `dsoxlab catalog add` | Install a catalogue by name, or by its repository URL. |
| `dsoxlab catalog list` | List known catalogues and the ones installed. |
| `dsoxlab catalog remove` | Remove an installed catalogue. |
| `dsoxlab catalog update` | Update an installed catalogue (all of them if none is named). |
| `dsoxlab catalog use` | Choose the active catalogue, the one used outside its directory. |
| `dsoxlab challenge` | Display the challenge mission for this lab (challenge/README.md). |
| `dsoxlab check` | Run tests, calculate score (hints deducted) and record result. |
| `dsoxlab clean` | Remove all resources created by the lab. |
| `dsoxlab completion install` | Install completion for the current shell (zsh, bash). |
| `dsoxlab completion show` | Print the completion script on stdout, writing nothing. |
| `dsoxlab course` | Display a course section, or the table of contents if no section is given. |
| `dsoxlab demo` | Install a demonstration catalog and play a first lab, with nothing to clone and nothing to provision. |
| `dsoxlab destroy` | Destroy the lab infrastructure (terraform destroy), including machines left outside the state. |
| `dsoxlab doctor` | Diagnose the environment (runtimes, tools, detected labs). |
| `dsoxlab fullhelp` | Show the complete platform guide (concepts, workflow, commands). |
| `dsoxlab guide` | Open the lab's online guide in your web browser. |
| `dsoxlab hint` | Show the next challenge hint (deducts points from final score). |
| `dsoxlab infra status` | Check SSH connectivity to all hosts declared in meta.yml, and name the cause when one stays silent. |
| `dsoxlab install` | Deprecated: use `dsoxlab completion install`. Installs shell completion. |
| `dsoxlab instructor bootstrap` | Generate the lab SSH key (if missing) and check that terraform/ansible-runner are installed. |
| `dsoxlab list-labs` | List all available labs (filtered by active context if set). |
| `dsoxlab new catalog` | Scaffold an empty catalog: meta.yml, labs/, .gitignore, ssh/. |
| `dsoxlab new lab` | Scaffold a lab, discovered by the next list-labs. |
| `dsoxlab next` | Recommend the next lab or challenge to complete in the active context. |
| `dsoxlab progress` | Show progression by bloc (labs completed, average score, challenges and capstones). |
| `dsoxlab provision` | Provision the lab infrastructure (terraform apply on the current provider). |
| `dsoxlab reset` | Reset the lab to its initial state (clean + restart). |
| `dsoxlab run` | Prepare and start the lab environment. |
| `dsoxlab scores` | Show recorded scores history. |
| `dsoxlab show` | Show details and status of a lab. |
| `dsoxlab ssh` | Open an interactive SSH session on a lab host. |
| `dsoxlab start` | Play a lab end to end: context, prerequisites, infrastructure if needed, then the session. Every step is announced with the single command that replays it alone. |
| `dsoxlab status` | Where the active lab stands: not started, ready, in progress, validated. |
| `dsoxlab submit` | Final submission: run tests, record score, then type 'exit' to leave the session. |
| `dsoxlab support` | Produce an anonymised diagnostic report, ready to paste into an issue. |
| `dsoxlab use` | Sets the active context (section and/or default level). Use --reset to clear it. |
| `dsoxlab validate-structure` | Check structure and metadata of all labs. |

<!-- END COMMANDES -->

## Exit codes

Every code the CLI returns, what it means and the gesture it calls for, is on
[its own page](./exit-codes.md), held in step with `src/dsoxlab/exit_codes.py`
by a test. The table below is the short list; it is not the whole one, and a
script should branch on the page rather than on this excerpt.

| Code | Meaning |
| --- | --- |
| `1` | The command ran, and the answer is no: a failing test, an unknown lab id |
| `2` | The command could not run: no infrastructure, a fixture missing. Something has to be prepared, and the message says what |
| `5` | `provision` found machines a failed provisioning left outside the Terraform state. The message names the command that removes them |
| `6` | `destroy` could not remove those machines |
| `7` | Another dsoxlab command already holds this catalog's write lock. The message names it — the only code worth retrying |
| `8` | `provision` gave up waiting for hosts that never answered: the infrastructure exists, but it is not usable as it stands |
| `9` / `10` | `doctor --strict`: a required check failed, or could not be measured. The first is repaired, the second is measured again |
| `130` | The command was interrupted (Ctrl-C), and says how to resume |

Every one of them exists because a failure that does not announce itself is
worse than a failure: `destroy` used to exit successfully while leaving machines
running.

## Global options

`--verbose` / `-v` (repeatable), `--debug` (same as `-vv`) and `--version`, all
before the command. Whatever the verbosity, the full log is written to
`~/.local/state/dsoxlab/dsoxlab.log`, and never to standard output — so `--json`
stays machine-readable even in verbose mode.
