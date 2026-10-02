# bastion dashboard

Audit log viewer and human-approval queue for the `bastion` Python SDK
(see the repo root). Two pages:

- **`/audit`** — every tool-call decision the SDK recorded (allowed /
  blocked / approved / denied), filterable by tool name, action, and
  session id.
- **`/approvals`** — the live queue of actions waiting on a human reviewer,
  with Approve/Deny buttons.
- **`/policy`** — edit the policy YAML the SDK enforces, instead of hand-
  editing a local `policy.yaml` file. Validates YAML syntax on save;
  deeper rule validation (unknown condition type, missing fields) happens
  Python-side when the SDK loads it, same as it always did for a local
  file. Every save is kept (append-only version history), not overwritten.

## Live deployment

https://bastion-dashboard-two.vercel.app (Vercel + Supabase Postgres)

## Database

Real Postgres via `DATABASE_URL` (see `lib/db.ts`). In production this is
Supabase — use the **transaction pooler** connection string, not the direct
one: Supabase's direct connections are IPv6-only, which Vercel's serverless
functions can't reach. The pooler string looks like
`postgresql://postgres.<project-ref>:<password>@aws-0-<region>.pooler.supabase.com:6543/postgres`.

Schema lives in `lib/schema.sql` and is applied (idempotently) on startup —
no separate migration step at this scale.

(v1 ran on PGlite, an embedded WASM Postgres, to avoid standing up a
database before there were real users. Swapped to real Postgres once the
dashboard was actually being deployed somewhere reachable — PGlite doesn't
support concurrent writers from multiple processes. See `NOTES.md` at the
repo root.)

## Auth

Two separate mechanisms, deliberately not shared:

- **Human login** (`/login`) — a single shared password (`DASHBOARD_PASSWORD`),
  sets a signed, httpOnly session cookie (`DASHBOARD_SESSION_SECRET`) via
  `proxy.ts` (Next.js's middleware convention) that gates `/`, `/audit`, and
  `/approvals`. Sign out from the nav bar.
- **SDK API key** (`DASHBOARD_API_KEY`) — every `/api/*` route requires
  `Authorization: Bearer <key>`. This is what the Python SDK sends; it has
  no browser session, so it can't use the login cookie.

Copy `.env.example` to `.env.local` and fill in real values (the example
file has a one-liner to generate strong random secrets) before running
anything beyond a quick look at the UI with no backing data.

## Dev setup

```bash
npm install
cp .env.example .env.local   # then edit in real secrets, including DATABASE_URL
npm run dev
```

Opens at http://localhost:3000, redirects to `/login` until you sign in.

## Deploying (Vercel)

```bash
vercel link
vercel env add DATABASE_URL production            # paste value, do NOT pipe via `echo` - see gotcha below
vercel env add DASHBOARD_PASSWORD production
vercel env add DASHBOARD_SESSION_SECRET production
vercel env add DASHBOARD_API_KEY production
vercel --prod
```

Two gotchas hit during the first deploy, worth knowing before you hit them
again:

1. **Vercel's own "Vercel Authentication" deployment protection** is on by
   default for new projects and puts *Vercel's* login wall in front of
   everything — before our app's `/login` is ever reached. Turn it off in
   the Vercel dashboard: Project Settings → Deployment Protection →
   "Require Log In" → off.
2. **Never pipe env var values through `echo`**: `echo "value" | vercel env
   add KEY production` stores `echo`'s trailing newline as part of the
   secret, which silently breaks every comparison against it (password
   check, API key check, session signing/verification) without an obvious
   error — the login route still returns a 303 either way, so check the
   `Location` header, not just the status code, if this bites you. Use
   `printf '%s' "value" | vercel env add KEY production` instead (no
   trailing newline). If in doubt, `vercel env pull` and check the exact
   byte length of the value.

## Wiring up the Python SDK

```python
from bastion import AuditLogger, guard
from bastion.integrations.dashboard import (
    DashboardApprovalHandler,
    dashboard_audit_sink,
    load_policy_from_dashboard,
)

api_key = "..."  # must match DASHBOARD_API_KEY in the dashboard's env
policy = load_policy_from_dashboard("http://localhost:3000", api_key)
audit = AuditLogger(sink=dashboard_audit_sink("http://localhost:3000", api_key))
approval_handler = DashboardApprovalHandler("http://localhost:3000", api_key)

guarded_fn = guard(my_tool, policy=policy, audit=audit, approval_handler=approval_handler)
```

`load_policy_from_dashboard()` fetches once at call time — call it again
(e.g. on a timer) to pick up edits made after the agent process started.

A blocked-pending-approval call creates a row on `/approvals`; the SDK polls
until a reviewer clicks Approve/Deny there (or the call times out and fails
closed — denied).

## Before committing

```bash
npx eslint .
npm run build
```
