# Architecture

How bastion is put together and why. For what's planned, see
[roadmap.md](roadmap.md); for what has shipped, [CHANGELOG.md](../CHANGELOG.md).

## Request path

Everything that decides whether a tool call runs happens in the agent's own
process. The dashboard is optional and only ever sees the result.

```
agent framework calls a tool
        │
        ▼
integrations/<framework>.py         adapts the framework's tool hook
        │
        ▼
guard.evaluate_and_record()         the one enforcement core
        ├─ PolicyEngine.evaluate()  → Decision (+ shadow decision)
        ├─ ApprovalHandler          only if the decision is APPROVE
        └─ AuditLogger.record()     every outcome, including would_*
        │
        ▼
tool runs, or the framework gets a "blocked" result
        ┆
        ┆  (async, best-effort)
        ▼
dashboard/  Next.js + Postgres: audit log, approval queue, policy editor
```

## Modules

| Module | Owns |
|---|---|
| `policy.py` | `Rule`, `PolicyEngine`, `Decision`, condition helpers |
| `config.py` | YAML → `PolicyEngine`, condition-type registry |
| `guard.py` | `evaluate_and_record()`, `guard()` / `guard_tools()` for plain callables and LangChain tools |
| `audit.py` | `AuditEvent`, `AuditLogger`, JSONL sink |
| `approval/` | `ApprovalHandler` interface, console handler, `slack.py` |
| `scanning.py` | regex PII/secrets detectors, `contains_pii` condition |
| `dashboard.py` | HTTP client for `dashboard/`: audit sink, approval handler, policy fetch |
| `integrations/` | agent-framework adapters only |

### Where new things go

- **A framework** → `integrations/<framework>.py`. Import the framework
  lazily inside the function so it stays an optional extra, and call
  `evaluate_and_record()` rather than re-implementing decisions. See
  [AGENTS.md](../AGENTS.md) for the full checklist.
- **An approval channel** (Teams, email, PagerDuty) → `approval/<channel>.py`,
  subclassing `ApprovalHandler`.
- **An audit destination** → any `Callable[[AuditEvent], None]` passed as
  `AuditLogger(sink=...)`. If it does network I/O, ship off the calling
  thread the way `DashboardAuditSink` does.
- **A condition type** → a helper returning `Callable[[dict], bool]`, plus an
  entry in `config._CONDITION_BUILDERS` so YAML can use it.

## Design decisions

**Evaluation is local.** Policy runs in-process with no network hop, so a
decision costs microseconds and keeps working when the dashboard is down.
The dashboard can *supply* policy (`load_policy_from_dashboard`) but is
never asked per call.

**First match wins; no match → `default_action` (allow by default).**
Ordering is the whole precedence model, so allow-lists are written as an
ALLOW rule followed by a catch-all APPROVE/BLOCK for the same tool. Default
allow keeps adoption friction low; set `default_action: block` for a
deny-by-default posture.

**Shadow rules are skipped over, not stopped at.** Adding a shadow rule
must never change enforced behaviour, so evaluation continues past a shadow
match to the real rule behind it, and a shadow rule whose condition raises
is logged and ignored. The would-be outcome is audited as a separate
`would_<action>` event, which keeps the dashboard schema unchanged.

**Approvals fail closed, audit shipping fails open.** An approval nobody
answers within its timeout is a deny. A dashboard that can't receive audit
events logs a warning and drops them — making audit delivery a hard
dependency of every tool call turned an observability outage into an agent
outage. Revisit (local spool + retry) if guaranteed delivery is needed.

**How a block surfaces depends on the framework**, chosen so the model sees
*why* and can react instead of the run crashing:

| Framework | Block/deny becomes |
|---|---|
| plain `guard()` | `BlockedByPolicy` raised |
| LangGraph | `BlockedByPolicy`, caught by `ToolNode(handle_tool_errors=BlockedByPolicy)` → error `ToolMessage` |
| OpenAI Agents SDK | the string `"Tool call blocked by policy: <reason>"` — raising would be swallowed into a generic error message by the SDK, losing the reason |
| Claude Agent SDK | `PermissionResultDeny(message=...)` from `can_use_tool` — built-in and MCP tools alike, but the SDK skips the callback for tools pre-allowed via `allowed_tools`/settings and under `bypassPermissions` |

**LangChain tools are guarded on both `.func` and `.coroutine`.** `ainvoke`
calls `.coroutine` directly when it's set, so wrapping only `.func` would
let every async invocation skip policy.

**`ApprovalHandler` is synchronous.** One interface for console, Slack and
dashboard. In the async integrations an approval wait therefore blocks the
event loop for its duration — fine for one agent, a problem for many on one
loop. On the roadmap.

**Scanning is regex, not ML.** No model download or spaCy dependency, fast
enough to run on every call. It catches the common, costly leaks and has a
known false-negative rate; it isn't a DLP classifier.

**Slack approval polls reactions** rather than using Block Kit buttons,
which need a public webhook server to receive clicks. Polling needs only a
bot token, so it works from a plain script.

**Policy YAML is validated in Python only.** The dashboard's policy editor
checks YAML syntax; rule semantics (unknown condition types, missing
fields) are checked by `bastion.config` when the SDK loads it, so the schema
lives in one place.

## Dashboard

A separate Next.js (App Router) app with Postgres via `DATABASE_URL`. Two
auth mechanisms, deliberately separate: a signed session cookie for humans
using the UI, and a Bearer API key for the SDK, which has no browser
session. `lib/session.ts` is edge-safe (used by `proxy.ts`), while
`lib/credentials.ts` uses `node:crypto` and must stay out of edge code.
Policy versions are append-only, so every saved policy is kept.

It started on PGlite (embedded WASM Postgres) and moved to real Postgres
once it was deployed somewhere with concurrent access. Setup and deployment
gotchas: [dashboard/README.md](../dashboard/README.md).
