# dsoxlab documentation

**Audience:** this page is a switchboard, and belongs to no one in particular.
Every other page names its reader in its first lines, because a document that
answers three people at once answers none of them.

**Language:** [English](./README.md) · [Français](./README.fr.md)

`dsoxlab` turns declarative exercises into reproducible, runnable and verifiable
lab environments. The [repository README](../README.md) says what it is in
thirty seconds; these pages say how it works.

---

## The three doors

| Page | For you if… |
| --- | --- |
| **[For the learner](./learner.md)** | You install dsoxlab, play labs and want to understand your score |
| **[For the catalog author](./catalog-author.md)** | You write labs in your own repository |
| **[For the trainer](./trainer.md)** | You run the machines and providers the labs need |

## References

| Page | Content |
| --- | --- |
| [The v1 contract](./contract-v1.md) | `meta.yml` and `lab.yaml`, field by field, with what version 1 guarantees |
| [Command reference](./commands.md) | Every command, generated from the CLI itself |
| [Where dsoxlab writes](./files.md) | Every file dsoxlab creates, and the environment variables it reads |
| [The mark](./brand.md) | Name, logo and their usage terms |

Contributors have [CONTRIBUTING.md](../CONTRIBUTING.md): setup, quality gates,
architecture map and commit conventions.

---

## Two habits worth borrowing

**Nothing here is written twice.** The command table is generated from the CLI,
and the file locations are checked against the code by
`tests/test_documentation_synchrone.py`, which derives them by calling the same
functions the CLI calls. Both controls exist because both had already drifted:
the command table described a `cleanup.sh` the contract forbids, and the
persistence section pointed at a database that never existed.

**These pages are Markdown in the repository, deliberately.** There is no site
generator here, so the documentation is read where it is written, versioned with
the code that it describes, and reviewed in the same pull request.
