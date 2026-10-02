# Changelog

All notable changes to this project are documented here. Format loosely
follows [Keep a Changelog](https://keepachangelog.com/).

## [0.1.0] - 2026-10-02

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
