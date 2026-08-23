# dsoxlab for the learner

**Audience:** you want to play labs. You are not writing a catalog and you are
not running a training platform — those have [their own
pages](./README.md).

**Language:** [English](./learner.md) · [Français](./learner.fr.md)

---

## Install

Python 3.11 or newer, and that is the whole prerequisite.

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
Clone one, then run `dsoxlab` from inside it — the catalog you are in is the
catalog dsoxlab serves.

```bash
git clone https://github.com/stephrobert/linux-dsoxlab-training.git
cd linux-dsoxlab-training

dsoxlab doctor                  # what this catalog needs, and what is missing
dsoxlab list-labs
dsoxlab show <lab-id>
dsoxlab run <lab-id>
```

`dsoxlab doctor` only reports what *this* catalog needs: a catalog made of
shell labs never asks for a hypervisor. `dsoxlab doctor --fix` repairs what can
be repaired safely.

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

Two exit codes are worth recognising:

| Code | Meaning |
| --- | --- |
| `7` | Another dsoxlab command is already writing in this catalog. The message names it. Wait for it, or close the other terminal |
| `130` | You interrupted the command (Ctrl-C). The message says how to resume |

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
