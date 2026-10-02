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
- `tests/test_dashboard_integration.py` — 4 tests against a real stdlib
  `http.server` standing in for the dashboard API (actual HTTP calls over
  a real socket, not mocked `urllib`): event posting, wrong-API-key
  rejection, polling-until-approved, and deny-on-timeout.

Total: 35 Python tests passing, `ruff check .` / `mypy src` / `pytest -q`
all clean. Dashboard: `npx eslint .` clean, `npm run build` clean.

### Dashboard auth (2026-10-02)

The dashboard had zero authentication through the first build — anyone who
could reach its URL could view the audit log and approve/deny pending
actions, which undermines the point of a security/compliance tool. Added
two independent mechanisms, deliberately not shared:

- **Human login** — `lib/session.ts` (edge-safe, `jose`-based JWT signing,
  used by `middleware.ts` and the login route) + `lib/credentials.ts`
  (node:crypto, timing-safe password comparison, Node-runtime only).
  `/login` page, `/api/auth/login` and `/api/auth/logout` routes, a session
  cookie (httpOnly, signed, 7-day expiry) gates `/`, `/audit`, `/approvals`
  via middleware.
- **SDK API key** — every `/api/*` route now calls `requireApiKey()`
  (`Authorization: Bearer <key>`, timing-safe comparison) before doing
  anything else. Separate from the session cookie because the Python SDK
  has no browser session to present.
- Split `lib/session.ts` (edge-safe) from `lib/credentials.ts` (node:crypto)
  deliberately: Next.js middleware runs on the Edge runtime by default,
  which cannot import `node:crypto` — even transitively, even if the
  function using it is never called from that file. Mixing them in one
  module would have broken the build or silently failed at the edge.
- `dashboard_audit_sink()` and `DashboardApprovalHandler` both now take a
  required `api_key` argument and send it as a Bearer token.
- Verified against a live server with real env vars, not just unit tests:
  unauthenticated `/audit` redirects to `/login`; wrong password rejected,
  correct password sets a working session cookie that then grants access;
  `/api/events` POST returns 401 with no key or the wrong key, 201 with the
  right one; ran the actual Python SDK (`dashboard_audit_sink`,
  `DashboardApprovalHandler`) against the live authenticated server end to
  end, including the full polling-approval loop in a background thread
  while approving it via the API mid-poll — confirmed it returns `True`
  exactly when expected, not just that it doesn't crash.

### Live deployment (2026-10-02)

Dashboard deployed to Vercel: **https://agentguard-dashboard-nine.vercel.app**
Database: Supabase Postgres (transaction pooler connection, required — direct
connections are IPv6-only and unreachable from Vercel's serverless runtime).

Setup notes for next time:
- Vercel's own "Vercel Authentication" deployment protection is on by
  default for new projects and puts *Vercel's* login wall in front of
  everything, before our app's own `/login` is ever reached. Had to be
  turned off in Project Settings → Deployment Protection.
- `echo "value" | vercel env add KEY production` silently stores a trailing
  newline as part of the secret (from `echo`'s own newline) — broke
  password, session-secret, and API-key comparisons in a way that failed
  confusingly (login *looked* like it succeeded by status code alone,
  because both the success and failure paths return 303 — only the
  `Location` header differs). Fixed by using `printf '%s'` instead of
  `echo`, which doesn't add a trailing newline. Verified by pulling the
  env vars back down and checking exact byte lengths before redeploying.
- Verified the fix against the live production URL end to end (not just
  "build succeeded"): login, session cookie, API key accept/reject, and
  a real Python SDK call through `dashboard_audit_sink` all the way to
  the rendered `/audit` page.

### Policy config editor (2026-10-02)

Added a `/policy` page (session-protected) where a reviewer edits the
policy YAML the SDK actually enforces — not just a local text editor, it's
wired all the way through:

- `dashboard/lib/policy.ts` — append-only `policy_versions` table (every
  save kept, not overwritten — a free history of policy changes, matching
  the audit-trail ethos of the rest of the product)
- `GET /api/policy` (API-key protected) — what the SDK fetches
- `POST /policy/save` (session-protected route, not under `/api/*` since
  it's a human form submission, not the SDK) — validates YAML *syntax*
  only (`js-yaml`); deeper rule validation (unknown condition type, missing
  fields) deliberately stays Python-side in `agentguard.config`, same as
  it always worked for a local file — not worth duplicating that schema
  logic in TypeScript
- Python: `agentguard.config.policy_from_yaml_string()` (extracted from
  `load_policy_from_yaml` for reuse) and
  `agentguard.integrations.dashboard.load_policy_from_dashboard()`
- 6 new/updated tests (39 total Python tests passing)
- Verified the **entire chain for real**, not just each piece in
  isolation: submitted a rule through the actual `/policy` form → saved to
  real Supabase → SDK's `load_policy_from_dashboard()` fetched it → called
  `guard()` with that policy → the exact tool call got blocked with the
  exact reason text typed into the browser. Also verified invalid YAML is
  rejected before touching the database (confirmed the prior valid policy
  was untouched after a bad submission).

## Next up, in order

1. **Ship v1 publicly.** OSS SDK on GitHub/PyPI + hosted dashboard waitlist.
   Get 5-10 real teams to install it before iterating further — see GTM
   notes in NOTES.md. This is the actual next priority over further
   features — the MVP scope from this file is now fully built, including
   the policy editor.

## Definition of done (every item above)

Per [AGENTS.md](AGENTS.md): `ruff check .`, `mypy src`, and `pytest -q` all
pass; tests added for new behavior; NOTES.md/PLAN.md updated if scope or
architecture changed.
