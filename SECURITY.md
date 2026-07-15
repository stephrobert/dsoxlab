# Security Policy

## Supported versions

`dsoxlab` is in active development. Security fixes are applied to the latest
release on the `main` branch.

| Version | Supported |
| --- | --- |
| latest (`main`) | ✅ |
| older | ❌ |

## Reporting a vulnerability

**Please do not open a public issue for security vulnerabilities.**

If you believe you have found a security vulnerability, report it privately:

- Preferred: open a
  [private security advisory](https://github.com/stephrobert/dsoxlab/security/advisories/new)
  on GitHub.
- Alternatively, use the contact details published at
  <https://blog.stephane-robert.info>.

Please include:

- a description of the vulnerability and its impact,
- the steps to reproduce it (command, environment, `dsoxlab --version`),
- any relevant logs or proof of concept.

We will acknowledge your report as soon as possible, keep you informed about the
progress toward a fix, and credit you in the release notes if you wish.

## Scope

`dsoxlab` drives external tooling (SSH, Terraform, libvirt/Incus, `pytest`) and
executes lab scripts provided by lab repositories. Vulnerabilities in the engine
itself, in how it invokes those tools, or in the way it handles credentials and
generated configuration are in scope. Issues in third-party dependencies should
be reported to their respective projects.
