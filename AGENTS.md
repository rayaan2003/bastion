# AGENTS.md

Instructions for any AI agent (or human) working in this repository.

## What this repo is

`agentguard` — a Python SDK that enforces policy on AI agent tool calls
(allow/block/require-approval) and produces an audit log, plus a Next.js
dashboard (`dashboard/`) for viewing that log and managing approvals/policy
through a UI. See [NOTES.md](NOTES.md) for product context and
[PLAN.md](PLAN.md) for the current roadmap and task list. See
[CONTRIBUTING.md](CONTRIBUTING.md) for the contributor-facing version of
this file.

## Non-negotiables

- **No AI slop.** No filler docstrings that restate the function name. No
  comments explaining *what* the code does when the code already says it —
  only comment on *why*, and only when it's non-obvious (a workaround, a
  hidden constraint, a subtle invariant). No speculative abstractions,
  config flags, or "just in case" parameters for things nothing calls yet.
- **No placeholder/stub code presented as done.** If something isn't
  implemented, it doesn't exist in the codebase — it's a line item in
  PLAN.md, not a function that raises `NotImplementedError` or returns a
  fake value.
- **Every change must pass the full check before it's considered done:**
  ```
  ruff check .
  mypy src
  pytest -q
  ```
  Don't report work as complete without having actually run these.
- Public functions/classes get type hints everywhere (mypy strict mode is
  on — see `pyproject.toml`). No untyped defs.
- Keep modules single-purpose and small. If a file is doing two jobs, split
  it before it grows further, not after.

## Project layout

```
src/agentguard/          the package (installed as `agentguard`)
  policy.py               policy engine: Rule, PolicyEngine, Action, conditions
  guard.py                wraps callables/tools with policy enforcement;
                           evaluate_and_record() is the shared policy/audit/
                           approval core every integration below reuses
  approval.py              human-in-the-loop approval handlers
  audit.py                 audit event logging
  config.py                declarative YAML policy loading
  scanning.py               regex-based PII/secrets detection
  integrations/
    langgraph.py            guarded_tool_node()
    openai_agents.py         guarded_tools()
    claude_agent_sdk.py       guarded_can_use_tool()
    slack.py                  SlackApprovalHandler
    dashboard.py              talks to dashboard/'s HTTP API
examples/                 runnable, dependency-minimal demos (one per integration)
tests/                    pytest suite, mirrors src/agentguard structure —
                           framework integration tests run against the real
                           installed package, never a mock of its API
dashboard/                Next.js + Postgres app; see dashboard/README.md
                           and dashboard/AGENTS.md (deployment-specific)
.github/workflows/ci.yml  lint + typecheck + test on push/PR
```

When adding a new framework integration:
1. It goes under `src/agentguard/integrations/<framework>.py` and imports
   the framework lazily inside the function (see `integrations/langgraph.py`)
   so the core package has zero hard dependency on it — the framework
   stays an optional extra in `pyproject.toml`.
2. **Inspect the real, installed package's current API before writing
   anything against it** — don't rely on a remembered or guessed API.
   Every integration in this repo found at least one real bug this way
   (see PLAN.md's history for specifics). Write a throwaway script that
   imports the package and prints `dir()` / `inspect.signature()` on the
   relevant types first.
3. Reuse `evaluate_and_record()` from `guard.py` for the actual policy/
   audit/approval decision — don't reimplement that logic per integration.
4. Tests go against the real installed package (skip gracefully via
   `pytest.importorskip` if it's not installed — see
   `tests/test_openai_agents_integration.py` for the pattern), not a mock
   of its types.
5. Verify the package still degrades gracefully with the new dependency
   *not* installed: uninstall it, confirm `ruff`/`mypy`/`pytest` still
   pass clean, reinstall, reconfirm green.

## Dev setup

```bash
python -m venv .venv
.venv/Scripts/activate   # or source .venv/bin/activate on macOS/Linux
pip install -e ".[dev,langgraph,slack,openai-agents,claude-agent-sdk]"
```

## Before calling anything "done"

1. `ruff check .` — zero warnings
2. `mypy src` — zero errors
3. `pytest -q` — all passing, and add tests for new behavior in the same
   change, not as a follow-up
4. If you changed product direction, scope, or architecture, update
   [NOTES.md](NOTES.md) (context/history) and [PLAN.md](PLAN.md) (what's
   next) in the same change — don't let the docs drift from the code.
5. Don't commit generated artifacts (`*.jsonl` audit logs, `.venv/`,
   `__pycache__/`) — `.gitignore` already excludes these, keep it that way.
