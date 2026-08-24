# The machine output

**Audience:** you are writing something that *reads* dsoxlab — an editor
extension, a dashboard, a CI step, a grading script. This page is the contract
you may build on, and the only part of the output that is meant to be parsed.

**Language:** [English](./machine-output.md) · [Français](./machine-output.fr.md)

Everything else dsoxlab prints is for eyes: Rich tables whose width follows the
terminal, colours, progress bars. It is *made* to move. `--json` gives you a
document instead, and this page says what is in it.

---

## Three rules

**1. Standard output carries the document, and nothing else.** In `--json` mode
the context banner, the tips and the update notice all go to standard error. So
`json.loads(stdout)` works without stripping anything, and that is exactly how
the test suite asserts it — a message slipped in front of the document, or a
progress bar left behind it, makes it raise.

**2. Every document carries a `schema`.** It is the first field, and it tells a
consumer whether it speaks the same language before reading the rest. The
current value is **1**.

**3. A verdict is read from a key and a state, never from a label.** Checks and
issues carry a stable identifier (`key`) and, where there is a verdict, a state
token (`ok`, `failed`, `choice_required`). The translated label sits *beside*
them, for display. No integration should ever have to parse English or French
to know whether something is green or red.

And one consequence worth stating on its own: **`--json` changes the shape of
the output, never the verdict nor the exit code.** `check` on a failing lab
exits 1 with or without it; `validate-structure` exits 1 as soon as one lab
fails; `doctor` exits 0 either way and puts its verdict in `ok`
(it is `--strict`, not `--json`, that turns it into an exit code). On a *hard*
error — an unknown lab id, an unreadable `meta.yml` — standard output stays
empty, the reason goes to standard error, and the exit code is unchanged. Read
the exit code first.

---

## The commands that take `--json`

| Command | Document | Exit codes |
| --- | --- | --- |
| `dsoxlab list-labs` | the catalog | 0 |
| `dsoxlab show <id>` | one lab and its runtime status | 0, or 1 if the id is unknown (no document) |
| `dsoxlab progress` | the catalog plus a progression summary | 0 |
| `dsoxlab next` | the suggested lab and what remains | 0, or 1 with no active context (no document) |
| `dsoxlab scores` | the score history and exam verdicts | 0 |
| `dsoxlab check <id>` | the test result and the score | 0, or 1 when the lab fails (document still printed) |
| `dsoxlab status` | SSH reachability of the declared hosts | 0, or 1 when a declared host does not answer (document still printed) |
| `dsoxlab doctor` | the environment diagnosis | 0, always — the verdict is in `ok`. With `--strict`, 9 (a required check fails) or 10 (a required check could not be measured) |
| `dsoxlab validate-structure` | every contract issue found | 0, or 1 as soon as one lab fails (document still printed) |
| `dsoxlab support` | the anonymised diagnostic report | 0 |

`doctor --json --fix` is refused, and says so on standard error: the remediation
commands write to standard output, which would leave the document unreadable.
Read the diagnosis first, act on it second.

---

## The lab object

Five documents (`list-labs`, `show`, `progress`, `next` and `check`) embed the
same lab object. It is described once here.

| Field | Type | Meaning |
| --- | --- | --- |
| `id` | string | the lab identifier, unique in the catalog, and the key every command takes |
| `title` | string | display title, in the catalog language |
| `section` | string | the section it belongs to, defaulting to `repo.category` |
| `bloc` | int or null | the teaching block, derived from the position in `meta.yml` |
| `bloc_order` | int or null | the rank inside that block — `next` follows this order |
| `level` | string | free-form level (`l1`, `rhcsa`, …) |
| `type` | string | `lab`, `challenge` or `capstone` |
| `exam_passing_score` | int or null | pass mark, as a percentage of the scale. `null` on an ordinary lab |
| `difficulty` | string or null | free-form, never validated |
| `estimated_time` | string or null | free-form, e.g. `"30m"` |
| `skills` | array of strings | never empty; the validator requires it |
| `distros` | array of strings | never empty; same |
| `doc_url` | string | the online guide, `http` or `https` |
| `path` | string | **absolute** path of the lab directory, so an editor can open its files |
| `runtime.type` | string | `shell` or `vm` |
| `runtime.session` | string | `target` or `local` |
| `runtime.target` | string or null | the resolved target host, `null` on a `shell` lab |
| `runtime.workdir` | string | working directory, relative to `path` |
| `best_score` | object or null | `{"points": int, "max": int}`, or `null` when the lab was **never attempted** |

`best_score: null` is not a zero. A lab that has never been played and a lab
played and failed are different states, and an interface that merges them tells
the learner something false.

---

## `list-labs`

```json
{
  "schema": 1,
  "labs": [ { "id": "l1-first-terminal", "…": "…" } ],
  "count": 20
}
```

| Field | Type | Meaning |
| --- | --- | --- |
| `labs` | array of lab objects | filtered by the options and by the active context |
| `count` | int | the size of `labs`, so a consumer need not compute it |

## `show`

```json
{
  "schema": 1,
  "lab": { "id": "l1-first-terminal", "…": "…" },
  "status": "ready"
}
```

| Field | Type | Meaning |
| --- | --- | --- |
| `lab` | lab object | including its `best_score` |
| `status` | string or null | `ready`, `stopped`, or `null` when the runtime cannot answer |

`status` is a token, not a sentence: it does not follow the display language.

## `progress`

```json
{
  "schema": 1,
  "labs": [ { "…": "…" } ],
  "summary": { "total": 84, "attempted": 12, "points": 940, "max_points": 1200 }
}
```

| Field | Type | Meaning |
| --- | --- | --- |
| `labs` | array of lab objects | sorted by `bloc`, then `bloc_order`, then `id` |
| `summary.total` | int | labs in scope |
| `summary.attempted` | int | labs with at least one recorded result |
| `summary.points` | int | points obtained, summed over the attempted labs only |
| `summary.max_points` | int | the scale of those same labs |

## `next`

```json
{
  "schema": 1,
  "context": { "section": "l1", "level": null },
  "next": { "id": "l1-first-terminal", "…": "…" },
  "all_done": false,
  "remaining": 12
}
```

| Field | Type | Meaning |
| --- | --- | --- |
| `context.section` | string | the active section — `next` needs one, and exits 1 without |
| `context.level` | string or null | the active level, when one is set |
| `next` | lab object or null | the first lab with no recorded result, in teaching order |
| `all_done` | bool | true only when the section holds labs and every one has a result |
| `remaining` | int | labs with no recorded result at all |

`all_done` and `next: null` are not the same statement: an empty section also
yields `next: null`, and a consumer that congratulated the learner on it would
be celebrating a course that never started.

## `scores`

```json
{
  "schema": 1,
  "results": [
    {
      "lab_id": "aws-provider-aws-first-ec2",
      "section": "aws",
      "score": 100,
      "max_score": 100,
      "passed_tests": 11,
      "total_tests": 11,
      "hints_used": 0,
      "validated_at": "2026-08-13T13:30:12.831759+00:00",
      "exam": null
    }
  ],
  "count": 1
}
```

| Field | Type | Meaning |
| --- | --- | --- |
| `results` | array | most recent first, capped by `--top` |
| `results[].score` / `max_score` | int | the recorded mark and its scale |
| `results[].passed_tests` / `total_tests` | int | what pytest reported |
| `results[].hints_used` | int | hints taken, which is what lowered the score |
| `results[].validated_at` | string | ISO 8601, UTC |
| `results[].exam` | object or null | `null` on an ordinary lab; otherwise `{"passing_score", "percentage", "passed"}` |

`exam: null` means *not an exam*, and it is deliberately not `false`: an
ordinary lab is not a failed exam. The comparison behind `passed` is done in
integers, never on a rounded percentage — a pass mark does not round in the
candidate's favour.

## `check`

```json
{
  "schema": 1,
  "lab": { "id": "premiers-pas", "…": "…" },
  "check": {
    "ok": true,
    "passed": 3,
    "total": 3,
    "score": 100,
    "max_score": 100,
    "output": "=== test session starts ===\n…"
  }
}
```

| Field | Type | Meaning |
| --- | --- | --- |
| `check.ok` | bool | every test passed |
| `check.passed` / `total` | int | tests passed, tests run |
| `check.score` / `max_score` | int | the mark recorded in the catalog database |
| `check.output` | string | pytest's raw output, where the detail of a failure lives |

The command exits 1 when `ok` is false, and still prints the document.

## `status`

The state of the active lab, or of the one you name.

```json
{
  "schema": 1,
  "lab": "l2-swap-management",
  "state": "in_progress",
  "label": "in progress",
  "detail": "Work started in /path/challenge/work",
  "best_score": null,
  "max_score": null
}
```

| Field | Type | Meaning |
| --- | --- | --- |
| `lab` | string or null | the lab id; `null` when no lab is active |
| `state` | string or null | a **stable token**, see the table below |
| `label` | string | the same state, translated, for eyes |
| `detail` | string | what was observed, and the gesture that follows |
| `best_score` / `max_score` | integer or null | the best score obtained, if any |

| `state` | What it means |
| --- | --- |
| `not_started` | nothing is prepared for this lab |
| `ready` | the environment is prepared, and untouched |
| `in_progress` | work has started |
| `validated` | a score has been obtained |
| `degraded` | a declared service no longer runs: the lab cannot be played as is |

`state` and `label` are separate on purpose. An integration filtering on
"validated" must not depend on the language of whoever ran the command: the
token does not move, the label follows `DSOXLAB_LANG`.

`ready` and `in_progress` differ only by the contents of the working directory,
compared with the fingerprint `run` recorded when preparing it. On a `vm` lab
that work happens on the machine, where no local fingerprint would see it: the
state is `in_progress` from preparation onward, and `detail` says so rather than
implying a measurement that did not happen.

## `infra status`

Was named `status` until 0.1.67.


```json
{
  "schema": 1,
  "provider": "kvm",
  "hypervisor": { "queryable": true, "error": null },
  "hosts": [
    {
      "fqdn": "alma-rhcsa-1.lab",
      "ip": "10.10.10.11",
      "reachable": false,
      "reason": "Connection timed out",
      "domain": "alma-rhcsa-1",
      "domain_state": "shut off",
      "cause": "domain_not_running"
    }
  ],
  "summary": { "reachable": 0, "total": 1 }
}
```

| Field | Type | Meaning |
| --- | --- | --- |
| `provider` | string or null | the active infra provider; `null` on a catalog with no hosts |
| `hypervisor.queryable` | bool | whether machine state could be asked of the backend |
| `hypervisor.error` | string or null | why it could not, when it could not |
| `hosts[].reachable` | bool | SSH answered |
| `hosts[].reason` | string or null | the last line of the SSH failure, when it failed |
| `hosts[].domain` / `domain_state` | string or null | what the hypervisor says, when it can be asked |
| `hosts[].cause` | string | a **stable token** naming the diagnosis, not a sentence |
| `summary.reachable` / `total` | int | hosts that answered, hosts declared |

The command exits 1 as soon as one declared host does not answer, and prints
the document anyway: that document is precisely what says which one, and why.

A catalog with no `infra:` block is a normal case, not an error: it yields
`provider: null`, `hosts: []` and a zeroed summary, and exits 0.

## `doctor`

```json
{
  "schema": 1,
  "ok": true,
  "required": [
    {
      "key": "pytest",
      "state": "ok",
      "ok": true,
      "label": "pytest",
      "detail": "bundled with dsoxlab (the one `check` uses)",
      "fix": null,
      "fix_kind": null,
      "hint": null
    }
  ],
  "informational": [
    {
      "key": "kvm",
      "state": "failed",
      "ok": false,
      "label": "virsh/KVM",
      "detail": "virsh not found",
      "fix": "sudo apt install libvirt-clients libvirt-daemon-system qemu-kvm",
      "fix_kind": "automatic",
      "hint": null
    }
  ],
  "notes": ["No lab in this catalog uses a VM: the hypervisors above are informational."]
}
```

| Field | Type | Meaning |
| --- | --- | --- |
| `ok` | bool | **the verdict**, and it covers `required` only |
| `required` | array of checks | what blocks *this* catalog |
| `informational` | array of checks | components this catalog does not need, never an error |
| `notes` | array of strings | translated sentences explaining *why* a component is informational here |

Each check:

| Field | Type | Meaning |
| --- | --- | --- |
| `key` | string | **the stable identity**: `python`, `pytest`, `shell`, `provider`, `kvm`, `incus`, `terraform`, `ansible`, `libvirt_pool`, `iso_tool`, `hw_virt`, `cpu_arch`, `resources`, `labs`, `lab_home` |
| `state` | string | `ok`, `failed`, `choice_required`, or `unknown` |
| `ok` | bool | the same thing as `state == "ok"`, kept for a plain green/red reading |
| `label` | string | the component's name, translated — for display only |
| `detail` | string | what was measured: a version, an error line, a count |
| `fix` | string or null | the remediation in its readable form; `dsoxlab doctor --fix` plays the same commands token by token, without a shell |
| `fix_kind` | string or null | the remediation category: `automatic`, `manual` (shown, never run), `needs_relogin` or `needs_reboot` (run, but the check stays red until the session or the machine restarts) |
| `hint` | string or null | a step only a human should take — an install page, a decision |

`state: choice_required` exists because a decision is not a failure: a catalog
that declares several providers and has none selected blocks provisioning, but
nothing is broken, and painting it red treats a choice like an outage.

`state: unknown` exists because an impossible probe proves nothing, in either
direction: a check whose measurement failed (an unreadable `/proc/meminfo`, a
libvirt pool that does not answer) is neither the reassuring green of an
unearned `ok` nor the accusing red of an unproven failure. Its `ok` field is
`false` — nothing was verified — but it does not count toward the top-level
verdict.

`ok` covers `required` only, deliberately. A hypervisor this catalog will never
use must not turn a perfectly healthy machine red.

`fix` and `hint` are kept apart on purpose: one is a command, the other is a
sentence. Merging them would have an automation run a documentation URL.

`fix_kind` is what an automation must read before acting on `fix`: a `manual`
remediation is never run by `--fix`, and a `needs_relogin` or `needs_reboot`
one succeeds while its check keeps reporting `failed` until the session or
the machine restarts — that is a delayed effect, not a failure.

### The exit code, and the two modes

By default `doctor` exits **0 whatever happens**: the verdict lives in `ok`.
That is the right call for a human — a diagnosis is not a failure — but it made
the command useless as a gate, since a script had to read the document to learn
whether anything was missing.

`--strict` turns the diagnosis into an exit code. It changes **nothing** else:
the table and the document are still rendered identically, before the code
lands.

| Mode | Code | When |
| --- | --- | --- |
| `doctor` | `0` | always, including when a required check fails |
| `doctor --strict` | `0` | every required check is `ok` |
| `doctor --strict` | `9` | at least one required check is `failed` or `choice_required` |
| `doctor --strict` | `10` | no failure, but at least one required check is `unknown` |

Two codes rather than one, because the two situations call for different
gestures: `9` gets repaired, `10` gets measured again. An environment whose
probe did not complete is not validated for all that — which is exactly what an
image build must not mistake for a success.

`9` wins when both coexist: a certainty outweighs an ignorance.

`--strict` combines with `--json`, and the order matters: the document goes to
standard output **before** the code is returned, exactly like
`validate-structure`. A caller receiving a non-zero code can still read what
went wrong.

## `validate-structure`

```json
{
  "schema": 1,
  "ok": false,
  "labs_checked": 87,
  "doc_urls_checked": false,
  "issues": [
    {
      "kind": "structure",
      "key": "struct_missing_file",
      "params": { "name": "test_functional.py" },
      "message": "Missing file: test_functional.py",
      "lab": "labo-tordu",
      "path": "/home/…/labs/domaine/labo-tordu/challenge/tests/test_functional.py",
      "field": null
    }
  ],
  "counts": {
    "contract": 0, "unknown_key": 1, "structure": 1,
    "content": 1, "doc_url": 0, "metadata": 3
  }
}
```

| Field | Type | Meaning |
| --- | --- | --- |
| `ok` | bool | the verdict, matching the exit code: `false` means exit 1 |
| `labs_checked` | int | labs actually discovered and validated |
| `doc_urls_checked` | bool | whether `--check-urls` was passed — without it, `doc_url: 0` means *not looked at*, not *all alive* |
| `issues` | array | every anomaly, in the order the checks run |
| `counts` | object | one entry per family, **always all of them**, zero included |

Each issue:

| Field | Type | Meaning |
| --- | --- | --- |
| `kind` | string | the family: `contract`, `unknown_key`, `structure`, `content`, `doc_url`, `metadata` |
| `key` | string | **the stable identity of the rule that fired** — filter, count and compare on this |
| `params` | object | the facts of that rule, values reduced to strings and numbers |
| `message` | string | the same thing said to a human, translated |
| `lab` | string or null | the lab id; `null` for issues found before discovery (`contract`, `unknown_key`) |
| `path` | string or null | absolute path of the file at fault |
| `field` | string or null | the metadata field at fault, on `metadata` issues only |

`counts` always carries all six families. Omitting the empty ones would leave a
dashboard unable to tell a healthy family from one this version of the tool does
not know about.

When `meta.yml` itself cannot be read, validation stops there: the document has
the same shape, `labs_checked` is 0, and the exit code is 1. The file describes
the whole catalog, so every later check would be guesswork.

## `support`

The anonymised report `dsoxlab support` prints as Markdown, as a document. Its
top-level keys are `dsoxlab`, `python`, `systeme`, `distribution`,
`architecture`, `shell`, `outils`, `catalogue`, `etat` and `journal`. It is a
diagnostic bundle meant for an issue, not a state to build a dashboard on:
personal paths and public addresses are replaced before it is printed.

---

## The evolution rule

**Adding a field keeps `schema` where it is.** A consumer that ignores unknown
fields keeps working, which is why one should. New optional data lands this way.

**Changing what a field means, renaming it, or removing it increments
`schema`.** So does changing the meaning of a `state` or `kind` token, or the
shape of a nested object. A consumer that reads `schema` first can refuse to
guess.

Two things are explicitly **not** part of the contract, and must not be parsed:

- **translated text** — `label`, `message`, `detail`, `notes`. They follow
  `DSOXLAB_LANG` and are rewritten whenever the wording improves;
- **the raw output of another tool** — `check.output` is pytest's, verbatim.

Two things that *are* part of it, and are easy to overlook:

- the **stable tokens**: `key`, `state`, `kind`, `status`, `cause`, and the
  runtime `type` and `session`. New values may appear — treat an unknown one as
  unknown, not as an error;
- the **exit codes**, which `--json` never changes.

The rules live next to the code, in `src/dsoxlab/reporting/machine.py`, and the
tests that hold them in `tests/test_json_output.py` and
`tests_e2e/test_parcours.py`. The end-to-end ones run the installed binary in a
subprocess and parse its standard output without stripping it: that is the only
way to catch a stray message printed by something other than the CLI itself.
