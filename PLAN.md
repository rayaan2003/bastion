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
- [x] Basic PII/secrets scan on tool-call args + LLM outputs
- [x] Audit log dashboard — every call, decision, timestamp, agent/session id

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

- `scanning.py` — regex-based detectors (email, US SSN, credit card w/ Luhn
  validation, AWS access/secret keys, common API key formats, private key
  blocks); `scan_text()`, `redact()`, `contains_pii()` (a `PolicyEngine`
  condition for tool-call args), `enforce_text_policy()` (block/redact
  applied directly to arbitrary text, e.g. an LLM response, outside the
  tool-call path — this is deliberately a standalone function rather than
  a framework-specific hook, since no LLM-call interception exists yet in
  any integration). Chose regex over Microsoft Presidio: no spaCy/ML model
  dependency, matches "basic" scope, easy to extend later if the
  false-negative rate becomes a real problem
- `contains_pii` wired into the YAML condition registry (`type: contains_pii`)
- `tests/test_scanning.py` — 14 tests, including a real check that Luhn
  validation actually rejects a non-Luhn 16-digit sequence (not just that
  the assertion happens to pass)
- `examples/pii_scanning_example.py` — verified end-to-end: blocks a tool
  call with an SSN in its args, allows a clean call through, blocks/redacts
  PII in a standalone text string (the "LLM output" case)

- `dashboard/` — a separate Next.js (TypeScript, App Router) app, not part
  of the Python package. Database: PGlite (embedded Postgres compiled to
  WASM, file-persisted under `dashboard/data/`, gitignored) rather than a
  hosted Postgres instance — deliberate v1 choice so there's nothing to
  stand up before there are real users; doesn't support concurrent writers
  from multiple processes, swap for real Postgres (`pg` + a connection
  string) when that matters. Schema in `dashboard/lib/schema.sql`, applied
  idempotently on startup, no migration tooling at this scale.
  - `/audit` — filterable audit log table (tool name / action / session id)
  - `/approvals` — pending-approval queue, Approve/Deny buttons (Server Actions)
  - API: `POST/GET /api/events`, `POST/GET /api/approvals`,
    `GET /api/approvals/[id]`, `POST /api/approvals/[id]/decide`
  - Found and fixed two real bugs via an actual production build, not just
    "it compiled": (1) PGlite's data directory didn't exist yet on first
    run (`fs.mkdirSync(..., {recursive: true})` before opening it), and
    (2) Next.js tried to statically prerender `/approvals` and `/audit` at
    build time even though they read live DB state on every request
    (`export const dynamic = "force-dynamic"` on both). Also hit and fixed
    a PGlite + Next.js bundling incompatibility (WASM asset resolution
    breaks when bundled) via `serverExternalPackages` in `next.config.ts`
  - Verified the full flow with real HTTP calls against the running dev
    server, not just reading the code: posted an audit event and confirmed
    it rendered on `/audit` with correct filtering; created an approval,
    polled it as pending, decided it via the API (same function the
    Approve/Deny buttons call), confirmed it left the pending list, and
    confirmed a second decision attempt on an already-decided approval is
    correctly rejected (404) rather than silently overwriting
- `src/agentguard/integrations/dashboard.py` — `dashboard_audit_sink()` (an
  `AuditLogger` sink that POSTs to `/api/events` instead of writing JSONL)
  and `DashboardApprovalHandler` (creates a pending approval via the API,
  polls until a reviewer decides it on `/approvals`, fails closed/denies on
  timeout — same pattern as `SlackApprovalHandler`). Stdlib `urllib` only,
  no new dependency.
- `tests/test_dashboard_integration.py` — 3 tests against a real stdlib
  `http.server` standing in for the dashboard API (actual HTTP calls over
  a real socket, not mocked `urllib`): event posting, polling-until-approved,
  and deny-on-timeout.

Total: 34 Python tests passing, `ruff check .` / `mypy src` / `pytest -q`
all clean. Dashboard: `npx eslint .` clean, `npm run build` clean.

## Next up, in order

1. **Policy config editor in the dashboard.** Currently the dashboard only
   shows audit logs and approvals — editing `policy.yaml` still happens by
   hand. Lower priority than it sounds: the YAML format already makes this
   readable by a non-engineer without a UI.
2. **Ship v1 publicly.** OSS SDK on GitHub/PyPI + hosted dashboard waitlist.
   Get 5-10 real teams to install it before iterating further — see GTM
   notes in NOTES.md. This is the actual next priority over further
   features — the MVP scope from this file is now fully built.

## Definition of done (every item above)

Per [AGENTS.md](AGENTS.md): `ruff check .`, `mypy src`, and `pytest -q` all
pass; tests added for new behavior; NOTES.md/PLAN.md updated if scope or
architecture changed.
