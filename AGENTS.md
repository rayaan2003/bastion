# AGENTS.md

Instructions for any AI agent (or human) working in this repository.

## What this repo is

`agentguard` — a Python SDK that enforces policy on AI agent tool calls
(allow/block/require-approval) and produces an audit log. See
[NOTES.md](NOTES.md) for product context and [PLAN.md](PLAN.md) for the
current roadmap and task list.

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
  guard.py                wraps callables/tools with policy enforcement
  approval.py             human-in-the-loop approval handlers
  audit.py                audit event logging
  integrations/           framework-specific glue (langgraph.py, more later)
examples/                 runnable, dependency-minimal demos
tests/                    pytest suite, mirrors src/agentguard structure
.github/workflows/ci.yml  lint + typecheck + test on push/PR
```

When adding a new framework integration, it goes under
`src/agentguard/integrations/<framework>.py` and imports the framework
lazily inside the function (see `integrations/langgraph.py`) so the core
package has zero hard dependency on it — the framework stays an optional
extra in `pyproject.toml`.

## Dev setup

```bash
python -m venv .venv
.venv/Scripts/activate   # or source .venv/bin/activate on macOS/Linux
pip install -e ".[dev,langgraph]"
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
