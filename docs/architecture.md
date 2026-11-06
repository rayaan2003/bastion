# Architecture

How bastion is put together and why. For what's planned, see
[roadmap.md](roadmap.md); for what has shipped, [CHANGELOG.md](../CHANGELOG.md).

## Request path

Everything that decides whether a tool call runs happens in the agent's own
process, or in the MCP proxy's when there's no agent code to wrap. The
dashboard is optional and only ever sees the result.

```
agent framework calls a tool          MCP client sends tools/call
        │                                     │
        ▼                                     ▼
integrations/<framework>.py         mcp_proxy.py (bastion mcp-proxy)
        │
        ▼
guard.evaluate_and_record()         the one enforcement core
        ├─ PolicyEngine.evaluate()  → Decision (+ shadow decision)
        ├─ ApprovalHandler          only if the decision is APPROVE
        └─ AuditLogger.record()     every decision, including would_*
        │
        ▼
tool runs, or the framework gets a "blocked" result
        │
        ▼
guard.record_outcome()              completed / failed, same call_id
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
| `mcp_proxy.py` | stdio MCP proxy that checks `tools/call` and relays everything else |
| `cli.py` | the `bastion` command (`bastion mcp-proxy`) |

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

**One call, several events, one `call_id`.** A decision is recorded before
the tool runs and its outcome after, as separate events, rather than one
event updated in place — sinks are append-only (JSONL, HTTP). The framework's
own id is used where it has one (OpenAI `tool_call_id`, Claude `tool_use_id`)
so bastion's log can be joined against the framework's traces. Outcomes are
`completed`/`failed`, not success/error: bastion can only see whether the
tool returned or raised, and the OpenAI Agents SDK converts exceptions into
results by default.

**Audit logs redact args; enforcement doesn't.** `AuditLogger` masks
detected PII/secrets in the logged copy of args by default (strings, nested
containers, and numbers such as a card passed as an int). Policy conditions
and the tool always get the raw args — redacting before evaluation would
blind `contains_pii` rules. Approval requests are not redacted, since a
reviewer usually needs the real values to decide.

**How a block surfaces depends on the framework**, chosen so the model sees
*why* and can react instead of the run crashing:

| Framework | Block/deny becomes |
|---|---|
| plain `guard()` | `BlockedByPolicy` raised |
| LangGraph | `BlockedByPolicy`, caught by `ToolNode(handle_tool_errors=BlockedByPolicy)` → error `ToolMessage` |
| OpenAI Agents SDK | the string `"Tool call blocked by policy: <reason>"` — raising would be swallowed into a generic error message by the SDK, losing the reason |
| Claude Agent SDK | a `PreToolUse` hook returning `permissionDecision: "deny"` with the reason; `PostToolUse`/`PostToolUseFailure` hooks record the outcome |

**Claude Agent SDK enforces through a `PreToolUse` hook, not `can_use_tool`.**
The SDK only consults `can_use_tool` when its own permission rules would
prompt, so tools pre-allowed by `allowed_tools`/settings, and everything
under `bypassPermissions`, never reached bastion. The hook runs for every
call. An allowed call returns no decision rather than `"allow"`, since a
hook allow also skips the SDK's permission checks; the matcher uses
`on_failure="block"` so a hook error blocks the call; policy and approval
run through `evaluate_and_record_async()` (below). Outcome hooks don't set `on_failure`, so an audit error there can't block
anything. `guarded_can_use_tool()` remains for compatibility.

**LangChain tools are guarded on both `.func` and `.coroutine`.** `ainvoke`
calls `.coroutine` directly when it's set, so wrapping only `.func` would
let every async invocation skip policy.

**Approval handlers take a request object and return a decision object.**
`request_approval(ApprovalRequest) -> ApprovalDecision` rather than loose
arguments and a bool, so new fields (the request's `call_id`/`session_id`,
the decision's `approver`) don't break every handler again. The request
carries raw args, since a reviewer needs them. An empty `approver` means
nobody decided (a timeout). The dashboard records where a decision was
made (`ui`/`api`) rather than a person, because it has one shared login;
named reviewers need the multi-user dashboard. Slack takes the first user
to react, and a deny reaction wins over an approve. With `approvers` set,
reactions from anyone else are ignored, denies included: an outsider's ❌
could otherwise veto every call, and an unlisted reaction carries no
authority either way.

**`ApprovalHandler` is synchronous; async callers wait for it on a
thread.** One interface for console, Slack and dashboard, rather than a
sync and an async variant of each. Every async path (OpenAI Agents, both
Claude Agent SDK entry points, async tools under `guard()`) goes through
`evaluate_and_record_async()`, which evaluates policy on the event loop and
moves only the approval wait to a thread, so allowed calls never touch a
thread. That thread comes from bastion's own pool (32 threads), not the
loop's default executor: the default pool is small and shared, the OpenAI
Agents SDK runs sync tools on it, and a pending approval can hold a thread
for minutes. More than 32 simultaneous pending approvals queue behind each
other, not behind tool calls.

**The MCP proxy relays JSON-RPC lines, not MCP SDK objects.** It only
needs to recognise `tools/call`; everything else (resources, prompts,
sampling, protocol versions it has never seen) passes through. That keeps
it dependency-free and unaffected by SDK churn: mcp 2.x renamed `FastMCP`
and made the protocol stateless (`server/discover`, a version in every
request's `_meta`) without the proxy needing to change. Its rules:

- Messages from the client are **re-encoded** before forwarding, so the
  server parses exactly what was checked even if its JSON parser treats
  duplicate keys or escapes differently from Python's.
- Anything it can't read is **dropped**, not forwarded: unparseable lines,
  a `tools/call` without an id, a batch containing a `tools/call` (batches
  were removed from MCP in 2025-06-18).
- A blocked call is answered by the proxy with an `isError` result, the
  way MCP reports tool errors, so the model reads the reason. On
  2026-07-28+ requests it includes `resultType: "complete"`, which those
  clients require.
- Each `tools/call` is decided in its own task, so a pending approval
  doesn't hold up other messages. A call cancelled
  (`notifications/cancelled`) while a human is deciding is never forwarded.
- An `input_required` or task result isn't an outcome yet. The client's
  retry is a new `tools/call` and is checked again, which with an
  `approve` rule means asking again.
- The terminal can't approve: stdin is the MCP connection. Approvals go to
  Slack or the dashboard, or are denied.

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
