# Changelog

**Language:** [English](./CHANGELOG.md) · [Français](./CHANGELOG.fr.md)

All notable changes to this project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [0.1.67] - 2026-08-24

### Added

- **`dsoxlab catalog`: install a catalog, and use it from anywhere** (issue
  #78). Separating the engine from the catalogs is a sound architectural
  decision, but it was left entirely to the user: nothing said which catalogs
  exist, how to install one, or that dsoxlab had to be run from inside the
  cloned directory. Five subcommands close that gap:

  ```console
  $ dsoxlab catalog list              # known catalogs, and the installed ones
  $ dsoxlab catalog add linux         # clone it, and make it active
  $ cd ~ && dsoxlab list-labs         # works, with no cd into the catalog
  $ dsoxlab catalog use ansible       # switch the active one
  $ dsoxlab catalog update [<id>]     # update one, or all of them
  $ dsoxlab catalog remove <id>       # remove one
  ```

  **The current directory keeps priority.** The active catalog is consulted
  *after* walking up from the working directory, never before: someone sitting
  in a hand-cloned catalog expects to work on that one. The reverse would mean
  a `catalog add` silently changing what a `dsoxlab check` does inside an
  existing repository — a side effect that is mute, remote, and on the command
  that grades the work.

  The registry of known catalogs is a **manifest packaged with the tool**
  (`templates/catalogues.yml`), not a remote service: a registry is a component
  to host, monitor and keep available, for a project that today has three
  catalogs. A versioned manifest also has a merit a service does not — it is
  reviewable in a pull request, so proposing a third-party catalog becomes an
  ordinary contribution. Any git URL is accepted too, including one absent from
  the manifest: the manifest aids discovery, it restricts nothing.

  The engine stays domain-agnostic, and a test enforces it: `services/catalog.py`
  contains no domain name at all, only ids and URLs read from the manifest or
  the command line.

### Fixed

- **A test function name could fail the commit as a leaked secret.** The
  `trufflehog` hook runs with `--results=verified`, which is the right bar: it
  blocks on verified secrets only. But its *Lob* detector recognises that
  service's test keys by their `test_` prefix alone, and a Lob test key is
  verified **without any network call**. Measured against the hook's exact
  command: a name of **exactly 40 characters** trips it, 39 and 41 do not.

  Seven test names in this repository already had that shape. None had ever
  fired, because the hook only reads the diff — they were waiting for the first
  contributor to touch their file. They are renamed, and a test now refuses that
  length across `tests/`, `tests_e2e/` and `fuzz/`, so the defect states itself
  here, in a second and with its reason, instead of at `pre-push` disguised as a
  secret leak.

  **The detector was not excluded.** Dropping Lob would have fixed the symptom by
  removing a detection capability, for a service this project does not use today
  but may use tomorrow. Renaming costs one word and takes nothing away from the
  scan.


- **The release guard was unreliable in two ways, both observed while shipping
  0.1.65 and 0.1.66.** It guards a publication that cannot be undone, so being
  wrong costs more here than elsewhere. Nothing in the published wheel changes:
  `scripts/` is development tooling, hence no version bump.

  - *It counted untracked files as a dirty tree.* This repository permanently
    carries `/dev/null` nodes at its root (`.bashrc`, `.gitconfig`, `.idea`,
    `.mcp.json`…), which `git status --porcelain` lists as untracked. The check
    therefore passed or failed depending on whether those mounts were visible
    at that moment — intermittently, inside the very tool that guards a
    definitive publication, and a guard that fires at random ends up bypassed.
    Only **tracked** modifications block a tag now; untracked files are named in
    a warning, because a forgotten `git add` is real but no script can decide it
    for the author.
  - *`--publiee <tag>` ignored the tag it was given* and queried PyPI for the
    currently packaged version. Once the next version was merged, `--publiee
    v0.1.65` announced "version 0.1.66 is absent from PyPI": a false verdict
    about a version that had shipped correctly.

  The script had no test at all. It now has five, each failing without its fix.

## [0.1.66] - 2026-08-24

### Fixed

- **A stopped container was reported as a failed initialisation command.** When
  `post_start` met a container that was no longer running, Docker answered
  `container <64 hex characters> is not running`, and dsoxlab quoted it inside
  "initialising service 'x' failed on 'y'". Two things were wrong at once: it
  sent you looking for a defect in a command that had never been played, and it
  named the container by an identifier you had never seen. The message now says
  the container stopped, gives its **exit code** and the **last ten lines of its
  logs**, and names the container the way you declared it. The check runs only
  when a `docker exec` has actually failed, so a healthy service is never
  interrogated for nothing.

- **The documentation check was red on a contributor's machine and green in
  CI.** It scanned every Markdown file at the repository root, including
  unversioned ones. A `CLAUDE.md` mentioning `~/.config/dsoxlab/config.yaml` to
  say the path does not exist yet was enough to fail two tests locally, while CI
  — where that file does not exist — stayed green. The check now considers only
  files git tracks, and falls back to scanning everything when there is no git
  repository at all, so an extracted archive does not turn the control green by
  emptying it.

### Changed

- **The two Docker integration tests of `services` now declare the `ready_exec`
  probe the contract recommends** (issue #155). They enchained a `docker exec`
  right after `start()` without anything having proved the container could
  accept one: the implicit wait depended on how busy the machine was. Their
  failure messages also carry the container state, its exit code and its logs —
  an intermittent failure in CI leaves no other trace, and `assert x.ok` alone
  left nothing to diagnose.
## [0.1.65] - 2026-08-24

### Added

- **`--json` now covers every command whose output has a structure.** `show`,
  `scores`, `next`, `doctor` and `validate-structure` join `list-labs`,
  `progress`, `check`, `status` and `support`: ten commands, one document each,
  all going through `machine.emit()` and therefore all carrying `schema`. An
  integration could read a quarter of what the tool knows; for the rest it had
  to parse Rich tables whose width follows the terminal.

- **A verdict can be read without translating it.** `doctor` gives every check
  a stable `key` (`kvm`, `pytest`, `libvirt_pool`…) and a `state` token (`ok`,
  `failed`, `choice_required`); `validate-structure` gives every issue the
  `key` of the rule that fired, its `params`, and a `kind` naming the family.
  The translated label sits beside them, for display only. The lazy design
  would have copied the displayed sentence into a field: complete-looking, and
  unusable, since no consumer can tell green from red without parsing French or
  English. A test runs `doctor --json` in both languages and asserts the keys
  and states are identical while the labels are not.

- **[A documentation page for the machine output](docs/machine-output.md)
  ([FR](docs/machine-output.fr.md))**: every document field by field, the exit
  codes, and the evolution rule. Adding a field keeps `schema`; changing what a
  field means increments it. Translated text and pytest's raw output are
  explicitly outside the contract; the stable tokens and the exit codes are
  inside it. `fullhelp` gained a matching section, in both languages.

### Fixed

- **A diagnostic that crashed while diagnosing.** `virsh version` and
  `incus list` are run with a five-second timeout, and the `TimeoutExpired` was
  not caught: on a host whose libvirt socket never answers, it took the whole
  `doctor` command down. Now that `doctor --json` is an interface, it took the
  caller's document down with it and handed back a Python traceback. A probe
  that does not answer is now reported as a component that does not answer,
  with the gesture that fixes it.

### Changed

- `doctor --json --fix` is refused, and says why: the remediation commands write
  to standard output, and the document would come out preceded by apt's output.
  The diagnosis is read first, acted upon second.

- `Check` carries its identity (`key`) and derives its label from it, instead of
  spelling both out at each call site where nothing prevented them from
  diverging. Its `status_key` becomes a `state`, so the terminal wording and the
  machine token come from one source.

Closes #83.

## [0.1.64] - 2026-08-24

### Fixed

- **A malformed Terraform output crashed the inventory build.**
  `{"hosts": {"value": "10.99.0.11"}}` was enough: the code took the value for a
  mapping and called `.items()` on it, producing an `AttributeError` at the very
  moment someone runs a lab, and never saying that the cause was a stale
  Terraform state. That document is thirty-four bytes and nobody had written it
  by hand: the new fuzz harness found it in under thirty thousand runs.

### Added

- **Fuzzing now covers every input the engine does not produce itself.** Two
  harnesses join the two existing ones, and each asserts a different contract,
  because each input is untrusted for a different reason:

  - **`.dsoxlab-context.json`** lives on the learner's disk: hand-edited out of
    curiosity, truncated by a laptop closed mid-write, left behind by an older
    version. Its harness has **no contract exception at all**, and that is the
    whole point: `read_context` promises to return an empty context rather than
    raise, because losing the context costs one `dsoxlab use` where an exception
    costs the entire CLI.
  - **Terraform outputs** come from an external binary whose version, providers
    and output schema all move without dsoxlab knowing. The harness targets what
    `build_inventory` **does** with the document, not the `json.loads` before it:
    that one is already guarded, and fuzzing it would only measure the standard
    library.

  The CI job's header comment now lists the covered inputs and says, for each,
  why it is considered untrusted.

## [0.1.63] - 2026-08-24

- **The documentation described a product that does not exist.** Three claims
  of the "Persistence" section of both READMEs were false, and they were the
  ones a reader looking for their scores would follow: a database at
  `~/.local/share/dsoxlab/progress.db`, a user configuration file at
  `~/.config/dsoxlab/config.yaml`, and `XDG_DATA_HOME` / `XDG_CONFIG_HOME` as
  the way to move them. The database is `<catalog>/.dsoxlab.db`, one per
  catalog; no configuration file is read anywhere. Four more claims went the
  same way: progress "following the XDG spec", `incus` and `kvm` presented as
  runtimes (there are two, `shell` and `vm`, and the backend is the catalog's
  choice), an architecture map naming `IncusRuntime` and `KvmRuntime` classes
  that do not exist, and a `runtime.host` field in the flagship `lab.yaml`
  example that no code reads.

- The `--lab-home` help said "root of the linux-training repo", naming one
  catalog as if it were the only one, in both languages. It now says "the lab
  catalog".

### Added

- **A control that forbids the drift from starting again.** The documented file
  locations are now confronted with the code the same way the command table
  already was: `scripts/generer-doc.py` derives the real locations **by calling
  the functions the CLI calls**, on a throwaway `HOME`, then reports any path a
  page cites that matches none of them. Proven by mutation, and by six tests in
  `tests/test_documentation_synchrone.py`. A path may be cited as *not*
  existing, but only by the page whose subject that is, and a test checks that
  such a path really is absent from the code.

### Changed

- **Documentation split by audience**, each page naming its reader in its first
  lines: [the learner](docs/learner.md), [the catalog
  author](docs/catalog-author.md), [the trainer](docs/trainer.md), plus two
  references shared by the three ([where dsoxlab writes](docs/files.md) and
  [the commands](docs/commands.md), still generated from the CLI). Both READMEs
  keep their role as the entry point and now fit in a thirty-second read. No
  site generator is introduced: that decision belongs to the repository owner.

- `Documentation` in `pyproject.toml` points at the tool's documentation instead
  of the generic index of a blog. The architecture map moved to
  `CONTRIBUTING.md`, corrected, where the contributors it addresses will find
  it.

Closes #86.

## [0.1.62] - 2026-08-24

### Fixed

- **The first `Tab` of a session proposed nothing**, the second one worked. zsh
  loads the `#compdef` file on the first tab and expects it to produce the
  completions **for that very invocation**; the script typer generates only
  defines the function and registers it for later. A silent `Tab` reads as
  "completion does not work", and nobody presses a second time to check a
  feature they believe is missing: the cost is a silent give-up, not an
  annoyance. The installed script now calls its function after registering it,
  and the reason for that divergence from upstream is written **inside the file
  it drops**, so nobody removes it later without knowing why it is there.
  Reproduced and verified in a real zsh under a pseudo-terminal, before and
  after: calling the completion mechanism directly does not cross the layer at
  fault.

### Added

- **`dsoxlab completion install` and `dsoxlab completion show`.** The first
  installs shell completion, the second prints the script without writing
  anything, for those who would rather place it themselves.

### Deprecated

- **`dsoxlab install` is deprecated and will be removed in 0.3.0.** It was the
  first command name a user saw in the help, and it promised to install the
  tool, which is already installed. It still does what `completion install`
  does, and says so.

  It **no longer writes a wrapper** in `~/.local/bin`. Two real defects came
  from that file: a path containing a space broke the `exec` for lack of
  quoting, and above all `write_text()` on a symlink writes into **the target**,
  so uv's real binary was replaced by a script pointing at itself. `uv tool
  install` and `pipx` already put their launcher exactly there: replacing it
  only undid what their next update would restore.

## [0.1.61] - 2026-08-24

### Added

- **The published schemas are now tested against documents, not just against key
  names.** The existing check compares, by parsing `models/`, the keys the
  parser reads with the schema's `properties`: it catches a forgotten or
  invented key, and nothing of what lives inside one. A wrong `type`, an
  incomplete `enum`, a `pattern` that is too loose or a bound that is off all
  went through silently. Those defects never bother dsoxlab, which does not read
  its own schemas: they bother the catalog author, in their editor and in their
  CI. A wrong schema carries authority it has not earned, which is the least
  comfortable position there is.

  The check now runs both ways. The packaged demonstration catalog, the one
  `dsoxlab demo` drops, is validated file by file; and sixteen faulty documents,
  **one fault each**, must be rejected, at the exact location of the fault.
  Every case starts from the valid document, which is what makes the proof
  solid: if the base passes and the variant fails, it is the fault that was
  rejected, and nothing else.

### Internal

- `jsonschema` becomes a **development** dependency, never a runtime one: the
  engine has its own parser and has no business validating through the schema at
  run time.

## [0.1.60] - 2026-08-24

### Fixed

- **A malformed catalogue spoke French under `DSOXLAB_LANG=en`.** Every message
  `validate-structure` prints came from a `message` field written by hand in a
  validator dataclass, and no guard could see it: the four sinks the i18n guard
  watches (`help=`, the display helpers, `raise`, the Rich output verbs) do not
  cover a value stored in a dataclass. `ContentIssue`, `MetadataIssue` and
  `StructureIssue` now carry a **key** and its parameters, exactly like
  `ContractIssue` already did, and the CLI composes the sentence. 39 keys added
  in English and French. `check_doc_url()` follows the same rule: it returns a
  `ContentIssue` instead of a reason it wrote itself.

- **The contract errors of `meta.yml` were French too**, and they reach the
  screen: `discovery/repo.py` lets them through and `cli.py` renders them. They
  are raised as `ContractError`, which carries `source`, `field`, an i18n key
  and its parameters, the pattern `UnsupportedSchemaVersion` and
  `ProviderUnresolved` already followed. The model stays language-agnostic; the
  CLI says the sentence and frames it with the file path.

- **A mistyped field in `meta.yml` produced a raw traceback on `list-labs`**,
  because the scanner reads that file for the section order and nothing caught
  the error on that path, while the other commands went through `_read_repo`
  and got a sentence. Both paths now go through the same helper.

### Changed

- The 24 `ValueError` of `models/` were sorted on one question: does this
  message reach a human reading the interface? 17 do, through `meta.yml`, and
  follow the pattern. 7 do not: they come from a `lab.yaml`, whose only reader
  is `discovery/scanner.py`, which drops the lab and logs the reason. Those
  raise a `LabYamlError` whose text stays technical, because translating what
  is never displayed is wasted work and noise in the translation tables.

- The i18n guard now covers `models/`, whose blanket exclusion is gone, and
  gains a fifth sink for the anomalies `validate-structure` displays. It knows
  `LabYamlError` by name, which is what makes the sort **checkable**: the day
  one of those messages has to be displayed, it changes class and the guard
  asks for its key.

Closes #139.

## [0.1.59] - 2026-08-23

### Changed

- **The project description said what the tool does for its author.** "A
  domain-agnostic CLI framework driving labs spread across multiple
  repositories" was accurate when it was written. What changed since is not a
  feature but the nature of the tool: the declarative contract, interchangeable
  runtimes, validation and diagnostics make it an engine someone else can use
  for their own exercises. All four places (`pyproject.toml`, the GitHub
  description, both READMEs and `fullhelp`) now carry the same sentence: dsoxlab
  turns declarative exercises into **reproducible, runnable and verifiable**
  environments.

- **`fullhelp` advertised runtimes that no longer exist.** It promised an "incus
  container or KVM VM" where the contract only exposes two types, `shell` and
  `vm`: Incus is a backend of `vm`, picked by the catalog's `meta.yml`, not a
  runtime a learner declares. It also tied every lab to a guide on one specific
  site, and listed levels (`l1`, `lfcs`, `rhcsa`) that belong to one particular
  catalog, when it is the catalog that names its own sections and levels.

## [0.1.58] - 2026-08-23

### Fixed

- **`doctor` reported "0 labs" without saying why.** `list-labs` explains it
  well: it names the file, the offending version and the command that fixes it.
  `doctor` showed a silent red, although it is the command people run when
  something is wrong, and the one they paste into a bug report. The check now
  compares the `lab.yaml` files **present on disk** with the labs actually
  loaded, and names the gap. That gap covers all three ways a lab becomes
  invisible at once, with no need to guess which one applies: a `schema_version`
  that is too new, a file that raises while parsing, or a lab declared in
  `meta.yml` but missing from disk.

- **A `lab.yaml` that raises while parsing only went to the log**, which nothing
  displays: it vanished without a usable trace — trap #4 in the repository's
  `CLAUDE.md`. `CatalogScan` now keeps the path and the reason.

### Internal

- The `lab.yaml` search rule is extracted into the scanner and exposed through
  `compter_fichiers_labs()`. A first attempt duplicated it inside `doctor`, and
  the two definitions diverged as they were written: the count ignored the
  `tp-*/` layout the scanner accepts for older repositories.

## [0.1.57] - 2026-08-23

### Fixed

- **A missing executable produced a Python traceback.** The CLI carefully turns
  `CommandError`, `DomainNotFound`, `UnsupportedSchemaVersion` and the contract
  errors into a translated message plus an exit code; `FileNotFoundError` went
  straight through to the interpreter. A traceback says "the tool is broken"
  when what is usually missing is a binary the learner can install themselves.
  The net sits in `_I18nGroup.invoke`, alongside the Ctrl-C one: the only point
  that covers all twenty-four commands without instrumenting any of them. A name
  with no separator was looked up in `PATH`, so it is an executable and the exit
  code is **127**, the one the shell uses for "command not found"; a path is a
  file and yields **2**.

### Changed

- **`click` is no longer a declared dependency.** Its last importer went away in
  0.1.50 with the completion migration to `autocompletion=`, and typer 0.27 no
  longer depends on click: it vendors it. The dependency was installed for
  nothing. Verified after removal: `click` disappears from `uv.lock` entirely,
  all 544 unit tests and 16 end-to-end tests pass, and the installed wheel still
  drives the three catalogues.

## [0.1.56] - 2026-08-21

### Fixed

- **Snapshots worked on no dsoxlab VM at all, and the failure was silent.** The
  packaged Terraform template boots its machines in UEFI — modern cloud images
  no longer ship a legacy BIOS bootloader — and libvirt refuses *internal*
  snapshots on pflash firmware: `internal snapshots of a VM with pflash based
  firmware are not supported`. `infra/snapshot/kvm.py` asked for exactly that.
  It now takes an **external** snapshot (`--disk-only --atomic`), verified on a
  real UEFI domain.

- **The overlay path is passed, not guessed.** On a `type='volume'` disk — the
  form the template produces — libvirt refuses to derive the name itself
  (`cannot generate external snapshot name for disk 'vda' without source`), so
  a naive external snapshot fails just as the internal one did. `create` now
  passes one `--diskspec` per writable disk. The cloud-init cdrom is left out:
  giving it a diskspec would fail the whole snapshot.

- **`run` now fails when a required checkpoint cannot be taken.** This is the
  change that matters most. `runtimes/vm.py` swallowed the failure in a
  `logger.warning`, and no `logging.basicConfig` exists in this package: a lab
  declaring `snapshot_required: true` started **without the safety net it asks
  for**, `run` exited 0, and the learner found out when they needed it. That
  silence is what let the feature stay broken unseen. A lab that can live
  without a net still declares `snapshot_required: false`, which is the default
  and what every lab in every catalogue declares today.

- **Rolling back is a different operation, and it is implemented as one.**
  libvirt refuses `snapshot-revert` on an external snapshot (`Invalid target
  domain state 'disk-snapshot'`). `revert` now stops the machine, empties the
  overlay through libvirt's own storage API and restarts it — the disk path
  never changes, so the domain XML is never rewritten and the checkpoint stays
  usable. It refuses to run when the checkpoint is no longer the disk's top
  layer, rather than dropping the wrong file.

- **`clean` and `destroy` know about the overlay file.** An external snapshot
  leaves an artefact Terraform has never heard of: it is in no state file, and
  the volume beneath it gets deleted from under it. `clean` drops the
  checkpoint through `snapshot-delete`, which merges the overlay back and
  removes the file; `destroy` purges every checkpoint **before** Terraform runs,
  because after the `undefine` the metadata is gone with the domain and the file
  becomes untraceable. Same defect family as the orphan domains of #107.

### Added

- **`reset` finally gives `snapshot_required` an observable effect.** On a lab
  that declares it, `dsoxlab reset` rolls the machine back to its checkpoint
  instead of replaying `cleanup.yaml`, then replays `setup.yaml`. Labs that do
  not declare it keep the exact previous behaviour.

- **The contract says what a checkpoint captures, and what it does not.**
  `docs/contract-v1.md`, its French counterpart and `schemas/lab.schema.json`
  now state the disk/memory boundary: rolling back reboots from a consistent
  disk state, it does not put the machine back in the second before. A lab whose
  exercise depends on a running process must replay it.
## [0.1.55] - 2026-08-21

### Added

- **A write lock per repository, so two terminals stop overwriting each other.**
  Nothing prevented two `dsoxlab` from working at once on the same repository,
  and two open terminals is the normal case for a learner. The shared state is
  spread wide: `.dsoxlab-context.json` is rewritten *whole* on every change, so
  the second write silently discarded the first; the Terraform state under
  `~/.local/state/dsoxlab/<repo-id>/`; the regenerated inventory and `ssh_config`
  fragment; the `runtime.services` containers, named per repository and therefore
  shared. Only the SQLite progress database was protected, by SQLite itself.
  `provision`, `destroy`, `run`, `check`, `submit`, `reset`, `clean` and `use`
  now take the lock. A second invocation is refused with exit code **7** and a
  translated message naming the holding command, its PID and how long it has been
  running.

- **Read commands are never blocked.** `list-labs`, `show`, `scores`, `progress`,
  `next`, `status`, `doctor`, `course`, `challenge`, `hint`, `guide`,
  `validate-structure` and `support` do not take the lock: consulting the
  catalogue while a `provision` runs in another terminal is normal use, not a
  conflict.

- **A stale lock is never something to delete by hand.** The lock is a `flock`
  held on a file in the repository's own state directory, right next to the
  Terraform state it protects. The kernel releases it when the descriptor closes,
  so a holder killed with `SIGKILL`, or lost in a reboot, leaves nothing to clean
  up: there is no stale lock to "recover", which is the hard part of every
  sentinel-file lock. The file survives and is truncated on release, so it can
  never name a command that finished hours ago, and it is never unlinked, which
  is the classic race where one process pulls the inode out from under another.
  On a filesystem that cannot lock (`ENOLCK`), the command runs unprotected with
  a warning in the journal rather than refusing to start.

- **`run` hands the lock back before opening the session.** A lock held "for the
  whole command" would cover the interactive sub-shell, and that is exactly where
  the learner types `dsoxlab check`, which would then be refused by its own
  session.

### Fixed

- **Ctrl-C no longer returns the prompt without a word.** Nothing caught
  `KeyboardInterrupt` outside the pager. Typer turns it into `Exit(130)` at the
  very bottom, so the exit code was already right, and that is exactly what made
  the defect invisible: the learner got their prompt back with no idea what had
  been interrupted, what was still standing, or what to replay. Every long step
  now names those three things, and still exits **130** (`128 + SIGINT`, what the
  shell itself returns). One step also lied about the code, and it is the next
  entry.

- **Terraform is stopped in two steps instead of being raced.** It now runs in
  its own session (`start_new_session`). In the shared process group, the
  terminal's Ctrl-C reached dsoxlab and Terraform at the same instant, so dsoxlab
  could never know whether the child had already been signalled, and sending it
  one risked counting as the *second* interrupt, the one that makes Terraform
  exit without finishing the resource in flight. Isolated, the child receives
  only what dsoxlab sends: the first Ctrl-C forwards `SIGINT` and keeps draining
  its output so it can finish and save its state, and the second escalates to
  `SIGTERM` then `SIGKILL`. Before, a second Ctrl-C broke out of the
  `finally: proc.wait()` and left Terraform running, orphaned, still creating
  machines nobody was watching.

- **An interrupted playbook is no longer reported as a failed playbook.** This
  is the one path where the exit code itself was wrong. `ansible-runner`
  installs its own `SIGINT` and `SIGTERM` handlers whenever no `cancel_callback`
  is given, and never restores them. Two consequences, both measured on the
  installed version: during a playbook, Ctrl-C raised no `KeyboardInterrupt` at
  all, the run was cancelled, and the caller turned the resulting `rc=254,
  status=canceled` into "setup.yaml failed" and exit code **2**; and after the
  playbook, `SIGINT` *and* `SIGTERM` stayed hijacked for the rest of the process,
  so a `kill` on dsoxlab had no effect. dsoxlab now supplies the callback and
  restores the handlers it found.

- **An interrupted `check` no longer leaves pytest running behind it.** The read
  loop was abandoned without waiting for the child: pytest kept driving the lab
  machine while the learner believed everything had stopped, and the process
  stayed a zombie until the CLI exited. It is now killed, and nothing is
  recorded, because an interrupted validation must not cost a score.

- **The remaining interruption points are named too**: the Terraform provider
  download, the post-provision SSH wait (the infrastructure itself is up, and
  replaying `provision` is idempotent), the container services (one may be up
  without having been initialised, which the next `run` repairs by replaying
  `post_start`), and the interactive lab session. A Ctrl-C anywhere else is
  caught by a last-resort net installed on the Click group, the last place able
  to give the interruption a name before Typer turns it into a silent exit 130.
## [0.1.54] - 2026-08-21

### Fixed

- **A declared `section` is no longer overwritten by the engine.** The default
  value of `LabDefinition.section` was `linux`, and the scanner used that same
  string as its "nothing declared" sentinel. The two were therefore
  indistinguishable: a lab writing `section: linux` in a catalog whose category
  is something else had its declaration silently replaced. The sentinel is now
  `None`, the legacy path inference returns `None` rather than inventing a
  value, and a domain name no longer lives anywhere in the code that reads a
  catalog. No existing catalog changes behaviour — none of the 284 labs
  declares `section: linux` — but the next third-party author would have hit
  it.

- **Section and level colours no longer come from a list of domains.**
  `reporting/console.py` mapped `linux`, `ansible`, `terraform`, `kubernetes`,
  `rhcsa`… to colours, which is domain knowledge in the engine, with one
  visible consequence: catalogs on that list were coloured, every other one was
  uniformly white. The colour is now derived from the name itself (`crc32` over
  a fixed palette): stable across runs, and available to every catalog.

- **`exam_passing_score` finally sets a pass mark.** Eleven exam labs declared
  one — the RHCSA and LFCS mocks, and nine drills — with a comment explaining
  the chosen threshold, and nothing read it: a learner handing in 40/100 on a
  mock RHCSA read nowhere that they had failed. It is now part of the contract,
  as a **percentage** of the lab scale, and it is rendered by `dsoxlab show`
  before the exam, by `dsoxlab submit` as a pass/fail verdict, and by `dsoxlab
  scores` as a Verdict column. The comparison is exact: 69.5 % of the scale
  fails a 70 % bar.

- **`meta.yml` gains the translation mechanism the rest of the contract
  already had.** Section titles are the bloc names shown by `dsoxlab progress`,
  and all three catalogs write them in French, so an English session read
  French. One catalog had tried `title_en:` / `description_en:`, which nothing
  read. A `meta.<lang>.yml` next to `meta.yml` now overrides `repo.title`,
  `repo.description`, `sections[].title` and `sections[].description` — the
  same per-file convention as `lab.<lang>.yaml`, with sections matched by `id`
  rather than by position. The packaged demonstration catalog ships one.

### Added

- **`validate-structure` reports every key nothing reads.** The real fix for
  the four dead keys is not to settle those four: it is that a fifth cannot
  install itself in silence. The check re-reads `meta.yml`, `lab.yaml` and
  their translation files from disk, descends into every block the contract
  describes, and names each unknown key along with the closest key the engine
  actually reads. It leaves the free-form mappings alone —
  `runtime.targets[].roles`, `runtime.services[].env`,
  `infra.providers.<provider>` — whose keys belong to the catalog. The known
  keys are held against the published JSON Schemas by a test, so the two cannot
  drift.

  The **parser stays tolerant**: ignoring unknown keys is a v1 guarantee, and
  it is what lets a v1 tool survive a v1.1 catalog. This is a lint, not the
  parser.

  Consequence for catalogs as they stand: `linux-dsoxlab-training` reports
  `runtime.hosts_required` (one lab, redundant with the two targets it already
  declares), and `terraform-training` reports `sections[].title_en` and
  `sections[].description_en` (to be moved into a `meta.fr.yml`).
  `ansible-training` is clean.

## [0.1.53] - 2026-08-21

### Changed

- **The i18n guard now reads the whole package, not just `cli.py`.** The rule
  "every displayed text goes through `_()`" was already held by a test, which is
  the right way to hold it. But that test parsed a single file. Everything raised
  from `infra/`, `runtimes/`, `services/` and `templates/` escaped it, and those
  are precisely the messages a learner reads when something breaks: an entirely
  English session answered `terraform est absent du PATH`. The rule had a keeper
  watching one door out of five.

- **The criterion is written into the test, because it is the hard part.** A
  guard too loose keeps nothing; too strict, it gets disabled at the first false
  positive. A literal is interface text when two things are true together. It
  reaches a human, through one of four sinks: `help=` and `description=`, the
  `error`/`info`/`warn`/`success` helpers, the text of a `raise` (this CLI
  renders errors with `error(str(exc))`, so an exception message *is* interface
  text), and the `.print()`/`.echo()`/`.secho()` output verbs. And it reads as a
  sentence, defined as at least two words separated by a space, a whitespace-free
  fragment counting for a single word. That last clause is the whole tuning: it
  lets `meta.yml`, `challenge/tests`, `lab_starting` and pure layout such as
  `f"  ✔ {fqdn} ({ip})"` through, while catching anything written to be read.

- **Two exclusions are decided out loud, each held by its own test.** `logger.*`
  is not an interface sink: the journal is a diagnostic artefact, read beside a
  Python traceback, and translating it would make two bug reports incomparable
  depending on the locale of whoever produced them. `models/` is left out because
  the right pattern already lives there, `UnsupportedSchemaVersion` and
  `ProviderUnresolved` carrying data while the CLI composes the translated
  sentence; converting the contract's 24 `ValueError`s to that pattern is a
  redesign, not an i18n fix.

### Fixed

- **43 hardcoded French sentences no longer leak into an English session.** They
  are the consequence of the extended guard, not the reason for it: it surfaced
  all of them at once, in `infra/credentials.py` (13), `runtimes/vm.py` (8),
  `runtimes/services.py` (5), `infra/inventory.py` (4), `infra/terraform.py` (4),
  `infra/ansible.py` (3), `runtimes/manager.py` (2), `templates/__init__.py` (2),
  `infra/snapshot/__init__.py` (1) and `services/lab_service.py` (1). The 38 new
  keys were added to `i18n/strings/en.py` and `i18n/strings/fr.py` at the same
  time, and `dsoxlab provision` without terraform on the PATH now answers in the
  language of the session, which was the symptom that opened the issue.
## [0.1.52] - 2026-08-21

### Fixed

- **VM disks are declared by path, and AppArmor stops denying every one of
  them.** The packaged KVM template asked for a disk declared as a pool
  reference (`<disk type='volume'>`), and `virt-aa-helper` — which builds the
  per-domain AppArmor profile out of that XML — cannot resolve that form into a
  file path. No disk entered the profile at all, and qemu was refused
  everything: `Could not open '…qcow2': Permission denied`, on a machine where
  `dsoxlab doctor` had just gone green. It looked like an ownership problem and
  was not: setting every volume to `libvirt-qemu:kvm` changed nothing.

  The three disks — system, cloud-init seed and the optional extra disk — now
  point at the absolute path of their volume. The volumes are still created in
  the pool; only the way the domain designates them changes. libvirt then grants
  the rights by itself, lock right `k` included, the one without which the
  failure becomes `Failed to lock byte 100`.

  Nothing is changed on the learner's machine, and that is the point. Setting
  `security_driver = "none"` in `/etc/libvirt/qemu.conf` does start the domain,
  and also switches off the confinement of every VM on that host — taught, in a
  DevSecOps tool, to people learning the trade. A local AppArmor rule would have
  worked too, but it is a system change this fix does not need.

  Measured on Ubuntu 24.04.2 with dmacvicar/libvirt 0.9.8 and the distribution's
  `virt-aa-helper`, on two domains created side by side from the same volume:
  `type='volume'` produced a profile carrying no disk rule at all, `type='file'`
  produced `"/var/lib/…/x.qcow2" rwk,`. What remains to be confirmed on a truly
  fresh machine is the end of the journey, because the development host runs its
  libvirt profiles in `complain` mode, where every VM starts either way.

- **`doctor` no longer mistakes a stopped storage pool for a missing one.**
  `virsh pool-list --name` lists only the *active* pools. A pool defined but
  never started did not appear there, the check declared it missing, and offered
  a `pool-define-as` that fails on the spot with "pool already exists".
  Terraform, for its part, exits on an entirely different message there
  (`storage pool 'x' is not active`), and the gesture that unblocks is
  `pool-start`. The two states are now told apart, each with its own
  remediation.

- **The remediation names the pool the repository really targets.** The "Pool
  Not Found" explanation printed after a failed `provision` hardcoded `default`.
  A catalog pointing at its own pool through `infra.providers.kvm.storage_pool`
  was handed the creation command for a pool nobody uses. The name is now read
  from the message libvirt produced.

### Added

- **`infra.providers.kvm.storage_pool` enters the documented contract.** The
  setting has been readable by the packaged template since 0.1.42 and described
  nowhere, so a trainer whose pool is not called `default` had no way to learn
  of it short of reading the packaged Terraform. `docs/contract-v1.md`, its
  French counterpart and `schemas/meta.schema.json` now carry it, with `default`
  as its default value. No contract version bump: an optional field with a
  default breaks no catalog.

- **A test reads the template and demands that the contract describe it.** It
  walks the `lookup(var.provider_config, …)` calls of the KVM `main.tf` and
  fails on any key that is steerable from `meta.yml` yet absent from the three
  documents, or whose default has drifted. The bidirectional check of
  `tests/test_json_schemas.py` cannot see these keys, since they never pass
  through `models/repo.py`: this is the door that was missing.

## [0.1.51] - 2026-08-21

### Added

- **A black-box end-to-end suite, `tests_e2e/`.** The 421 unit tests all speak
  to the engine from the inside. They prove the functions do what they say; they
  never prove that *the installed program* behaves as promised. A broken entry
  point, a data file missing from the wheel, a mis-declared `console_scripts`:
  none of it was detectable by a green suite. The new suite builds the wheel,
  installs it into a throwaway virtualenv and drives the `dsoxlab` binary by
  subprocess, asserting only on the exit code, stdout, stderr and the files left
  on disk.

- **The newcomer's path is replayed in full:** `demo`, `list-labs`, `run`,
  `check`, `scores`, from a bare machine to 100/100 on the packaged
  demonstration lab. It needs no KVM, no Incus, no Docker and no privilege — the
  demonstration catalog is a `shell` lab — and the job takes about six seconds,
  wheel build included.

- **The suite can fail, and that is the whole point.** The same lab is worth
  100/100 once solved and 0/100 with a non-zero exit code when it is not; taking
  its single hint drops the same flawless run to 80/100. Excluding the
  demonstration catalog from the wheel turns the packaging checks red and takes
  the whole journey down with them, which is the proof that what is under test
  is the distribution and not the source tree.

- **The "no `dsoxlab` import" rule is held by a test,** on the model of
  `tests/test_i18n_coverage.py`. Three doors, because one alone can be walked
  around: a syntax check over every file of the suite for `import dsoxlab`, a
  second for the dynamic route (`importlib.import_module("dsoxlab")`), and a
  third that reads `sys.modules` at run time, which no syntactic trick escapes.

### Changed

- **CI gains a job of its own, `End-to-end (black box, installed wheel)`.** It
  is kept separate from the unit matrix on purpose: a red end-to-end run and a
  red unit run do not mean the same thing, and only the first one says the
  packaged tool is broken. `tests_e2e/` carries its own `pytest.ini`, so
  `uv run pytest` still runs the unit suite alone and the contribution gate
  keeps its measured duration.

- The ruff step now lints `tests_e2e` as well, aligning it with the pre-commit
  hook, which has always run on every Python file of the tree.

## [0.1.50] - 2026-08-20

### Changed

- **Shell completion no longer relies on `shell_complete`, which typer
  deprecates.** The ten `lab_id` arguments (`show`, `run`, `course`,
  `challenge`, `guide`, `hint`, `check`, `submit`, `reset`, `clean`) went
  through click's `shell_complete=`, a keyword typer 0.27 warns about and
  announces the removal of. Moving to `autocompletion=` is not a rename: the
  callback no longer receives `(ctx, param, incomplete)` positionally, but the
  parameters typer derives from its annotations, and it now returns
  `(value, help)` pairs instead of click `CompletionItem` objects, which typer
  refuses. The help text next to each proposal, the lab title, is preserved:
  zsh still displays `lab-id -- Lab title`.

- **The suite no longer emits a single typer `DeprecationWarning`,** down from
  490 per run. A deprecation drowned in 490 others is no longer a signal, and
  the next one, the one that will matter, would have arrived in that noise.

### Added

- **Completion is now covered by tests that actually trigger it.** Nothing
  exercised the mechanism: the completion could have stopped proposing anything
  at all while ruff, mypy and the whole suite stayed green, and the failure
  would only have shown up as a `Tab` that does nothing on a learner's machine.
  The new tests ask the CLI for a completion the way the shell does, through the
  environment variable the generated zsh script sets, and read what comes back:
  the proposals themselves, the prefix filtering, the help text, all ten
  commands one by one, and the degraded cases (outside a lab repository, with a
  broken `meta.yml`, with a contract too recent to read) where the blind
  `except` must yield no proposal rather than a Python traceback in the shell.

## [0.1.49] - 2026-08-20

### Fixed

- **`doctor` declared Terraform green without reading its exit code.** The check
  ran `terraform version` and only ever looked at stdout: a binary that is
  present but unusable — corrupted plugin cache, broken wrapper, wrong
  architecture — exits non-zero with nothing on stdout, so the check printed
  "ok" and reported success. `provision` then failed on a machine `doctor` had
  just called ready, which is the worst thing a diagnostic can do. The exit code
  is now read, and the failure carries the last line of Terraform's own error.

- **A DHCP lease that libvirt refused was dropped in silence.** `provision`
  adds the missing static leases of an existing KVM network on a best-effort
  basis; a `virsh net-update` that failed logged nothing at all. Without that
  lease the host never gets its address, and the failure only surfaced much
  later as an "unreachable host" that named no cause. Best-effort now means
  "keep going", not "say nothing": the refusal is logged as a warning.

### Changed

- **The lint rule set is declared in full in `pyproject.toml`.** The
  configuration relied on ruff's default selection and only extended it with
  `S`. Ruff 0.16 widened that default: the same command, on the same code, went
  from 0 to 123 errors, none of which belonged to `E`, `F` or `S` — a change of
  scope nobody decided, arriving with a version bump. `select` now replaces the
  default rather than extending it (`F`, `E`, `W`, `I`, `UP`, `B`, `S`, `SIM`,
  `ISC`, `RUF`, `PLE`, `PLW`, `BLE`, `DTZ`, `LOG`, `G`, `PTH`, `PYI`, `EXE`,
  `FURB`), and every family left out is named there with the measurement that
  justifies it.

- **Every `subprocess.run` now states whether it checks its exit code.** The 19
  calls that omitted `check=` were reviewed one by one: all 19 were deliberate —
  a probe whose exit code *is* the answer, a wait loop, a fix cascade that must
  survive one failure. They now say so with `check=False` and a comment. One of
  them, however, read its exit code nowhere, and that one was the Terraform bug
  above.

- **`typer` 0.26.8 → 0.27.1, `pre-commit` 4.6.0 → 4.6.2, `ruff` → 0.16.3.**

## [0.1.48] - 2026-08-20

### Fixed

- **`virsh` was called through `sudo` without need, which switched the
  diagnosis off exactly where it helps most.** The configuration libvirt
  recommends is to add the user to the `libvirt` group: they then reach the
  system URI without `sudo`, and with no `NOPASSWD` anywhere. Requiring
  `sudo -n` up front therefore answered "hypervisor cannot be queried" on a
  machine where `virsh list --all` works perfectly, and that machine is the one
  belonging to a learner discovering the tool. dsoxlab now detects the path that
  answers, direct first then `sudo -n`, and declares the URI
  (`--connect qemu:///system`) instead of depending on whichever one the
  distribution picks: the real reason `sudo` was needed here was the URI, not
  the privilege.

  The `-n` is kept on the fallback, and it is not decorative: the output of
  these commands is captured, so a password prompt would have no terminal to
  appear on and the call would hang until the timeout.

  The snapshot backend now goes through the same door. Its four calls hardcoded
  `sudo virsh` **without** `-n`: those were the ones that would hang.

- **`status` printed two markers per host line**, `✘   ✘ host.lab`, because
  `error()` already emits one. It reads as a rendering bug in the very output we
  show a learner.


- **A failed `provision` left machines behind, and `destroy` reported success
  without seeing them.** When `libvirt_domain` fails at startup, the provider
  has already *defined* the domain but never records it in the Terraform state.
  `terraform destroy` therefore had nothing to delete: the command printed
  `✔ Infrastructure destroyed.` and exited 0 while the machines were still
  standing, and every later `apply` died on `domain already exists`. On a fresh
  Ubuntu, where the first provisioning fails for other reasons, no `dsoxlab`
  command got the learner out — and the recovery procedure documented in the
  catalogues is precisely `destroy` then `provision`.

  `provision` now looks at the hypervisor before starting: machines declared in
  the `meta.yml` that exist there without being in the state are named, along
  with the exact `virsh undefine` command that removes them, and the command
  exits 5 instead of spending a minute on an `apply` that cannot succeed.
  `destroy` looks again once Terraform has finished, and removes what it left
  behind — after an explicit confirmation, since nothing proves to `dsoxlab`
  that a domain with the same name is its own. `--yes` counts as confirmation.
  A refused confirmation, or a removal that fails, exits 6 and names the manual
  command: a machine still standing must never be reported as destroyed.

  Only the `infra.hosts[].name` entries of the current repository are ever
  considered, so a machine this catalogue does not declare is never named and
  never removed. A successful `provision` followed by a `destroy` behaves
  exactly as before, with no extra warning. (#107)

- **`status` never asked libvirt for its state: two guesses instead of a
  diagnosis.** The command captured the real reason for each SSH failure, host
  by host, then discarded it to print a sentence offering two causes at once
  (`Cloud-init may still be running … or run 'dsoxlab provision'`). Both were
  wrong in the observed case: three hosts, one answering, two on
  `No route to host`. `EHOSTUNREACH` and `ECONNREFUSED` say **opposite** things
  about a machine, and the tool treated them alike.

  On a provider whose machine state can be queried, `status` now asks the
  hypervisor and names one cause, and one gesture, per host: a domain that does
  not exist points at `dsoxlab provision`; a domain that is stopped points at
  `virsh start` and says which state libvirt reports; a running domain with no
  DHCP lease points at `virsh console`; a running domain holding its address
  points at cloud-init and at waiting. Where the hypervisor cannot be asked, the
  SSH layer alone still separates "nothing answers at this address" from
  "something answers and refuses the port".

  The interrogation is lazy — nothing is asked while every host answers — and
  never fatal. A provider with no queryable state, a missing `virsh`, a refused
  `sudo` or a dead daemon all fall back to the previous behaviour **and say so**,
  because turning "I could not look" into "nothing exists" would be a false
  diagnosis. `--json` carries `domain`, `domain_state` and `cause` per host, plus
  a `hypervisor` block that distinguishes an empty answer from no answer at all.
  (#122)

### Changed

- **`virsh` is invoked as `sudo -n virsh`.** The output of these commands is
  captured, so a password prompt had no terminal to appear on and the call hung
  until the timeout. With `-n`, `sudo` refuses immediately and the caller can
  report it. This also affects the KVM snapshot backend, which used the
  interactive form.

- **`status` runs its SSH probes under `LC_ALL=C`.** The failure reason comes
  from `strerror`, which the C library translates: without this lock,
  `No route to host` reads differently on every machine and no diagnosis could
  recognise it.

- `incus` and `outscale` are explicitly out of scope for hypervisor
  interrogation, and the code says why: the incus template creates
  `incus_instance` resources, which the incus daemon owns and `virsh` cannot
  see, and Outscale is a remote cloud with no local hypervisor. Both keep their
  previous behaviour, stated rather than silent.

## [0.1.47] - 2026-08-20

### Fixed

- **KVM snapshots aimed at a domain that does not exist.** The packaged
  Terraform template names each libvirt domain after `infra.hosts[].name` from
  `meta.yml`, unchanged, so a FQDN: `control-node.lab`. The snapshot backend
  assumed the opposite convention and cut the FQDN at the first dot, so
  `create`, `revert`, `delete` and `list_` all targeted `control-node`, which
  libvirt does not know. Verified on a real hypervisor: `virsh domstate
  control-node` answers `failed to get domain`, `virsh domstate
  control-node.lab` answers `running`.

  The domain name is now **resolved against libvirt** instead of being rebuilt
  from a convention: the FQDN first, which is what the template produces, then
  the short name as a fallback for infrastructures created by an earlier
  version of the template. Renaming domains on the Terraform side would have
  recreated every VM of every catalog for no benefit.

  A host that matches no domain now raises an error naming the host, the names
  tried and the domains that do exist, instead of letting `virsh`'s laconic
  `error: failed to get domain` surface. `delete` stays best-effort and only
  logs, so that cleaning up what is already gone never fails.

  Nothing activated this path — no lab in any catalog sets
  `snapshot_required: true`, and the module had no test — which is how the two
  conventions drifted apart in silence. The module docstring, which stated the
  wrong convention and authorised the drift, is corrected, and the resolution
  is now covered by tests.
## [0.1.46] - 2026-08-20

### Added

- **The input contract is versioned: `schema_version` in `meta.yml` and
  `lab.yaml`.** These two files are the public interface of the engine, and
  until now that interface had no number. A field changing meaning could
  therefore be neither announced, nor detected, nor refused: it showed up as a
  lab disappearing from the catalog, without a word. That is the most expensive
  symptom to diagnose in the whole project.

  Leaving the field out means **version 1**, so none of the 284 labs of the
  three existing catalogs has anything to change: not one declares it today.
  A file that declares a version this dsoxlab does not read is now named, and
  named differently depending on which file it is. A `meta.yml` from the future
  **stops the command**, because it describes the whole catalog and reading it
  wrong would make everything downstream untrustworthy. A single `lab.yaml` from
  the future is **left out with a warning** while the rest of the catalog is
  served normally, because otherwise nobody could ever publish the first v2 lab
  without breaking every learner not yet upgraded.

  The read is strict where the rest of the contract is lenient: `"1"`, `1.0` and
  `true` are refused rather than rounded. A version number is not a measurement,
  and silently turning `1.5` into `1` is exactly the silence this field exists to
  remove.

  Not to be confused with the JSON output version (`reporting/machine.py:
  SCHEMA`), which versions what dsoxlab **writes** for other programs. Two
  contracts, two audiences, two rhythms. They are never bumped together.

- **`dsoxlab validate-structure` now sees files that no other check can see.**
  It reads `schema_version` straight from disk, before discovery. Every other
  validator iterates over labs that were already loaded, so a file the parser
  rejects has always slipped through validation without a word. This one reports
  it, names the file, and gives the value.

- **`schemas/lab.schema.json` and `schemas/meta.schema.json`, published for
  editors and CI.** Put a `# yaml-language-server: $schema=…` line at the top of
  a file and any editor running `yaml-language-server` completes the fields and
  underlines mistakes as you type. A catalog repository can also validate its own
  YAML in CI without installing the Python tool.

  A schema that lies is worse than no schema, because it carries authority it
  does not deserve. So a test confronts both schemas with the parser **in both
  directions**: it reads `models/lab.py` and `models/repo.py`, extracts the keys
  they actually look up, and demands equality with the schema's `properties`. A
  field read by the code and missing from the schema fails; a field invented in
  the schema and read nowhere fails too; and a new nested mapping in the parser
  fails until it is described. The enumerated values are checked against the code
  constants rather than copied.

- **The v1 contract is written down**: [`docs/contract-v1.md`](docs/contract-v1.md)
  and its French counterpart list every field, whether it is required, the
  enumerated values, what may be added without a version bump, what would demand
  a v2, and the migration path to that v2 with the command that will help.

### Changed

- `discovery/scanner.py` gained `scan_catalog()`, which returns the labs **and**
  the files it had to leave out. `discover_labs()` keeps its signature and
  behaviour, as a wrapper. Callers that want to tell the user what is missing now
  can; the others are untouched.

## [0.1.45] - 2026-08-19

### Added

- **`dsoxlab demo`: a first lab you can play right after installing, with
  nothing to clone and nothing to provision.** Between `uv tool install dsoxlab`
  and the first lab played, there was an implicit piece of knowledge: that labs
  live in other repositories, which ones, and that you have to stand inside one.
  Whoever installed the tool and ran it where they were got nothing, with a `0`
  exit code saying all was well.

  The demonstration catalog holds a single `shell` lab, and **its subject is
  dsoxlab itself**: the run / course / challenge / hint / check loop, nothing
  else. That is what keeps it clear of the anti-pattern this project forbids,
  which is shipping lab templates for a technical domain. Playing it takes about
  five minutes and ends on 100/100, a path an end-to-end test walks in full.

  An existing installation is never overwritten: that directory holds the
  learner's progress and answers, and `--force` is required to start over.

- **Documentation can no longer lie about the CLI.** A new test closes both
  directions: every command quoted in the docs exists, and every command of the
  CLI is described in `fullhelp`, in English and French alike. It immediately
  found that `provision`, `destroy`, `ssh` and `status` were described **nowhere**
  in the guide, though they are the four infrastructure commands. They are now.

- **The README now opens on the user's installation, not the contributor's.**
  It started with `git clone` and `uv tool install --editable .`, a development
  setup, while the package is published on PyPI and `doctor` already recommended
  the PyPI install. A reader following it ended up with an editable checkout they
  had no reason to want. The path is now: install, play a lab, then pick a
  catalog.

- **The command table is generated from the CLI** (`scripts/generer-doc.py`),
  between markers, in both languages. Written by hand it had drifted without a
  sound: it still described `dsoxlab clean` running a `cleanup.sh`, which the
  zero-bash rule forbids, and it was missing `demo` and `support`. A pre-commit
  hook and a test refuse a stale version.

### Fixed

- **The Persistence section was wrong on all three counts.** It announced
  `~/.local/share/dsoxlab/progress.db`, a `~/.config/dsoxlab/config.yaml` and an
  `XDG_CONFIG_HOME` override. Checked against the code: the database is
  `<catalog>/.dsoxlab.db`, no configuration file is read anywhere, and the
  variables actually honoured are `XDG_DATA_HOME`, `XDG_STATE_HOME` and
  `XDG_CACHE_HOME`. Progress is **per catalog**, which the section now says.

- **`fullhelp` was missing five commands**, four of them long-standing:
  `provision`, `status`, `ssh`, `destroy`, and the new `demo`. A command absent
  from the guide does not exist for whoever reads it.

## [0.1.44] - 2026-08-19

### Added

- **`dsoxlab support`: a diagnostic report ready to paste into an issue.**
  Answering "it does not work" meant asking back for the version, the system,
  the provider, the catalog, the state of every dependency. Each round trip
  costs a day, and the tool already knew all of it. The command gathers it in
  one Markdown block, with `--json` for the same content as a machine document.

  **Anonymised by default, and tested as such**, because this report is meant to
  be pasted publicly: the home directory becomes `~`, the user name becomes
  `<user>`, public IPv4 addresses become `<ip>`, and the machine name is simply
  never collected. Private addresses stay readable on purpose: `10.10.30.11` is
  a lab VM, it identifies nobody outside the local network, and hiding it would
  make every infrastructure report useless.

  The bug report template and both `CONTRIBUTING` files now ask for this report
  instead of three fields to copy by hand.

- **`--verbose` / `-v`, `--debug`, and a persistent log.** Eleven engine modules
  write to a logger, and none of those messages ever reached a user or a file.
  The costliest case is known: a `lab.yaml` that raises while parsing is
  swallowed by a `logger.warning` then a `continue`, so the lab vanishes from
  the catalog **without a word**. That is the first symptom a catalog author
  meets, and the hardest to diagnose.

  Warnings are now shown by default, because a vanished lab is a real loss of
  content that both the author and the learner need to see. `-v` adds the
  informational level, `-vv` (or `--debug`) the full detail, and `DSOXLAB_LOG`
  does the same for cases where the command line is out of reach.

  Diagnostics always go to **standard error**, never to standard output: `--json`
  stays machine-readable even in verbose mode, which a test pins down.

  A rotating log is written to `~/.local/state/dsoxlab/dsoxlab.log` regardless of
  any option, bounded to 1 MB and three archives. That is what makes it possible
  to attach a trace to a bug report *after the fact*, instead of asking the user
  to reproduce with the right flag. A log that cannot be written (read-only HOME,
  full disk) never fails the command: it is a convenience, not a dependency.

## [0.1.43] - 2026-08-19

Three defects that only ever showed up on a user's machine: a completion that
did not complete, a launcher that did not launch, and a CLI that refused to
start because of its own state file.

### Fixed

- **Shell completion asked the CLI through a variable it does not listen to.**
  The generated script used `_DSOXL_COMPLETE`, while Click derives
  `_DSOXLAB_COMPLETE` from the program name. dsoxlab therefore answered with
  its help page, which the shell then tried to evaluate on every Tab. The zsh
  file was misnamed too (`_dsoxl` instead of `_dsoxlab`), so zsh never loaded
  it whatever it contained. The variable is now derived from the program name
  rather than copied, so the two cannot drift apart again.

- **The generated wrapper broke on any path containing a space.** It wrote
  `exec /home/me/My Tools/dsoxlab "$@"` unquoted, which the shell split into
  two arguments and reported as "not found". The path is now quoted with
  `shlex.quote`.

- **`dsoxlab install` no longer overwrites the launcher of `uv tool` or
  `pipx`.** It writes to exactly the path those tools use. The damage was worse
  than a plain overwrite, and it took a mutation test to see it: writing to a
  symlink writes to its *target*, so dsoxlab replaced uv's real binary with a
  script that `exec`s itself. The symlink survived, `resolve()` did not move,
  and the command looped forever. When a launcher already leads to this binary,
  it is now left alone.

- **A malformed `.dsoxlab-context.json` no longer takes the whole CLI down.**
  The `except` covered `JSONDecodeError` and `OSError` only, while `null`
  raised `TypeError`, `"foo"` raised `ValueError`, a non-object root raised
  `AttributeError`, and a file of arbitrary bytes raised `UnicodeDecodeError`,
  which descends from `ValueError` rather than `OSError`. Thirteen malformed
  shapes are now absorbed into an empty context, with a warning naming the
  file. Losing the context costs a `dsoxlab use`; raising cost every command,
  including those with nothing to do with it.

## [0.1.42] - 2026-08-19

An audit run on a fresh Ubuntu 24.04 VM measured **six undocumented steps**
between a green `dsoxlab doctor` and the first playable vm lab. A beginner
stops at the first one. This release closes that gap: the diagnostic now names
what is missing, before the failure rather than after it.

### Fixed

- **`ansible-core` is now a declared dependency, so a vm lab can actually
  run.** `ansible-runner` does not pull it in, contrary to what this project's
  own comment claimed: the installed tool weighed 18 MB and its `bin/`
  contained neither `ansible` nor `ansible-playbook`. Every `dsoxlab run` on a
  vm lab exited with `rc=127`, the shell code for "command not found", which
  nothing translated. The check made it worse by testing only that the
  `ansible_runner` module imports: it reported OK on a machine where no
  playbook could run. It now tests both halves, and the error message names
  `ansible-core` rather than sending the user to reinstall what they already
  have.

- **`instructor bootstrap` no longer exits 0 after printing a blocking
  error.** It reported `✘ terraform not found in PATH` and returned success. A
  learner checking the exit code, or an install script, concluded all was well
  while the SSH key had just been created for infrastructure nothing could
  provision.

- **The Terraform error no longer points at a command that does not install
  it.** `provision` said "run: dsoxlab instructor bootstrap", which only
  reports the absence in turn. The loop was closed. It now gives the install
  URL.

- **`doctor` no longer writes "not required here" above a component that is
  required.** On a catalog with 64 vm labs out of 84 and no provider selected
  yet, both hypervisors were listed under "Informational — not required here",
  followed by "these components block nothing in this repo". The checks
  deliberately stay out of the required table, since `--fix` would otherwise
  offer to install kvm **and** incus for a choice not yet made; it is the
  heading that had to tell the truth.

### Added

- **`doctor` checks Terraform, `ansible-playbook`, the libvirt pool and the ISO
  tool.** Terraform was verified nowhere, though `provision` cannot run without
  it. The libvirt `default` pool does not exist on a fresh install, and
  provisioning failed on a raw "Pool Not Found". Incus builds its
  `agent:config` CD-ROM on the host, so without `genisoimage` no instance
  starts at all. Each of these only appears when it applies: a shell-only
  catalog sees none of them, and the configuration checks stay silent while the
  hypervisor itself is missing, so one cause does not produce three red lines.

- **The libvirt storage pool is configurable** through
  `meta.yml: infra.providers.kvm.storage_pool`. The name was hardcoded in four
  places of the KVM template, so a repository could not target its own pool.

- **Known provisioning failures now come with their cause and their fix.**
  Terraform is exact but opaque to a newcomer. Three messages have a known
  cause and a one-line remedy: AppArmor denying VM disks, the missing storage
  pool, and a domain left behind by an earlier failed run. Note that the
  AppArmor case is only ever raised **after** the failure, never as a
  prediction: measured on a machine where AppArmor is enabled, the override
  absent, and eight libvirt domains running without incident, so its absence
  proves nothing on its own.

## [0.1.41] - 2026-08-19

### Added

- **`DSOXLAB_HOST_READY_TIMEOUT` sets how long `provision` waits for a host to
  become reachable.** The delay was hard-coded to 180 s. On a modest machine,
  booting several VMs at once saturates the CPU: a usage report measured a host
  ready at 181 s, one second after the wait had given up, while an audit on
  8 vCPU measured the same hosts ready in 45 s. The CPU at parallel boot is the
  limiting factor, and the learner's hardware is a property of their machine
  rather than of the labs repository, so this is an environment variable and
  not a `meta.yml` key. A value that is not a positive number falls back to the
  default instead of failing the provision, and the timeout message now names
  the variable.

- **AlmaLinux VMs install the Incus agent from the `agent:config` CD-ROM when
  the image has not done it itself.** The RHEL family ships no 9p driver
  (measured: no `9p` entry in `/proc/filesystems`), which is how cloud images
  normally fetch that agent. Without an agent Incus reports no IP at all, and
  the readiness wait expires on a VM that booted perfectly.

  This is a safety net, not the fix of a reproduced defect: on Incus 6.0.0 with
  `images:almalinux/10/cloud`, the agent already arrives through that very
  CD-ROM and provisioning succeeds without this block. It covers the setups
  where it does not, which is what a user reported in real use.

  The block is a no-op everywhere else, and it discriminates on the presence of
  `install.sh` rather than on `/dev/sr0`, because the KVM provider attaches a
  CD-ROM too (its NoCloud seed). It can never exit non-zero either: a failing
  `runcmd` ends cloud-init in `status: error`, which on its own is enough to
  hang that same wait.

## [0.1.40] - 2026-08-13

### Fixed

- **A running container is reused only if it matches the declaration.** Reuse
  was decided on the container name alone. Two labs of the same repository
  declaring a service under the same `name` but with different `ports`, `env`,
  `image` or `run_args` therefore shared whichever container came first: the
  second lab started against a service that had neither its ports nor its
  launch arguments, failed where the learner had done nothing wrong, and nothing
  reported why. The declared configuration is now stamped on the container as a
  label at `docker run` and compared on reuse; a divergent container is
  replaced. A container left by an earlier version carries no label, so it is
  treated as divergent and recreated once.

## [0.1.39] - 2026-07-28

### Added

- **Services of a repository share a Docker network, and reach each other by
  name.** A lab often needs more than one container — an application and its
  database. On Docker's default bridge there is no name resolution: the
  application can only reach the database through an IP nobody knows in advance,
  so such a lab could not be declared at all. Each service now joins a
  *user-defined* network `dsoxlab-<repo_id>` with its declared `name` as alias,
  which is what makes `DATASOURCES_DEFAULT_HOST: db` writable in a `lab.yaml`.
  The network is created on demand and survives a concurrent creation.

## [0.1.38] - 2026-07-28

### Added

- **`runtime.services[].post_start`: a service can be initialised, not just
  started.** A container that boots is rarely a usable service — a database
  wants its schema, a vault its secrets, a registry its repository. Until now
  that step fell back to a bash script at the lab root, which the learner had to
  remember to run: labs that skipped when the service was missing, or failed
  when it was there but empty. The declared commands run inside the container
  once it is ready, through `docker exec` with **no shell** (no expansion, no
  pipe, no redirection). Each entry may be written as a readable string
  (`vault kv put secret/lab k=v`, split the way a shell would, quotes honoured)
  or as an explicit argv (`["vault", "kv", "put", …]`).

  They are **replayed on every start**, including on a container that was
  already up: that is what makes the starting state identical from one lab to
  the next, whatever the previous exercise left behind — so they must be
  idempotent, exactly like a `setup.yaml`. A failing command raises
  `ServiceError` and stops the lab, naming the offending command and the
  service output, rather than letting the tests record a silent zero.

  dsoxlab stays domain-agnostic: it runs what the lab declares and knows nothing
  of secrets or schemas.

- **`runtime.services[].ready_exec`: the only trustworthy readiness signal.**
  `ready_tcp` alone is a **false positive whenever the port is published**:
  Docker installs its proxy on the host port at `run` time, and that proxy
  accepts connections before the service listens. Measured, not assumed — a
  connection succeeds on a `-p 8299:1234` whose container listens nowhere. The
  probe declared here runs *inside* the container (`vault status`,
  `pg_isready`, `redis-cli ping`…) and is retried until it succeeds or
  `ready_timeout` expires. It must be side-effect free; initialisation belongs
  in `post_start`, which now waits for the probe.

### Fixed

- **`ready_tcp` documented as what it is: a HOST port.** The docstring said
  "in the container, host side", which reads either way. It matters as soon as
  a lab remaps to cohabit: with `ports: ["8201:8200"]`, a `ready_tcp: 8200`
  probes the host's 8200 — somebody else's service — and declares it ready.

## [0.1.37] - 2026-07-28

### Fixed

- **A `shell` lab can finally ship a local module.** `ShellRuntime` copied every
  fixture on its **base name**, so `modules/stockage/main.tf` landed on
  `main.tf` and **silently overwrote** the root `main.tf`. Any lab teaching
  Terraform modules was therefore impossible to build, and the failure was
  invisible: the workdir looked plausible, only its content was wrong. The
  module docstring already promised `<lab>/fixtures/<file>` →
  `<lab>/<workdir>/<file>` with nested examples, so the code contradicted its
  own contract. The declared path is now **preserved** and intermediate
  directories are created. A path that is absolute or contains `..` is refused
  with a warning instead of being followed, so a fixture never writes outside
  the workdir. Strictly additive: none of the **136** fixtures declared across
  the three lab repositories uses a `/`, so no existing lab changes behaviour.

## [0.1.36] - 2026-07-27

### Added

- **Containerised services a lab needs, started automatically.** Some `shell`
  labs target an API the workstation does not host (a cloud emulator, a
  database, a registry). Instead of a manual `docker run` in every scenario, a
  lab now declares its service in `runtime.services`, and dsoxlab starts the
  container before `run`/`check` and stops it at `clean`. The engine stays
  **domain-agnostic**: it launches the **image the lab declares**, on the ports
  the lab declares, and knows nothing about the emulated product. Each container
  is namespaced `dsoxlab-<repo_id>-<service>`, and `ready_tcp` waits for the port
  to accept a connection before proceeding. Docker is the engine; if it is
  unreachable, `run`/`check` fail with a clear message rather than a Docker
  traceback. Verified live against the repository's cloud emulator: the service
  comes up on its port and is removed on `clean`.

Both fixes come from running a full validation campaign over an 84-lab
catalog: one incident, one leak that the campaign made visible.

### Fixed

- **`instructor bootstrap` could write an SSH key outside any lab repository.**
  It created `<root>/ssh/id_ed25519` from whatever `get_lab_home()` returned,
  and that function falls back to the **current directory** when it finds no
  `meta.yml`. Run from the tool's own repository, the command therefore dropped
  a passphrase-less private key into a public repo, where no `.gitignore`
  covered it. The `detect-private-key` hook would have refused the commit
  (verified: it exits 1 with "Private key found"), so nothing leaked, but a
  hook is bypassable with `--no-verify` and a lab key has no business being
  there. The command now refuses when the target has no `meta.yml`, and names
  the fix (`--lab-home`). Defence in depth: `ssh/`, `*.pem`, `id_ed25519` and
  `id_rsa` are now gitignored here.
- **A file descriptor leaked on every playbook run.** `_read_stdout()` read
  `ansible-runner`'s artifact file and never closed it. Harmless on one lab,
  measurable across a campaign that chains 84. The `ResourceWarning` that
  reported it was drowned in the library's own `DeprecationWarning` noise:
  once that noise was filtered, a `vm` lab went from 26 warnings to zero.

## [0.1.34] - 2026-07-27

### Fixed

- **21 user-facing strings ignored `DSOXLAB_LANG`.** The i18n rule ("every
  displayed text goes through `_()`") was stated in prose only, and prose does
  not hold: option helps and messages had drifted back into literals. Some were
  French, so an English run printed French (`dsoxlab use --provider`,
  `provision --host` and `destroy --host` helps, `Host inconnu`,
  `Cible Terraform`, the whole `doctor --fix` sudo pre-flight); others were
  English, so a French run printed English (every progress-bar label: Ansible
  task names, `Terraform init complete`, `Nothing to do`, test progress). All
  of them now live in the EN and FR catalogs, which reach 315 paired keys.
- **`destroy --host` lost its sharpest warning** while being extracted, and it
  is restored: Terraform destroys everything depending on the target, so the
  option does **not** isolate one VM from the others.

### Added

- **A guard that keeps the rule true** (`tests/test_i18n_coverage.py`): it
  parses `cli.py` and rejects any `help=`/`description=` that is not an `_()`
  call, and any literal sentence handed to `error/info/warn/success`. Pure
  layout around translated values (`f"  ✔ {fqdn} ({ip})"`) still passes. The
  guard was run against the previous commit, where it reports all 21
  violations, so it is known to fail when it should.

## [0.1.33] - 2026-07-27

Both changes come from a learner's report on their first session with the
tool: the first command they ran showed three failures, and the first
course they read scrolled off the screen.

### Fixed

- **`doctor` reported `pytest` as missing while `check` ran it fine.** The
  diagnostic looked for a `pytest` binary in `PATH`, whereas `check` resolves
  it through `resolve_pytest_cmd()`, which starts with `sys.executable -m
  pytest` — the tool's own environment, where pytest and pytest-testinfra are
  declared dependencies. So the table said red on a component that worked,
  and the remediation it offered (`uv add --dev pytest pytest-testinfra`)
  had the learner install what they already had. Both paths now share the
  same resolution, and an unresolvable pytest points at reinstalling the
  tool.

### Changed

- **`doctor` now separates what blocks this repo from what merely informs.**
  A repo whose labs are all `shell` needs no hypervisor at all; a repo that
  has picked `kvm` does not need incus. Those checks moved to an
  *Informational* table that never shows red and that `--fix` leaves alone,
  with a line saying why they are not required here. On a catalog like
  `terraform-training` (no `infra:` block, every lab `shell`), the diagnostic
  is now entirely green.
- **An unresolved provider is reported as a decision, not a failure.** When
  the `meta.yml` declares several candidates and none is active, the check is
  blocking — `provision` cannot run — but carries a *to be chosen* status and
  names the command to run. It stays a hint, never an auto-applied fix:
  picking a provider silently would decide how the learner's labs run.
- **`--fix` states its limits.** It only ever touched the components it has a
  command for; now the output says so, and points at manual remediation when
  nothing can be automated.

### Added

- **Long output goes through the pager.** `course` prints a whole README when
  the lab declares no `course.yaml` — up to a thousand lines in existing
  catalogs — which a plain local terminal cannot scroll back through. `course`
  and `challenge` now page their output when it is taller than the screen.
  Never in a pipe or a redirection, so scripted output stays plain text, and
  never for output that already fits. `$DSOXLAB_PAGER` (then `$PAGER`)
  chooses the pager, defaulting to `less -R`; `--no-pager` restores the raw
  dump.

## [0.1.32] - 2026-07-23

### Added

- **Debian 12 (bookworm) support across the three providers.** The `debian12`
  distro was already mapped to an image (qcow2 URL for kvm, `images:debian/12/cloud`
  alias for incus) and to a `debian` cloud-init template, but that template did
  not exist: any host declaring `distro: debian12` failed at provision time.
  Added `templates/cloud-init/debian.yaml.tmpl` (same `student`/`ansible`
  service accounts and hardening as the other distros). Debian 12 now
  provisions on kvm, incus and outscale.
- **Recent distros wired across all providers**: `debian13` (trixie) and
  `ubuntu26` (26.04 LTS, Resolute Raccoon), alongside `alma9` and `ubuntu22`.
  Each provider now exposes the same seven-distro set (kvm image URLs, incus
  `images:` aliases, outscale pinned OMIs), verified by
  `test_cloud_init_templates.py`. Image URLs confirmed live before wiring.
- **Regression test for distro/cloud-init consistency**
  (`tests/test_cloud_init_templates.py`): every distro a provider maps must have
  its cloud-init template, all providers must expose the same distro set, and
  `debian12` must be wired everywhere. This is the guard that the missing
  `debian.yaml.tmpl` slipped past.

### Fixed

- **Outscale only mapped OMIs for `alma10` and `ubuntu24`** while
  `distro_to_template` promised five distros. A host declaring `alma9`,
  `ubuntu22` or `debian12` on outscale resolved to an empty OMI and an opaque
  Terraform failure. `image_ids` now covers the full set (each still defaulting
  to `""`, so a catalog only pins the OMIs it actually uses), with the matching
  `image_id_alma9` / `image_id_ubuntu22` / `image_id_debian12` documented in
  `variables.tf`.
- **`element N has vanished` when adding a host to an existing KVM network.**
  The `dmacvicar/libvirt` provider cannot update a network in place: changing
  `ips[].dhcp.hosts` makes it recreate the network (issue #468), which fails and
  would drop connectivity for every attached VM. The network is now frozen after
  creation (`lifecycle { ignore_changes = [ips] }`); DHCP leases for hosts added
  later are applied live via `virsh net-update`, in a new
  `_ensure_kvm_dhcp_leases` step run before the domain apply.
- **MAC collision between repos sharing a host (KVM).** MACs were
  `52:54:00:cd:00:<idx>`, identical across repos, so two catalogs running in
  parallel gave the same MAC to their same-index VMs and one became unreachable
  (silent `No route to host`). The two middle octets are now derived from a hash
  of `repo.id`, making MACs unique per repo: the layer-2 counterpart of the
  existing per-repo CIDR isolation. Existing KVM VMs must be re-provisioned to
  pick up the new MACs.

## [0.1.31] - 2026-07-23

### Fixed

- **`dsoxlab next` suggested labs in alphabetical order.** The pedagogical
  sort relies on `bloc_order`, which the scanner never set: it stayed at 0
  unless a `lab.yaml` spelled it out, and the sort fell back to the `id`. A
  beginner was pointed at `ansible-vault` before their first playbook, or at
  writing a Bash script before ever opening a terminal. Measured: **19 of 22
  sections** in the Ansible repository.
  The `meta.yml` is documented as driving that order; it now actually does.
  The scanner derives the position from `sections[].labs[]`, so no repository
  has to copy it into its `lab.yaml` files: 197 files no longer need
  touching. An explicit `bloc_order` still wins.

## [0.1.30] - 2026-07-23

### Added

- **Three more structural checks.** **Scoring** first: dsoxlab scores **per
  test**, so a lab announcing five tasks at 20 points while shipping six
  tests really awards 16.7 per task, and the printed scale lies with no way
  for anyone to notice. It only fires when the statement announces per-task
  points: a mock exam checking several things per task is making another,
  equally valid choice. **Language parity** next, since a `.fr.md` with no
  counterpart leaves the other half of learners on missing or stale content.
  **VM targets** last, whose FQDN was only verified when playing the lab, on
  the learner's machine and after provisioning, though it is readable
  straight from the contract.
- **`validate-structure` now checks content, not just file presence.** Three
  silent drifts that no functional test catches, because they do not break a
  lab's execution: a **dead relative link** in a Markdown file (the Ansible
  repo had 150 the day the check was written there), a **solution left in
  plain text** (unrecoverable: git keeps it forever), and a **`doc_url` that
  no longer answers**, behind the `--check-urls` flag since it hits the
  network. These checks were hand-copied into each lab repository; they now
  benefit all of them. The solution check only applies to repositories that
  keep a `solution/` directory: its absence is not a fault, just another
  choice.

## [0.1.29] - 2026-07-23

### Fixed

- **`check-release.py` concluded "All good" right after warning that CI was
  still running.** Its first real use showed it: the closing message
  contradicted the warning and invited tagging exactly when `RELEASING` says
  to wait. A running CI is now a **wait** rather than a plain note: the script
  exits 2 with "too early", distinct from failure (1), where something needs
  fixing, and from the green light (0).

## [0.1.28] - 2026-07-23

### Added

- **A local check to run before pushing a tag**:
  `python3 scripts/check-release.py`. The guard added in 0.1.27 lives in the
  workflow, so it only speaks once the tag is pushed, and the tag then has to
  be deleted locally and on the remote. This script replays the same checks
  offline, plus the ones `RELEASING` left to human vigilance: clean tree,
  `main` up to date, tag consistent with `pyproject.toml`, CHANGELOG section
  present **in both languages**, `uv.lock` aligned, version still free on
  PyPI, CI green on the commit. It prints every verdict in one pass, then the
  exact command to run.

## [0.1.27] - 2026-07-23

### Fixed

- **The release workflow published under a tag that did not match the packaged
  version.** The build reads `pyproject.toml`, the tag only feeds the release
  notes, and nothing checked that they agree. Twice in a row, a tag pushed at a
  commit whose version had already moved on produced a wrong publication:
  `v0.1.22` republished 0.1.21, and `v0.1.25` built and published 0.1.26 under
  the wrong tag, so PyPI never received a 0.1.25 at all. The workflow now fails
  loudly and says what to do.

## [0.1.26] - 2026-07-23

> Published under the `v0.1.25` tag, which was pushed at a commit already
> carrying the 0.1.26 bump: PyPI never received a 0.1.25, and everything that
> version announced is present here.

### Fixed

- **The runtime icon shifted the layout.** Double-width emoji, and their
  variation selector, count as one column for Rich but render as two in the
  terminal: the line drifted and the panel border broke. The icon is dropped
  from `show` and `list-labs`. It showed "?" on every `vm` lab anyway: its table
  knew about `kvm` and `incus`, the two backward-compatible aliases, but not
  `vm`, the contract's canonical value.
- **An unknown section passed to `use` was accepted silently.**
  `dsoxlab use l2` set the filter, then `list-labs` answered "No lab found":
  the learner believed the catalog was empty when they had just set a filter
  matching nothing. The command now refuses and lists the sections declared in
  `meta.yml`.
- **Difficulty stayed in English under a French UI.** `show` printed
  "Difficulté : intermediate". The three values used by lab repositories are now
  translated; since the field is free-form by contract, any other value is
  printed as-is rather than vanishing.

## [0.1.25] - 2026-07-23

### Added

- **dsoxlab tells you when a newer version is available.** A learner installs
  the CLI once and never comes back to check: they keep playing labs with
  defects fixed long ago, and report problems already solved. The check now
  runs once a day and the notice is printed last, so it is actually read.

  It is built so it can never get in the way. The message goes to **stderr**,
  never stdout, so a `--json` document stays parseable whatever happens. It is
  skipped entirely when stderr is not a terminal, keeping CI logs clean. Any
  failure (offline, PyPI down, hostile proxy, unreadable response) is swallowed
  silently: checking a version is never a reason to break a `check`. The result
  is cached for a day, so a classroom does not hammer PyPI. Opt out with
  `DSOXLAB_NO_UPDATE_CHECK=1`.

## [0.1.24] - 2026-07-23

### Added

- **`destroy` now asks for confirmation.** The command wiped a whole park
  without a word: typed in the wrong repository, it destroyed the VMs and their
  data with no way back. It now prompts, and `--yes` / `-y` keeps scripted use
  (CI, the documented recovery procedure) working.

### Fixed

- **`check` no longer crashes on a repository that declares several providers
  with none active.** Reading the Terraform outputs raises `ProviderUnresolved`;
  the traceback surfaced raw from `inventory.py`. The learner now gets the same
  actionable message as the infra commands: pick a provider with
  `dsoxlab use --provider <name>` or `DSOXLAB_PROVIDER=<name>`. Shell labs,
  which need no infrastructure at all, are unaffected either way.

### Changed

- **`destroy --host` no longer claims to isolate a VM.** Measured on a
  three-host park: `terraform destroy -target` also destroys everything that
  depends on the target, so asking for one host planned **7** resources for
  destruction, not 4. The option help said "destroys a single VM", which is
  false and dangerous. It now states the real behaviour and points to
  `destroy` + `provision` as the reliable way to recover an unreachable
  machine, and a warning is printed at run time.

## [0.1.23] - 2026-07-22

> The `v0.1.22` tag was created on the wrong commit, before its pull request was
> merged: the release workflow republished 0.1.21 and PyPI never received a
> 0.1.22. Everything that version carried is therefore released here.

### Fixed

- **`check --json` polluted its own output.** On failure, the raw pytest output
  was printed before the JSON document, leaving the stream unparseable. The
  guard was missing on that one branch, and it is the most common case in real
  use: a lab that passes never takes it, which is exactly why the initial check
  missed it. The text is still available to callers in `check.output`.

- **`status --json` emitted nothing** when `meta.yml` declares no host. A
  catalogue made entirely of `shell` labs is a normal case, not an error: it now
  returns a document with `total: 0` instead of a Rich sentence and exit code 0.

- **Terraform plans are stable again, so `provision` can be replayed.** The
  cloud-init `instance-id` was built from `timestamp()`, so it changed on every
  run: Terraform planned a replacement of the cloud-init disk each time, and the
  libvirt provider refuses it (« Storage volumes cannot be updated »). Replaying
  a provision therefore failed on any repository, which left `destroy` then
  `provision` as the only option. The id now derives from a hash of the
  cloud-init content, and so does the volume name: a stable plan when nothing
  changed, a clean replacement when it did.

### Added

- **`dsoxlab course` now shows the lab README, not just the scenario.** The two
  files are complementary and were treated as rivals: `scenario` sets the
  situation in a few lines, `README` explains the commands and walks through the
  exercises. Only the first was ever displayed, so the richer half was reachable
  by no command at all (measured: 10 465 lines of code sitting in the READMEs of
  a single repository, exposed by nothing). Learners concluded there was no
  course and went looking for the answer in the challenge brief. `course` now
  prints the scenario, then the README, in the requested language.

- **An SSH fragment per course, in `~/.ssh/config.d/<repo-id>.conf`.** Written
  by `provision`, refreshed by `status`, removed by `destroy`. Briefs ask
  learners to connect to a machine by name, but that name is in neither DNS nor
  `/etc/hosts`: `ssh alma-rhcsa-1.lab` simply failed. It now works, with no
  `-F` and no `dsoxlab` prefix. A warning is raised when `~/.ssh/config` lacks
  the `Include ~/.ssh/config.d/*.conf` line, since the fragment would be written
  but never read. It is removed on `destroy` so that no configuration is left
  pointing at recycled addresses.

- **The welcome panel names the lab machine** for a `session: local` lab that
  still runs on a host, so the learner knows where to connect without having to
  guess the hostname.

- **`bloc` and `bloc_order` in the JSON catalogue.** The CLI sorts on them, but
  they were not published, leaving an integration with only `section` to group
  by, which defaults to `repo.category`. Measured: 84 labs under a single node
  in `linux-dsoxlab-training`.

## [0.1.21] - 2026-07-22

### Added

- **`runtime.session` in `lab.yaml`** — a `vm` lab can now declare where its
  interactive session opens: `target` (default, SSH onto `targets[].host`,
  unchanged behaviour) or `local`, a subshell on the learner's own machine, at
  the repository root.

  Some catalogues are driven *from* the workstation rather than *inside* the
  machine: the learner writes code in the repository and runs commands against
  the lab hosts, which stay provisioned and are still targeted by `setup.yaml`.
  For those, `dsoxlab run` used to open an SSH session on a host holding
  neither the repository nor its tooling — the session opened, but there was
  nothing to do in it. The welcome panel now states where you landed, and
  `validate-structure` rejects any value outside the two accepted ones, which
  would otherwise fall back silently to SSH.

### Fixed

- **`dsoxlab run` announced the wrong location.** The ready message stated
  "You are now in `challenge/work/`" for every runtime, including `vm` labs,
  where that directory is never where the learner lands. It now names the
  actual place: the workdir for `shell`, the connected host for a `target`
  session, the repository root for a `local` one. The `shell` message also
  reads the real `runtime.workdir` instead of assuming the default.

- **The welcome panel listed commands that could not be typed.** For a `vm`
  lab it displayed six `dsoxlab …` commands and then opened an SSH session on
  the lab host, where dsoxlab is not installed and never has been: every one
  of them answered `command not found`. The panel now names the host it is
  about to connect to and states that those commands live on the learner's
  own machine, behind `exit`. For a `local` session it names the lab
  directory the mission paths are relative to, and points to `dsoxlab
  challenge` as the starting point.

- **Machine-readable output**: `--json` on `list-labs`, `progress`, `check` and
  `status`. Each document carries a `schema` version, and standard output holds
  nothing but JSON — the ambient messages, the pytest progress bar and the
  active-context notice are all silenced in that mode.

  This is what any integration needs: an editor extension, a dashboard or a
  tracking script would otherwise have to parse the Rich output, whose tables,
  colours and line wrapping depend on the terminal width and are meant to keep
  changing.

## [0.1.20] - 2026-07-20

### Fixed

- **`lvm2` is missing from the AlmaLinux 9 cloud image**, and every storage lab
  failed on `Failed to find required executable "vgs"` — not at mount time, but at
  the very first LVM module call. The template's comment claimed "lvm2, parted and
  xfsprogs ship in the AlmaLinux Cloud image": true on 10, false on 9. It now states
  what was actually verified on 9.8, and installs `lvm2` explicitly. Measured on a
  lab catalogue: **78 test errors** traced back to this single package.

- **`cloud-init status --wait` was run without privileges**, so it exited
  `PermissionError: /run/cloud-init/cloud.cfg` (rc=1) on AlmaLinux 9. The trailing
  `|| true` swallowed that failure, so `wait_for_hosts_ready` returned *before*
  cloud-init had finished while appearing to have waited for it. Now `sudo -n`,
  which returns rc=0. `-n` keeps it non-interactive: a host where sudo asked for a
  password would hang instead of failing.

## [0.1.19] - 2026-07-20

### Fixed

- **cloud-init ended in `status: error` on every KVM node, and `dsoxlab provision`
  hung on its readiness wait.** The runcmd ran `systemctl enable --now
  qemu-guest-agent`, but that unit declares
  `BindsTo=dev-virtio\x2dports-org.qemu.guest_agent.0.device` and the KVM provider
  deliberately declares **no virtio channel** (see the note in
  `templates/terraform/kvm/main.tf`: the libvirt provider's schema made it
  impractical). The device therefore never appears: `--now` waited **90 seconds
  per node**, failed, and the runcmd script exited 1 — which cloud-init reports as
  a failed `scripts_user` module.

  The node was fully functional throughout (accounts created, packages installed,
  sshd and firewalld enabled), so the symptom was purely a provisioning that never
  returned. Dropping `--now` keeps the unit enabled for the day a channel exists,
  and the command now returns in **0 s instead of 90**.

## [0.1.18] - 2026-07-20

> **0.1.17 was never released.** Its tag landed on the 0.1.16 commit, so the
> GitHub Release `v0.1.17` carries `dsoxlab-0.1.16` artifacts and PyPI stayed on
> 0.1.16. The fix below, announced for 0.1.17, ships in this version instead.

### Fixed

- **`alma9` and `ubuntu22` were declared but unusable on the `kvm` provider.** Both
  appear in the Terraform `distro_to_template` map, so a lab repository could
  legitimately write `distro: alma9` in its `meta.yml` — but neither had an entry in
  `default_image_urls`. The `coalesce()` that resolves the image then had nothing to
  fall back on and the plan failed, unless the repository happened to override
  `providers.kvm.image_url_<distro>` by hand.

  Both now ship their upstream cloud image, like the distributions already listed.
  Every distribution the provider maps has a URL again; the `incus` provider already
  handled `alma9` (`images:almalinux/9/cloud`), and `outscale` legitimately expects a
  pinned OMI from the repository.

  This matters for RHCE training in particular: the EX294 exam runs on RHEL 9, so a
  catalogue targeting it needs `alma9` to work out of the box.

## [0.1.16] - 2026-07-20

### Added

- **`dsoxlab guide [<id>]` opens a lab's online course in your web browser.** The
  course is not bundled in the lab repository: each lab declares a `doc_url`
  pointing at the trainer's site. Opening the real page, rather than fetching its
  content, keeps it rendered exactly as published (images, code blocks, navigation)
  and avoids tracking a third-party site's HTML structure. `--print` writes the URL
  instead of opening a browser, which is what you want over SSH, where
  `webbrowser` has nothing to open.

- **`guide_url()` in the new `services/guide_service.py`**, a pure function that
  composes the URL and opens nothing. It appends campaign parameters
  (`utm_source=dsoxlab`, `utm_medium=lab`, `utm_campaign=<lab_id>`) so a trainer can
  tell which labs actually drive readers to which guides.

  This marking is necessary, not decorative: a link followed from a local interface
  carries `http://localhost:<port>` as referrer at best, nothing at all at worst, so
  those reads would otherwise be indistinguishable from direct traffic. Existing
  query parameters and `#anchors` are preserved, so a lab can point at a precise
  section of a guide. `source` and `medium` are overridable, letting a future web
  front-end distinguish itself from the CLI.

## [0.1.15] - 2026-07-20

### Added

- **`services/progress_service.py`**: `build_progress()`, `next_pending_lab()` and
  `pedagogical_sort_key()` expose a learner's progression as typed data
  (`BlocProgress`) rather than as terminal markup.
- **`evaluate_lab()` and `compute_score()`** in `services/lab_service.py`: scoring a
  run and recording it is now a single service call returning a `ScoreResult`.
- **`SessionSpec` and `Runtime.session_spec()`**: a runtime can now *describe* its
  interactive session instead of opening it, and `lab_session_spec()` exposes it as
  a service. `SessionSpec.display()` renders the command as a learner would type it,
  quoting included.

  `open_session()` calls `subprocess.call`, which seizes the current terminal. That
  made two things impossible: showing the command instead of running it, and letting
  an interface that cannot yield its TTY choose how to attach. Execution now lives in
  a single place (`BaseRuntime.open_session`), and each runtime only describes.

### Fixed

- **`dsoxlab ssh`, `dsoxlab status` and the VM interactive session still connected as
  `student`.** Version 0.1.14 moved the inventory and the generated `ssh_config` to
  the `ansible` service account but left `student@` hardcoded in three places, so
  those commands and the generated `ssh_config` disagreed about who connects. On a
  lab that restricts `AllowUsers` to the automation account, `dsoxlab ssh` was
  locked out of the node it had just provisioned. The account is now read from the
  inventory (`ansible_user`) in all three, so there is no hardcoded account left in
  the package.

### Changed

- **Business logic no longer lives in the presentation layer.** The scoring formula
  sat in `cli.py` (`_run_check`), interleaved with `typer.Exit` and console output,
  and the progression aggregation sat inside `reporting/console.py`, emitting Rich
  markup as it computed. Both were therefore unreachable from anywhere else and
  untestable without capturing terminal output: any second front-end would have had
  to reimplement the score formula and the "what comes next" rule.

  They are now plain functions over plain data. `print_progress_table()` only
  renders, the `next` command only presents, and the rules they encode are covered
  by unit tests (14 new tests, including the one that matters most: a hint lowers
  the ceiling, it is not subtracted from the final score).

  No behaviour change: same scores, same ordering, same rendering, verified against
  both `ansible-training` and `linux-dsoxlab-training`.

## [0.1.14] - 2026-07-20

### Added

- **A dedicated `ansible` service account on every provisioned node.** The
  cloud-init templates (AlmaLinux and Ubuntu) now create an `ansible` account
  next to the human `student` account, with the same hardening: SSH key only, no
  login password, membership of `wheel`/`sudo`, and `sudo NOPASSWD:ALL`.

  Separating the *service* account automation uses from the *human* account is
  the standard practice: it keeps audit trails meaningful and lets either account
  be revoked without locking the other one out. `student` remains the human
  account on the control node; `ansible` is what dsoxlab and the lab playbooks
  connect as. The blanket `NOPASSWD:ALL` is deliberate, since the account drives
  general-purpose automation (dnf, systemd, LVM, SELinux, firewalld): the safety
  comes from the account being dedicated, not from narrowing its sudo rules.

- **Packages missing from the AlmaLinux minimal cloud image.** `firewalld` is not
  shipped in the AlmaLinux 10 cloud image, so `systemctl enable --now firewalld`
  targeted a unit that did not exist and every firewall lab failed. Added with it:

  - `python3-firewall`, required by the `ansible.posix.firewalld` module, which
    otherwise fails with *Failed to import the required Python library (firewall)*.
  - `policycoreutils-python-utils`, which provides `semanage`, the reference RHCSA
    tool for SELinux port and context management.

  These are Ansible *execution prerequisites*: they belong in the base image, so
  that every managed node is Ansible-ready without a per-lab bootstrap step.

### Changed

- **BREAKING: the default SSH account is now `ansible`, not `student`.**
  `build_inventory()` and `write_ssh_config()` default `ssh_user` to `ansible`,
  so the generated inventory and `ssh_config` connect as the service account.

### Migration

Nodes provisioned before 0.1.14 have no `ansible` account and become unreachable
under the new default. Re-provision them:

```console
dsoxlab destroy && dsoxlab provision
```

In lab repositories, anything that restricts the connection (`AllowUsers`,
`remote_user`, `ansible_user`) must now target `ansible`, never `student`.
Pointing it at `student` locks automation out of the node.

## [0.1.13] - 2026-07-17

### Changed

- **Licence : CC BY 4.0 → Apache-2.0.** Creative Commons
  [advises against its licences for software](https://creativecommons.org/faq/#can-i-apply-a-creative-commons-license-to-software):
  they carry no patent grant, their terms are written for creative works rather
  than code, and PyPI could only mark the package as `Other/NOASSERTION`. For a
  CLI published on PyPI and imported by third-party lab repositories, that left
  real legal ambiguity for users.

  **Apache-2.0 is the closest software licence to the previous terms.** It keeps
  both obligations CC BY 4.0 imposed — give credit, and state whether you changed
  the files (§4.b) — and adds the express patent grant CC BY 4.0 lacks.
  Attribution now lives in the [NOTICE](./NOTICE) file, which §4.d requires
  derivative works to carry.

  **Releases up to and including 0.1.12 remain under CC BY 4.0**: that grant is
  irrevocable for anyone who received them. Only 0.1.13 onwards is Apache-2.0.

## [0.1.12] - 2026-07-17

### Fixed

- **The build provenance no longer attests a file that is not published.**
  `uv build` drops a one-byte `dist/.gitignore`, and `attest-build-provenance`
  globs dotfiles (unlike the shell glob feeding `gh release create`), so the
  v0.1.11 attestation listed `.gitignore` next to the wheel and the sdist. The
  artifacts are now named explicitly. Harmless in itself, but an attestation
  should name exactly what is published, nothing more.

## [0.1.11] - 2026-07-17

### Fixed

- **A malformed `lab.yaml` or `meta.yml` could crash the CLI instead of being
  skipped.** `discovery/scanner.py` catches `(KeyError, ValueError,
  yaml.YAMLError)` and ignores the offending lab with a warning — but the
  parsers could raise outside that contract, and the exception then surfaced as
  a raw traceback on an unrelated command (`list-labs`, `progress`…). Since a
  `lab.yaml` comes from a *lab-provider repository*, this is the engine's
  untrusted input. Five cases, all found by the new fuzz harnesses:
  - an **empty** `lab.yaml` (or one holding only comments) → `AttributeError`,
    because `yaml.safe_load` returns `None`;
  - a document whose **root is a list or a scalar**, in either file;
  - **`runtime: vm`** written instead of the `runtime:` block, and
    `runtime.targets: true` → `AttributeError` / `TypeError`;
  - **`infra.hosts:` written as a mapping** instead of a list → `TypeError` on
    `h["name"]`, the iteration walking the keys;
  - a **present-but-empty key** such as `vcpu:` or `bloc:` → `int(None)` raises
    `TypeError`, because `.get("vcpu", 1)` returns `None` rather than the
    default when the key exists.

  Every one of these now raises `ValueError` with the file path and the
  offending field, so the lab is skipped and the rest of the catalogue still
  loads. An empty `ip:` no longer yields the literal string `"None"` either.

### Added

- **Fuzz harnesses over the untrusted-YAML contract** (`fuzz/`), run as a short
  regression in CI. They assert the *contract* — any exception outside
  `(KeyError, ValueError, yaml.YAMLError)` fails the run — rather than merely
  executing the parsers. Ships a seed corpus and a libFuzzer dictionary of the
  contract's keywords; `uv sync --group fuzz` installs atheris (kept out of the
  `dev` group).
- **`actionlint` and `poutine` as CI gates**, alongside the existing zizmor job,
  both installed from a release binary whose SHA-256 is verified against the
  published checksums. `poutine --fail-on-violation` makes it a gate, not a
  report. The heavier jobs now wait on all three scanners.
- **`step-security/harden-runner`** as the first step of every job
  (`egress-policy: audit`), and `.poutine.yml` acknowledging three hand-vetted
  actions per purl rather than disabling the rule.
- **Build provenance attached to the GitHub Release** as
  `provenance.intoto.jsonl`. The existing attestation is recorded on GitHub's
  attestation API, which is a *different* artifact from the release asset that
  OpenSSF Scorecard's Signed-Releases control looks for.

## [0.1.10] - 2026-07-16

### Fixed

- **Scores were wrong on labs whose data contains "ERROR", "PASSED" or
  "FAILED"**: `_parse_counts()` counted occurrences of those words in pytest's
  raw output, including inside assertion messages. A lab that filters `ERROR`
  lines (`l1-get-help`, `l1-grep-regex`, `l1-redirections-pipes`,
  `l3-service-diagnose`…) inflated its own total — `dsoxlab check` reported
  `1/5` for a 4-test lab, so the learner's score was under-counted (20 pts
  instead of 25). The summary line pytest produces itself is now the source of
  truth, with a node-id-anchored fallback.

## [0.1.9] - 2026-07-16

### Fixed

- **KVM: two lab repositories can no longer fight over the same base volume.**
  The libvirt base image was named `dsoxlab-base-<distro>.qcow2`, without the
  repository id — but the libvirt pool is *shared* across repositories while
  each repository keeps its **own** Terraform state. So the second repository to
  provision on a distro already used by another failed with
  `storage volume 'dsoxlab-base-alma10.qcow2' exists already`: its state simply
  did not know about the volume the first one had created. Concretely,
  `linux-dsoxlab-training` (alma10) blocked `ansible-training` (alma10) on the
  same host. The volume is now `dsoxlab-base-<repo-id>-<distro>.qcow2`, so lab
  catalogs really do cohabit, as the contract promises with their separate
  libvirt networks. The cloud image is duplicated per repository (sparse, ~600 MB
  to 2 GB) — the price of isolation.

  Terraform gets a new `repo_id` variable, declared by the three providers
  (`kvm`, `incus`, `outscale`) since the tfvars are shared; only `kvm` creates a
  local volume, so only it was affected. Incus pulls public image aliases and
  Outscale uses AMIs: neither could collide.

  **Upgrade impact.** On a repository provisioned with ≤ 0.1.8, the next
  `dsoxlab provision` renames the base volume, which Terraform treats as a
  *replacement*: the VMs get recreated. Nothing is lost — lab VMs are meant to
  be disposable and the learner's work lives in the repository
  (`challenge/`), never on the VM — but any in-progress lab state on the VMs
  goes away. Run `dsoxlab destroy` then `dsoxlab provision` for a clean cycle.

## [0.1.8] - 2026-07-16

### Fixed

- **No more Python traceback when the infrastructure is not provisioned**: a
  learner running a VM lab before `dsoxlab provision` (first run, or after a
  `destroy`) got a raw `ValueError: target_fqdn '...' is not in the list of
  known hosts: []`. This is a normal situation, not a bug — `build_inventory()`
  now raises `InfraNotProvisioned`, rendered by the CLI as one actionable
  sentence (EN+FR) telling the learner to run `dsoxlab provision`. A `main()`
  entry point catches it for every command, so no command can surface a
  traceback for it.
- **`check` no longer records a 0/100 when there is no infrastructure**: pytest
  runs in a subprocess, so the missing-host error could not reach the CLI — the
  run was scored as a learner failure and saved to their history. `check`/
  `submit` now verify the inventory before scoring, and exit without recording.

## [0.1.7] - 2026-07-16

### Added

- **Multi-distro labs are now real**: `check`/`submit` accept `--target/-t` and
  export the resolved target's FQDN to the tests via `DSOXLAB_TARGET_HOST`.
  Until now `runtime.targets[]` was declarative only — a lab could declare an
  Ubuntu target while its tests hard-coded the RHEL host, so selecting Ubuntu
  changed nothing and the contract lied. Tests now ask for the chosen host
  (`lab_target_host()` helper in the repo's `conftest.py`), so one lab can be
  genuinely validated on several distributions.

### Fixed

- **A typo in `--target` no longer records a 0/100**: an unknown explicit
  target is now an error (`unknown_target`, EN+FR) raised before the tests run,
  instead of a failed check saved to the learner's history.
- **A session target no longer breaks labs that don't declare it**: the
  `active_target` persisted by `use --target` is applied only to labs that
  actually declare it; shell and single-target labs silently ignore it.

## [0.1.6] - 2026-07-16

### Fixed

- **KVM inventory after a targeted provision**: `terraform apply -target` does
  not evaluate root outputs, so KVM host IPs (libvirt DHCP) were missing and
  `dsoxlab check` failed with "Aucun host dans l'inventory" for every KVM lab.
  `apply()` now runs `terraform apply -refresh-only` after a targeted apply to
  recompute the `hosts` output map without recreating resources.

### Added

- **Provider conflict detection**: `dsoxlab provision` stops with a helpful
  message (EN + FR) when another provider (incus/KVM) still has active lab
  infrastructure — they share the lab's network name and subnet and cannot run
  at the same time.

## [0.1.5] - 2026-07-15

### Added

- **hints i18n**: the modern hint format (`text_en` / `text_fr`) now also accepts
  base64-encoded values, so hints can be both bilingual and obfuscated in the
  file. The loader tries base64 first and falls back to plain text.

### Changed

- **challenge i18n**: the localized challenge brief is resolved as
  `challenge/README.<lang>.md` (e.g. `README.fr.md`), consistent with
  `scenario.<lang>.md` and the root `README.<lang>.md` — instead of the old
  `README_FR.md` naming.

## [0.1.4] - 2026-07-15

### Fixed

- **progress**: `dsoxlab progress` now shows a clear bloc name (the meta.yml
  section title, e.g. "Fondamentaux (l1)") instead of `?`. Each lab is attached
  to its meta.yml section during discovery (`bloc` + new `bloc_name`), so the
  summary groups by real section instead of an unassigned `bloc=0`.

## [0.1.3] - 2026-07-15

### Added

- **multi-host labs**: a `runtime.targets[].roles` mapping (e.g.
  `roles: {server: alma-rhcsa-2.lab}`) lets a `vm` lab use several hosts at once.
  Each role becomes an Ansible group `lab_<role>` (alongside `lab_target`, the
  primary host where tests run), so `setup.yaml` / `solution.yaml` /
  `cleanup.yaml` can configure a server and a client without hard-coding a FQDN.
  The role hosts are validated against the provisioned inventory at run time.
  Backward compatible: no `roles` means a single-host lab as before.

## [0.1.2] - 2026-07-15

### Added

- **provision**: after `terraform apply`, `dsoxlab provision` now waits for each
  host to become truly reachable — `sshd` up, the `student` account created, and
  cloud-init finished (`cloud-init status --wait`) — before returning. This
  removes the "unreachable" (dark) failure that hit the very first `dsoxlab run`
  right after provisioning, so no manual retry is needed. A `HostReadyTimeout`
  falls back to a warning (the VM may still be booting).

### Fixed

- **version**: `__version__` is now read from the installed package metadata
  instead of a hard-coded string, so `dsoxlab --version` stays in sync with
  `pyproject.toml` (it was stuck at `0.1.0`).

## [0.1.1] - 2026-07-15

### Fixed

- **incus**: `provision --host X` no longer creates the additional disk of
  *other* hosts, and `destroy --host X` now removes that host's own additional
  disk. A `target_hosts` Terraform variable scopes the extra-volume `for_each`,
  and `host_targets` targets the host's own volume so `-target` cleans it up.
  ([#1](https://github.com/stephrobert/dsoxlab/issues/1))

## [0.1.0] - 2026-07-15

Initial public release.

### Added

- Typer-based CLI (`dsoxlab`) driving hands-on labs across multiple lab
  repositories through a declarative contract (`meta.yml` + `lab.yaml`).
- Catalog discovery that scans the current repository's `meta.yml` and every
  `lab.yaml`.
- Three runtimes: `shell`, `incus` (containers) and `kvm` (Terraform +
  libvirt), each opt-in and self-describing.
- Provisioning templates for Incus, KVM/libvirt and Outscale (Terraform HCL and
  cloud-init).
- Infrastructure-level validation with `pytest` + `pytest-testinfra`, including
  persistence-after-reboot checks.
- Scoring and progress tracking persisted in a local XDG SQLite database, with
  variable-cost hints.
- Structure and metadata validators (`dsoxlab validate-structure`).
- Environment diagnostics (`dsoxlab doctor [--fix]`).
- Bilingual (English/French) user interface driven by `DSOXLAB_LANG`.

[Unreleased]: https://github.com/stephrobert/dsoxlab/compare/v0.1.20...HEAD
[0.1.20]: https://github.com/stephrobert/dsoxlab/compare/v0.1.19...v0.1.20
[0.1.19]: https://github.com/stephrobert/dsoxlab/compare/v0.1.18...v0.1.19
[0.1.18]: https://github.com/stephrobert/dsoxlab/compare/v0.1.16...v0.1.18
[0.1.16]: https://github.com/stephrobert/dsoxlab/compare/v0.1.15...v0.1.16
[0.1.15]: https://github.com/stephrobert/dsoxlab/compare/v0.1.14...v0.1.15
[0.1.14]: https://github.com/stephrobert/dsoxlab/compare/v0.1.13...v0.1.14
[0.1.13]: https://github.com/stephrobert/dsoxlab/compare/v0.1.12...v0.1.13
[0.1.12]: https://github.com/stephrobert/dsoxlab/compare/v0.1.11...v0.1.12
[0.1.11]: https://github.com/stephrobert/dsoxlab/compare/v0.1.10...v0.1.11
[0.1.10]: https://github.com/stephrobert/dsoxlab/compare/v0.1.9...v0.1.10
[0.1.9]: https://github.com/stephrobert/dsoxlab/compare/v0.1.8...v0.1.9
[0.1.8]: https://github.com/stephrobert/dsoxlab/compare/v0.1.7...v0.1.8
[0.1.7]: https://github.com/stephrobert/dsoxlab/compare/v0.1.6...v0.1.7
[0.1.6]: https://github.com/stephrobert/dsoxlab/compare/v0.1.5...v0.1.6
[0.1.5]: https://github.com/stephrobert/dsoxlab/compare/v0.1.4...v0.1.5
[0.1.4]: https://github.com/stephrobert/dsoxlab/compare/v0.1.3...v0.1.4
[0.1.3]: https://github.com/stephrobert/dsoxlab/compare/v0.1.2...v0.1.3
[0.1.2]: https://github.com/stephrobert/dsoxlab/compare/v0.1.1...v0.1.2
[0.1.1]: https://github.com/stephrobert/dsoxlab/compare/v0.1.0...v0.1.1
[0.1.0]: https://github.com/stephrobert/dsoxlab/releases/tag/v0.1.0
