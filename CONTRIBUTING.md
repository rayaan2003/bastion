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
- Add a [CHANGELOG.md](CHANGELOG.md) entry under `[Unreleased]`, and update
  [docs/architecture.md](docs/architecture.md) if you change a design
  decision, so the docs don't drift from the code.

## Dashboard changes

The `dashboard/` app has its own checks:

```bash
cd dashboard
npm ci
npx eslint .
npm run build
```

See [dashboard/README.md](dashboard/README.md) for env var setup.

CI's `dashboard-e2e` job also runs `tests/e2e/` — the Python SDK against a
built dashboard and a Postgres container, starting from a database in the
v0.1.0 schema so the startup migrations are tested. Those tests skip locally
unless `BASTION_E2E_URL` points at a running dashboard.

## Questions

Open an [issue](https://github.com/rayaan2003/bastion/issues) — happy
to help you get oriented.
