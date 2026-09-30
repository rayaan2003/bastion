# PLAN — Roadmap & Task List

What to build next, in order. For *why* these choices, see [NOTES.md](NOTES.md).
For repo conventions, see [AGENTS.md](AGENTS.md). Check items off as they land;
don't delete completed items — they're the changelog.

## MVP scope (v1)

In scope:
- [x] Tool-call interception (wrap the agent's tool-execution step)
- [x] Policy engine — allow-list/block-list/condition rules on tool args
- [x] Human-in-the-loop approval for flagged actions (console handler +
      Slack handler, both done)
- [x] Declarative (YAML) policy config, so rules aren't hand-written Python
- [ ] Basic PII/secrets scan on tool-call args + LLM outputs
- [ ] Audit log dashboard — every call, decision, timestamp, agent/session id

Explicitly OUT of v1 (defer):
- Prompt-injection detection (commoditized, low differentiation)
- Multi-framework support beyond LangGraph
- On-prem / SSO / enterprise auth
- EU AI Act / compliance report generation

## Status (2026-09-30)

Repo scaffolded, package installable via `pip install -e .`. Production
tooling in place: ruff, mypy (strict), pytest, CI workflow. Git repo
initialized locally — not committed, no remote yet.

Built and verified (tests passing, demo run end-to-end):
- `policy.py` — `PolicyEngine`, `Rule`, `Action` enum, condition helpers
- `guard.py` — `guard()` / `guard_tools()`, raises `BlockedByPolicy`
- `approval.py` — `ApprovalHandler` ABC, `ConsoleApprovalHandler`, `AutoDenyHandler`
- `audit.py` — `AuditLogger`, JSONL sink
- `integrations/langgraph.py` — `guarded_tool_node()`, `ToolNode` configured
  with `handle_tool_errors=BlockedByPolicy` so a block/deny surfaces as a
  normal error `ToolMessage` the agent can react to, instead of crashing the
  graph run (found and fixed by testing against real LangGraph execution,
  not just unit tests — see below)
- `tests/test_policy.py` — 7 tests, all passing
- `integrations/slack.py` — `SlackApprovalHandler`, reaction-polling approval
  (posts a message, polls for ✅/❌ reaction; no webhook server needed since
  it doesn't use Slack's Block Kit button + Interactivity API). Fails closed
  (denies) if nobody responds within `timeout`. `client` is injectable for
  testing, so `slack_sdk` stays a true optional import — confirmed by
  running the full test suite with `slack_sdk` *not* installed before
  installing it and confirming still-clean mypy/ruff/pytest afterward
- `tests/test_slack_approval.py` — 3 tests against a fake Slack client
  (approve, deny, timeout-denies), all passing
- `examples/basic_example.py` — dependency-free, verified working
- `examples/langgraph_demo.py` — verified against real LangGraph execution:
  invoked the compiled graph with actual `AIMessage(tool_calls=[...])`
  input covering all three paths (allowed, blocked, approval-denied) and
  confirmed each produces the correct `ToolMessage` — not just that the
  script runs without error. This surfaced a real bug: `BlockedByPolicy`
  was crashing the whole graph run instead of becoming a normal tool
  result, fixed via `ToolNode(..., handle_tool_errors=BlockedByPolicy)`

- `config.py` — `load_policy_from_yaml()` / `policy_from_dict()`, declarative
  `Rule`/`PolicyEngine` loading from YAML with a small condition-type
  registry (`arg_exceeds`, `arg_matches_regex`, `any_arg_contains`).
  Malformed config raises `PolicyConfigError` with a specific message
  (missing field, unknown action, unknown condition type) rather than a
  raw `KeyError`/`ValueError`
- `tests/test_config.py` — 6 tests: file loading, all three condition types,
  and each error path, all passing
- `examples/policy.yaml` + `examples/yaml_policy_example.py` — verified
  end-to-end (loads the YAML file, blocks `delete_database` correctly)
- Along the way: removed an unused `pydantic` dependency that had been
  declared in `pyproject.toml` but never imported anywhere — caught by
  actually checking, not assuming the dependency list was accurate

Total: 17 tests passing, `ruff check .` / `mypy src` / `pytest -q` all clean
with dev+langgraph+slack extras installed.

## Next up, in order

1. **PII/secrets scanning.** Add a scan step on tool args and LLM outputs.
   Evaluate Microsoft Presidio (local, no API cost, slower) vs. a hosted
   API (faster to integrate, ongoing cost, sends data externally — probably
   wrong default for a security tool). Leaning local-first.
2. **Dashboard.** Next.js + Postgres. Views: audit log (searchable/filterable),
   policy config editor, pending-approval queue. This is what turns the raw
   JSONL log into the compliance artifact enterprises actually want.
3. **Ship v1 publicly.** OSS SDK on GitHub/PyPI + hosted dashboard waitlist.
   Get 5-10 real teams to install it before iterating further — see GTM
   notes in NOTES.md.

## Definition of done (every item above)

Per [AGENTS.md](AGENTS.md): `ruff check .`, `mypy src`, and `pytest -q` all
pass; tests added for new behavior; NOTES.md/PLAN.md updated if scope or
architecture changed.
