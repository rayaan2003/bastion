# agentguard dashboard

Audit log viewer and human-approval queue for the `agentguard` Python SDK
(see the repo root). Two pages:

- **`/audit`** — every tool-call decision the SDK recorded (allowed /
  blocked / approved / denied), filterable by tool name, action, and
  session id.
- **`/approvals`** — the live queue of actions waiting on a human reviewer,
  with Approve/Deny buttons.

## Database

Uses [PGlite](https://pglite.dev) — a real Postgres compiled to WASM,
embedded in the Node process and file-persisted under `./data/pgdata`
(gitignored). This is a deliberate v1 choice: no external Postgres instance
to stand up before there are real users. It does **not** support concurrent
writers from multiple processes — swap `lib/db.ts` for a real Postgres
connection (e.g. via `pg`, pointed at a hosted instance) once that matters.
See `NOTES.md` at the repo root for the full reasoning.

Schema lives in `lib/schema.sql` and is applied (idempotently) on startup —
no separate migration step at this scale.

## Dev setup

```bash
npm install
npm run dev
```

Opens at http://localhost:3000, redirects to `/audit`.

## Wiring up the Python SDK

```python
from agentguard import AuditLogger, guard
from agentguard.integrations.dashboard import DashboardApprovalHandler, dashboard_audit_sink

audit = AuditLogger(sink=dashboard_audit_sink("http://localhost:3000"))
approval_handler = DashboardApprovalHandler("http://localhost:3000")

guarded_fn = guard(my_tool, policy=policy, audit=audit, approval_handler=approval_handler)
```

A blocked-pending-approval call creates a row on `/approvals`; the SDK polls
until a reviewer clicks Approve/Deny there (or the call times out and fails
closed — denied).

## Before committing

```bash
npx eslint .
npm run build
```
