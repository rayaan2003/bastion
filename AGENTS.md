# AGENTS.md

Instructions for any AI agent (or human) working in this repository.

## What this repo is

`bastion` — a Python SDK that enforces policy on AI agent tool calls
(allow/block/require-approval) and produces an audit log, plus a Next.js
dashboard (`dashboard/`) for viewing that log and managing approvals/policy
through a UI. See [docs/architecture.md](docs/architecture.md) for how
it's built and why, and [docs/roadmap.md](docs/roadmap.md) for what's next.
See [CONTRIBUTING.md](CONTRIBUTING.md) for the contributor-facing version of
this file.

## Non-negotiables

- **No AI slop.** No filler docstrings that restate the function name. No
  comments explaining *what* the code does when the code already says it —
  only comment on *why*, and only when it's non-obvious (a workaround, a
  hidden constraint, a subtle invariant). No speculative abstractions,
  config flags, or "just in case" parameters for things nothing calls yet.
- **No placeholder/stub code presented as done.** If something isn't
  implemented, it doesn't exist in the codebase — it's a line item in
  docs/roadmap.md, not a function that raises `NotImplementedError` or returns a
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
src/bastion/              the package (PyPI: `bastionguard`, import: `bastion`)
  policy.py                 Rule, PolicyEngine, Decision, condition helpers
  config.py                 declarative YAML policy loading
  guard.py                  evaluate_and_record() — the one policy/audit/
                            approval core every integration reuses — plus
                            guard()/guard_tools() for callables and LangChain tools
  audit.py                  AuditEvent, AuditLogger, JSONL sink
  scanning.py               regex-based PII/secrets detection
  dashboard.py              HTTP client for dashboard/ (audit sink, approvals, policy)
  approval/                 approval channels
    __init__.py               ApprovalHandler, ConsoleApprovalHandler, AutoDenyHandler
    slack.py                  SlackApprovalHandler
  integrations/             agent-framework adapters only
    langgraph.py              guarded_tool_node()
    openai_agents.py          guarded_tools()
    claude_agent_sdk.py       guarded_can_use_tool()
tests/                    pytest suite, one file per module — framework tests
                          run against the real installed package, never a mock
examples/                 runnable, dependency-minimal demos (one per integration)
docs/                     architecture.md (how and why), roadmap.md (what's next)
dashboard/                Next.js + Postgres app; see dashboard/README.md
.github/workflows/        ci.yml (Python + dashboard checks), publish.yml (PyPI on release)
```

New approval channels go in `approval/`, new audit destinations are a
`Sink` callable, new framework adapters go in `integrations/` — see
docs/architecture.md "Where new things go".

When adding a new framework integration:
1. It goes under `src/bastion/integrations/<framework>.py` and imports
   the framework lazily inside the function (see `integrations/langgraph.py`)
   so the core package has zero hard dependency on it — the framework
   stays an optional extra in `pyproject.toml`.
2. **Inspect the real, installed package's current API before writing
   anything against it** — don't rely on a remembered or guessed API.
   Every integration in this repo found at least one real bug this way
   (see CHANGELOG.md for specifics). Write a throwaway script that
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
4. Add a CHANGELOG.md entry under `[Unreleased]`. If you changed
   architecture or a design decision, update docs/architecture.md; if you
   finished or reprioritised roadmap work, update docs/roadmap.md — in the
   same change, so docs don't drift from the code.
5. Don't commit generated artifacts (`*.jsonl` audit logs, `.venv/`,
   `__pycache__/`) — `.gitignore` already excludes these, keep it that way.

## Commits and PRs

Commits are authored by the human maintainer only — no `Co-Authored-By`
trailers for AI tools and no "Generated with ..." lines in PR descriptions.
