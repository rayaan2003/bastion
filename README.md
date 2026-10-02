<div align="center">

<img width="100%" src="https://capsule-render.vercel.app/api?type=waving&color=0:1a1a2e,100:16213e&height=200&section=header&text=bastion&fontSize=70&fontColor=ffffff&desc=A%20firewall%20for%20what%20your%20AI%20agents%20are%20allowed%20to%20do&descSize=18&descAlignY=62&animation=fadeIn" alt="bastion"/>

<img src="https://readme-typing-svg.demolab.com/?font=Fira+Code&size=18&pause=1200&color=5B8DEF&center=true&vCenter=true&width=600&lines=Block+a+tool+call+before+it+runs.;Require+a+human+for+the+risky+ones.;Audit+every+decision%2C+for+free." alt="Typing SVG" />

<br/>

[![CI](https://github.com/rayaan2003/bastion/actions/workflows/ci.yml/badge.svg)](https://github.com/rayaan2003/bastion/actions/workflows/ci.yml)
[![License: Apache 2.0](https://img.shields.io/badge/license-Apache%202.0-blue.svg)](LICENSE)
[![Python 3.10+](https://img.shields.io/badge/python-3.10%2B-3776AB?logo=python&logoColor=white)](pyproject.toml)
[![Type checked: mypy strict](https://img.shields.io/badge/mypy-strict-2A6DB2.svg)](pyproject.toml)
[![PyPI](https://img.shields.io/badge/pypi-coming%20soon-yellow.svg)](CHANGELOG.md)

**[Quickstart](#quickstart)** · **[Framework integrations](#framework-integrations)** · **[Dashboard](#dashboard)** · **[Live demo](https://bastion-dashboard-two.vercel.app)** · **[Why](#why)**

</div>

---

## Why

AI agents are shipping fast and getting real permissions — deleting
records, sending emails, moving money, running shell commands. Most teams
have zero enforcement between "the model decided to call a tool" and "the
tool ran." bastion sits in that gap:

```
 agent decides to call a tool
          │
          ▼
    ┌──────────┐      allow    ──▶  tool runs
    │ bastion  │      block    ──▶  denied, agent sees why
    │  policy  │      approve  ──▶  human reviews (Slack / dashboard / console)
    └──────────┘
          │
          ▼
   every decision logged
```

Not another prompt-injection classifier — enforcement on what agents are
actually allowed to **do**.

## What you get

| | |
|---|---|
| 🛡️ **Policy engine** | Allow / block / require-approval rules, glob-matched tool names, conditions on args (`amount > 500`, regex match, contains-PII, ...) |
| ✅ **Human-in-the-loop** | Console prompt, Slack (reaction-based, no webhook server), or the hosted dashboard — pluggable |
| 📝 **Audit log, for free** | Every decision recorded automatically — JSONL locally or shipped to the dashboard |
| 🔍 **PII/secrets scanning** | Regex-based (no ML model to download) — emails, SSNs, Luhn-validated credit cards, cloud credentials, private keys |
| 📄 **Declarative policy** | Rules in YAML, editable by a non-engineer reviewer — by hand or from the dashboard's `/policy` page |
| 🔌 **3 framework integrations** | LangGraph, OpenAI Agents SDK, Claude Agent SDK — one line to wrap your tools |
| 📊 **Dashboard** | Audit log, approval queue, and a policy editor — a real Next.js app |

## Quickstart

> Not on PyPI yet (see the badge above) — install from source for now:
> `pip install git+https://github.com/rayaan2003/bastion.git`

```python
from bastion import PolicyEngine, Rule, Action, guard
from bastion.policy import arg_exceeds

policy = PolicyEngine()
policy.add_rule(Rule(tool_pattern="delete_*", action=Action.BLOCK, reason="irreversible"))
policy.add_rule(Rule(
    tool_pattern="transfer_funds",
    action=Action.APPROVE,
    condition=arg_exceeds("amount", 500),
    reason="large transfers need a human",
))

def transfer_funds(account: str, amount: float) -> str:
    return f"sent ${amount} to {account}"

guarded = guard(transfer_funds, policy=policy)
guarded(account="acct_1", amount=600)  # prompts for approval in the terminal
```

```bash
python examples/basic_example.py   # runs the full demo above
```

Rules can also live in YAML instead of hand-written Python:

```python
from bastion import load_policy_from_yaml
policy = load_policy_from_yaml("policy.yaml")
```

See [`examples/policy.yaml`](examples/policy.yaml) for the schema.

## Framework integrations

<details>
<summary><b>LangGraph</b></summary>

```python
from bastion.integrations.langgraph import guarded_tool_node

tool_node = guarded_tool_node([my_tool_a, my_tool_b], policy=policy)
# use tool_node exactly where you'd use langgraph.prebuilt.ToolNode(tools)
```

A blocked or approval-denied call comes back as a normal error `ToolMessage`
(`handle_tool_errors=BlockedByPolicy`), so the agent can react to it instead
of the graph run crashing. See [`examples/langgraph_demo.py`](examples/langgraph_demo.py).

```bash
pip install "bastion[langgraph]"
```
</details>

<details>
<summary><b>OpenAI Agents SDK</b></summary>

```python
from bastion.integrations.openai_agents import guarded_tools

agent = Agent(name="...", tools=guarded_tools([my_tool_a, my_tool_b], policy=policy))
```

A blocked or approval-denied call returns a descriptive string as the
tool's result (`"Tool call blocked by policy: <reason>"`) rather than
raising — the same idiom the SDK itself uses when a tool raises an
exception, so the model sees why and can react. See
[`examples/openai_agents_demo.py`](examples/openai_agents_demo.py).

```bash
pip install "bastion[openai-agents]"
```
</details>

<details>
<summary><b>Claude Agent SDK</b></summary>

```python
from claude_agent_sdk import ClaudeAgentOptions
from bastion.integrations.claude_agent_sdk import guarded_can_use_tool

options = ClaudeAgentOptions(can_use_tool=guarded_can_use_tool(policy=policy))
```

Hooks into the SDK's own permission system (`can_use_tool`), which it calls
for **every** tool invocation — built-in tools (Bash, Read, Write, ...) and
custom tools registered via `create_sdk_mcp_server` alike. Unlike the other
two integrations, nothing needs wrapping per-tool — one callback covers
everything. See [`examples/claude_agent_sdk_demo.py`](examples/claude_agent_sdk_demo.py).

```bash
pip install "bastion[claude-agent-sdk]"
```
</details>

## PII / secrets scanning

```python
from bastion import Rule, Action, contains_pii, enforce_text_policy

policy.add_rule(Rule(
    tool_pattern="*",
    action=Action.BLOCK,
    condition=contains_pii(["ssn_us", "credit_card"]),
    reason="tool call args contain PII/secrets",
))

# directly on an LLM response, outside the tool-call path:
enforce_text_policy(llm_output, categories=["email"], on_detect="redact")
```

Also available as a YAML condition type (`type: contains_pii`). See
[`examples/pii_scanning_example.py`](examples/pii_scanning_example.py).

## Slack approval

```python
from bastion.integrations.slack import SlackApprovalHandler

approval_handler = SlackApprovalHandler(
    token="xoxb-...",       # needs chat:write + reactions:read scopes
    channel="#agent-approvals",
)
```

Posts a message and polls for a ✅/❌ reaction — no webhook server required.
Fails closed (denies) if nobody responds within `timeout` seconds.

## Dashboard

<div align="center">
<a href="https://bastion-dashboard-two.vercel.app"><b>→ Live demo</b></a>
</div>

A real Next.js app (`dashboard/`) — audit log, approval queue, and a
policy editor, all wired to the SDK over HTTP:

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
```

The dashboard UI is behind a separate session login (not this API key) —
see [`dashboard/README.md`](dashboard/README.md) for the full auth model
and self-hosting setup.

## Install

```bash
pip install bastion@git+https://github.com/rayaan2003/bastion.git
# with a framework integration:
pip install "bastion[langgraph]@git+https://github.com/rayaan2003/bastion.git"
```

For local development (editable install, running the test suite), see
[CONTRIBUTING.md](CONTRIBUTING.md). Will switch to plain `pip install
bastion` once published — see [CHANGELOG.md](CHANGELOG.md).

## Tests

```bash
ruff check . && mypy src && pytest -q
```

Framework integration tests run against the **real installed package** for
each framework, never a mock — see [AGENTS.md](AGENTS.md) for why that's a
hard rule here.

## Project status

Pre-1.0. Core SDK, all three framework integrations, and the dashboard are
built and tested — see [CHANGELOG.md](CHANGELOG.md) for what's shipped and
[PLAN.md](PLAN.md) for what's next. Not yet on PyPI; install from source
for now (see [CONTRIBUTING.md](CONTRIBUTING.md)).

## Contributing

Issues and PRs welcome — see [CONTRIBUTING.md](CONTRIBUTING.md). Found a
security issue? See [SECURITY.md](SECURITY.md) instead of opening a public
issue for it.

## License

[Apache 2.0](LICENSE)

<div align="center">
<img width="100%" src="https://capsule-render.vercel.app/api?type=waving&color=0:16213e,100:1a1a2e&height=100&section=footer" alt=""/>
</div>
