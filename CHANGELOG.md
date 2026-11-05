# Changelog

All notable changes to this project are documented here. Format loosely
follows [Keep a Changelog](https://keepachangelog.com/).

## [Unreleased]

### Added

- **Shadow mode.** `Rule(shadow=True)` / `PolicyEngine(shadow=True)` (and
  `shadow: true` in YAML, per rule or top-level) evaluate rules and audit
  their outcome as `would_block` / `would_approve` / `would_allow` without
  enforcing it or calling the approval handler. A shadow rule never changes
  the enforced outcome of the rules behind it. Dashboard audit log colours
  and filters `would_*` events.

### Changed

- `Decision.reason` is now a field rather than a computed property, and
  the no-match reason names the real default (`default block`, not always
  `default allow`).

### Fixed

- **Policy bypass on async LangChain tools.** `guard_tools()` /
  `guarded_tool_node()` only wrapped a tool's `.func`, so a tool with a
  `.coroutine` (async, or built with both) ran unguarded via `ainvoke` —
  the path LangGraph's `ToolNode` takes in an async graph. Async-only tools
  raised `TypeError`. Both `.func` and `.coroutine` are now guarded, and
  `guard()` returns an async wrapper for coroutine functions.
- **Dashboard audit sink could break tool calls.** It POSTed synchronously
  before every allowed tool ran, so a slow or unreachable dashboard stalled
  or failed every call. It now ships on a background thread: failures are
  logged on the `bastion` logger instead of raised, and pending events are
  flushed at interpreter exit. Non-JSON arg values are stringified, same as
  the JSONL sink.
- **`aws_secret_access_key` detection.** Missed the most common leak format
  (`AWS_SECRET_ACCESS_KEY=<key>`), and flagged every 40-character hex
  string — git SHAs, SHA-1 digests — as a secret.
- Integration error messages pointed at `pip install bastion[...]`, which
  installs an unrelated package; now `bastionguard[...]`.
- `send_email` rule in the LangGraph / OpenAI Agents examples was a
  deny-list (`any_arg_contains(["all-staff", "external"])`) that let any
  other recipient through. Now an allow-list: internal domain allowed,
  everything else requires approval.

## [0.1.0] - 2026-10-03

First published release.

### Added

- **Core policy engine**: `PolicyEngine`, `Rule`, `Action` (allow / block /
  approve), glob tool-name matching, condition helpers (`arg_exceeds`,
  `arg_matches_regex`, `any_arg_contains`).
- **`guard()` / `guard_tools()`**: wrap any callable or LangChain-style
  tool with policy enforcement; raises `BlockedByPolicy` on block/deny.
- **Audit logging**: JSONL by default, swappable sink.
- **Human-in-the-loop approval**: pluggable `ApprovalHandler` — console,
  Slack (reaction-polling, no webhook server needed), and the hosted
  dashboard.
- **Declarative YAML policy config**: `load_policy_from_yaml()` /
  `policy_from_yaml_string()`, so rules don't have to be hand-written
  Python.
- **PII/secrets scanning**: regex-based (no ML model dependency) —
  emails, US SSNs, Luhn-validated credit cards, AWS credentials, common
  API key formats, private key blocks. Usable as a policy condition
  (`contains_pii`) or directly on arbitrary text (`enforce_text_policy`),
  e.g. an LLM response.
- **Framework integrations**:
  - **LangGraph** — `guarded_tool_node()`, a drop-in `ToolNode` replacement.
    A blocked/denied call surfaces as a normal error `ToolMessage`
    instead of crashing the graph run.
  - **OpenAI Agents SDK** — `guarded_tools()` wraps `agents.FunctionTool`
    objects. A blocked/denied call returns a descriptive string result.
  - **Claude Agent SDK** — `guarded_can_use_tool()`, a `can_use_tool`
    callback covering every tool call (built-in and custom MCP tools
    alike) — no per-tool wrapping needed.
- **Dashboard** (`dashboard/`, Next.js + Postgres): audit log viewer
  (filterable), approval queue (Approve/Deny), and a policy editor —
  wired all the way through to the SDK via `load_policy_from_dashboard()`,
  `dashboard_audit_sink()`, and `DashboardApprovalHandler`. Session login
  for the UI, separate API-key auth for the SDK.
- Production tooling from day one: `ruff`, `mypy --strict`, `pytest`,
  GitHub Actions CI.

[0.1.0]: https://github.com/rayaan2003/bastion/releases/tag/v0.1.0
