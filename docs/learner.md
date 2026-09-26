# dsoxlab for the learner

**Audience:** you want to play labs. You are not writing a catalog and you are
not running a training platform — those have [their own
pages](./README.md).

**Language:** [English](./learner.md) · [Français](./learner.fr.md)

---

## Install

Two prerequisites, and no more: **Python 3.11 or newer**, and
[`uv`](https://docs.astral.sh/uv/getting-started/installation/) or `pipx` to
install dsoxlab with. If you have neither, `uv` installs itself in one line and
needs no administrator rights.

```bash
uv tool install dsoxlab      # or: pipx install dsoxlab
dsoxlab --version
```

Nothing to clone, nothing to build. Optionally, `dsoxlab install` adds shell
completion for bash and zsh (reload your shell afterwards).

---

## Your first lab, in five minutes

You do not need a catalog to start. `dsoxlab demo` installs a one-lab
demonstration catalog whose subject is dsoxlab itself: the loop you will repeat
on every other lab.

```bash
dsoxlab demo                    # installs it and prints what to do next
cd ~/.local/share/dsoxlab/demo

dsoxlab course premiers-pas     # the lesson
dsoxlab run premiers-pas        # drops you into the lab's work directory
dsoxlab challenge premiers-pas  # the mission
dsoxlab check premiers-pas      # the tests, and the score
```

No VM, no container, no Docker: it runs anywhere dsoxlab runs.

---

## Then, a real catalog

Labs live in their own repositories, published separately from the engine.
Install one by name — the tool knows `linux`, `ansible` and `terraform` — or by
any git URL. `catalog add` clones it under
`~/.local/share/dsoxlab/catalogs/` and makes it the **active** catalog, the one
dsoxlab serves when you are not standing in a catalog directory. A plain
`git clone` works too, and then the catalog you are in is the one it serves.

```bash
dsoxlab catalog add linux       # or a git URL, or: git clone … && cd …
dsoxlab doctor                  # what this catalog needs, and what is missing
dsoxlab list-labs
dsoxlab show <lab-id>
dsoxlab start <lab-id>          # context, prerequisites, infrastructure, session
```

`start` is the command to learn first. A lab needs steps in an order nothing
tells you — set the context, check the prerequisites, bring machines up when
the lab needs some, prepare and open the session — and `start` plays them
**announcing each one with the single command that replays it alone**. When a
step fails, the message names it and its command, and nothing beyond it is
attempted: you are never left guessing which of `use`, `doctor`, `provision`
or `run` you skipped.

`dsoxlab doctor` only reports what *this* catalog needs: a catalog made of
shell labs never asks for a hypervisor. `dsoxlab doctor --fix` repairs what can
be repaired safely.

### What a `vm` lab needs from your machine

Two kinds of labs, and only the first is free. A **`shell`** lab runs in a
directory on your own machine: the demonstration lab is one, and so is every
lab of the Terraform catalog. A **`vm`** lab starts real virtual machines next
to you — 66 of the Linux catalog's 86 labs do — and for that your machine has
to be able to run them:

- **Linux, with KVM.** The packaged hypervisors are KVM/libvirt and Incus, and
  neither exists on Windows or macOS: there, `vm` labs mean
  [the appliance](./appliance.md). Inside a virtual machine they also need
  nested virtualization, which is enabled on the host and not in the guest.
- **libvirt and QEMU.** `dsoxlab doctor --fix` installs them where the remedy
  is an `apt install`, the only package manager the remedies know today, and
  adds you to the `kvm` group — which takes effect at your next login.
- **Terraform.** `doctor` names it and links its install page but cannot
  install it: HashiCorp ships it through its own repository. Ansible needs
  nothing, it comes with dsoxlab.
- **An SSH key pair for the catalog**, from `dsoxlab instructor bootstrap`. The
  name says instructor; run it anyway. A catalog you clone carries no key — its
  `.gitignore` excludes the whole `ssh/` directory, since a private key has no
  business in a repository — and `provision` refuses to start without one.

None of this is guesswork: `dsoxlab doctor` sorts it into what this catalog
requires and what is merely informational, and says what to do about each.

---

## The loop

| Step | Command | What it does |
| --- | --- | --- |
| 1 | `dsoxlab list-labs` | Browse the catalog. `--section`, `--level`, `--type`, `--bloc` narrow it down |
| 2 | `dsoxlab use <section>/<level>` | Pin an active context, so the next commands stop asking |
| 3 | `dsoxlab show <id>` | Skills, runtime, estimated time, status |
| 4 | `dsoxlab course <id>` | The lesson, one section at a time when the lab declares them |
| 5 | `dsoxlab run <id>` | Prepare the environment and open a session in it |
| 6 | `dsoxlab challenge <id>` | The mission you have to accomplish |
| 7 | `dsoxlab hint <id>` | The next hint, at a cost in points |
| 8 | `dsoxlab check <id>` | Run the tests, compute the score, record it |
| 9 | `dsoxlab submit <id>` | Same, then close the session for good |
| 10 | `dsoxlab reset <id>` / `clean <id>` | Start over, or tear the environment down |

Once a lab is active in the session, the id becomes optional: `dsoxlab check`
knows which lab you are in.

`dsoxlab next` recommends what to do next in the active context, `dsoxlab
progress` shows where you stand bloc by bloc, and `dsoxlab scores` lists your
history.

### What `run` actually opens

A `shell` lab hands you a sub-shell in the lab's work directory, on your own
machine. A `vm` lab provisions or reuses the machines the catalog declares and
opens an SSH session on the target. Either way you leave it by typing `exit`,
and `dsoxlab check` works from inside that session as well as from outside.

---

## Reading the course

Two commands, two different things:

- **`dsoxlab course`** shows the lesson shipped with the lab, in the terminal.
- **`dsoxlab guide`** opens the lab's online guide in a browser tab, so it
  renders exactly as published, with its images and navigation. `--print`
  prints the URL instead, which is what you want over SSH.

Both `course` and `challenge` go through a pager as soon as their output is
taller than the terminal, so a long course stays readable without depending on
the scrollback. Pipes and redirections are never paged: they receive the full
text.

```bash
DSOXLAB_PAGER='bat --plain' dsoxlab course   # pick your pager (default: less -R)
dsoxlab course --no-pager                    # dump everything at once
dsoxlab course > course.txt                  # never paged: plain text
```

---

## Your score

The score starts at **100** — or at whatever total the lab's
`challenge/hints.yaml` declares — and every hint you take costs points. `check`
computes the final score, records it, and `scores` shows the history.

A lab that declares `exam_passing_score` is an exam: `submit` renders a
**pass or fail verdict** against that mark, expressed as a percentage of the
lab's own total.

Tests read the **state of the system**, not the commands you typed. There is no
credit for having run the right command, and no penalty for reaching the same
state another way.

---

## Language

Every message exists in English and French.

```bash
DSOXLAB_LANG=fr dsoxlab list-labs     # for one call
dsoxlab use linux --lang fr           # persistently, for this catalog
```

Priority: `DSOXLAB_LANG` > the catalog's context file > the system `LANG` > `en`.

---

## Where your progress lives

In the catalog itself: `<catalog>/.dsoxlab.db` for scores and hints,
`<catalog>/.dsoxlab-context.json` for the active context. Progress is therefore
**per catalog**, and copying the catalog directory copies your history with it.
The full list of locations is on [Where dsoxlab writes](./files.md).

---

## When something goes wrong

- **`dsoxlab doctor`** says what this catalog needs and what is missing, in two
  tables: what blocks you here, and what is merely informational.
- **`dsoxlab support`** produces an anonymised diagnostic report, ready to paste
  into an issue (no personal path, no public address). `--json` for the same
  content as a machine document.
- **The log is always written**, whatever the verbosity, to
  `~/.local/state/dsoxlab/dsoxlab.log`. There is no need to replay a command to
  find out what it did. `-v`, `-vv` and `--debug` only change what reaches your
  terminal.

Four exit codes are worth recognising:

| Code | Meaning |
| --- | --- |
| `1` | The command ran, and the answer is no: a failing test, an unknown lab id. It is about your work, not your setup |
| `2` | The command could not run: no infrastructure yet, a fixture missing from the lab. Something has to be prepared, and the message says what |
| `7` | Another dsoxlab command is already writing in this catalog. The message names it. Wait for it, or close the other terminal |
| `130` | You interrupted the command (Ctrl-C). The message says how to resume |

[The full list](./exit-codes.md) matters to a script, not to you.

---

## Staying up to date

dsoxlab checks once a day whether a newer version exists on PyPI and says so at
the end of a command, on standard error. Offline, it stays silent.

```bash
uv tool upgrade dsoxlab            # or: pipx upgrade dsoxlab
DSOXLAB_NO_UPDATE_CHECK=1 …        # silence the check
```

---

## Going further

- [Every command, generated from the CLI itself](./commands.md)
- [Where dsoxlab writes](./files.md)
- [Writing your own catalog](./catalog-author.md)
- [Running the machines a `vm` lab needs](./trainer.md)
- [The appliance](./appliance.md), if installing the tool is not an option
