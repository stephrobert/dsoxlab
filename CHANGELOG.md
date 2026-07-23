# Changelog

**Language:** [English](./CHANGELOG.md) · [Français](./CHANGELOG.fr.md)

All notable changes to this project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

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
