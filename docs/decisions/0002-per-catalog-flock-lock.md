# ADR-0002: One write lock per catalogue, a `flock` whose file is never deleted

**Status:** accepted
**Date:** 2026-08-21 (0.1.55)

**Language:** [English](./0002-per-catalog-flock-lock.md) · [Français](./0002-per-catalog-flock-lock.fr.md)

## Context

Two open terminals is the normal case for a learner. Nothing prevented two
`dsoxlab` from writing to the same state at the same time, and that state is
scattered:

- `<repo>/.dsoxlab-context.json`, rewritten **whole** by `config._persist` (two
  concurrent writes: the last one wins, the first is lost without a trace);
- the Terraform state under `~/.local/state/dsoxlab/<catalog-id>/terraform/`;
- the inventory and the `ssh_config` fragment regenerated in the cache;
- the `runtime.services` containers, named per catalogue and therefore shared.

The SQLite database `<repo>/.dsoxlab.db` was the only piece already protected,
by SQLite itself.

## Decision

**Where the lock lives, and why not in the catalogue.** Under
`~/.local/state/dsoxlab/<catalog-id>/dsoxlab.lock`, that is, at the root of this
catalogue's state directory, the very one that holds the Terraform state.
Putting it in the lab repository would have looked more natural (that is where
`.dsoxlab.db` and `.dsoxlab-context.json` live), but every provider repository
ignores those two files **by name**, not by a pattern: a third file would show
up as untracked in all of them, and three repositories would have had to change
to ship a lock.

The identity is `repo.id` when `meta.yml` is readable, otherwise the directory
name suffixed with a digest of its absolute path. Taking `repo.id` first is not
a detail: two clones of the same catalogue share the **same** Terraform
work-dir, so they must share the lock. Serializing them needlessly costs
nothing; letting them write over each other costs a corrupted state.

**A stale lock, and why there is none here.** The lock is a `flock`
(`LOCK_EX | LOCK_NB`). The kernel releases it **by itself** when the descriptor
closes, including when the process dies of a `SIGKILL`, and it obviously does
not survive a reboot. So there is no lock to "recover": the question of
recovery, which is the real difficulty of sentinel-file locks, does not arise.

What survives is the **file**, and the name of its former holder. It is
truncated on release so that it does not describe a finished invocation, and it
is **never** deleted: unlinking a lock file is the classic race where one
process removes, from under another, the inode that other process already
holds.

The lock is not inherited by subprocesses: Python creates its descriptors
non-inheritable (PEP 446), and `exec` closes them. The sub-shell opened by
`dsoxlab run` therefore holds nothing, which is essential, since the learner
types `dsoxlab check` in it.

**Who takes it.** The commands that write (as listed in
0.1.55: `run`, `check`, `submit`,
`provision`, `destroy`, `clean`, `reset`, `use`). Not the ones that read
(`list-labs`, `show`, `scores`, `progress`, `next`, `status`, `doctor`,
`course`, `challenge`, `hint`, `guide`, `validate-structure`, `support`):
consulting the catalogue while a `provision` runs in another terminal is normal
use, not a conflict.

## Consequences

- A second concurrent invocation is refused with exit code **7**, and a
  translated message names the holding command, its PID and how long it has
  been running. Code 7 is distinct so that a script chaining commands can retry
  on it and give up on the others.
- `run` hands the lock back before opening the session: a lock held "for the
  whole command" would cover the interactive sub-shell, where the learner types
  `dsoxlab check`, which would then be refused by its own session.
- On a filesystem that cannot lock (`ENOLCK`, `ENOSYS`, `EOPNOTSUPP`,
  `EINVAL`), the command runs unprotected with a warning in the log rather than
  refusing to start. A `~/.local/state` mounted on an NFS without lockd would
  otherwise make the tool unusable, a price far higher than the risk covered.
- A stale lock is never something to delete by hand, and the documentation says
  so.

## What would reverse it

State that is shared across machines (a Terraform backend or a catalogue state
outside the local disk). A `flock` only serializes processes of one kernel; at
that point the lock would have to move to wherever the shared state lives.
