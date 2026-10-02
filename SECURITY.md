# Security Policy

bastion is a security tool, so we take reports about it seriously.

## Reporting a vulnerability

**Please don't open a public GitHub issue for security vulnerabilities.**

Instead, email rayaansheikh442@gmail.com with:

- A description of the vulnerability and its impact
- Steps to reproduce (a minimal repro is ideal)
- Any suggested fix, if you have one

We'll acknowledge your report within 72 hours and aim to ship a fix or
mitigation before any public disclosure. Credit is given in the release
notes unless you'd prefer otherwise.

## Scope

In scope: the `bastion` Python package (policy engine, guard logic,
framework integrations, scanning) and the `dashboard/` Next.js app.

A policy you configure incorrectly (e.g. an overly permissive rule) is a
usage issue, not a vulnerability in the tool itself — though if the
*defaults* are unsafe, that's fair game to report.

## Supported versions

Pre-1.0: only the latest published release is supported. There's no
long-term support branch yet.
