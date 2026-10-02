# Contributing

## Dev setup

```bash
git clone https://github.com/rayaan2003/bastion.git
cd bastion
python -m venv .venv
.venv/Scripts/activate   # or source .venv/bin/activate on macOS/Linux
pip install -e ".[dev,langgraph,slack,openai-agents,claude-agent-sdk]"
```

## Before opening a PR

```bash
ruff check .
mypy src
pytest -q
```

All three must pass clean. CI runs the same checks on Python 3.10 and 3.12.

## Conventions

See [AGENTS.md](AGENTS.md) for the full set of repo conventions (project
layout, how to add a new framework integration, the no-slop policy on
comments/abstractions). The short version:

- No untyped public functions — mypy strict mode is on.
- Tests for new behavior ship in the same PR, not as a follow-up.
- If you're adding a new framework integration, verify it against the
  *real* installed package (inspect its actual current API, test against
  it directly) rather than against a remembered or guessed API — this
  project's integrations have each found real bugs that way.
- Update [NOTES.md](NOTES.md) / [PLAN.md](PLAN.md) if you change product
  direction or architecture, so the docs don't drift from the code.

## Dashboard changes

The `dashboard/` app has its own checks:

```bash
cd dashboard
npx eslint .
npm run build
```

See [dashboard/README.md](dashboard/README.md) for env var setup.

## Questions

Open an [issue](https://github.com/rayaan2003/bastion/issues) — happy
to help you get oriented.
