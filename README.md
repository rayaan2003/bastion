# agentguard

Runtime policy enforcement for AI agent tool calls. Wraps the tools your
agent can call so every invocation passes through a policy engine first:
**allow**, **block**, or **require human approval** — with a full audit log
of every decision, for free.

This is the "firewall for agents" layer — not another prompt-injection
classifier, but enforcement on what agents are actually allowed to *do*.

## Status

Early / v0.1 — core policy engine, tool-call guard, and a LangGraph
integration. See [NOTES.md](NOTES.md) for the full product plan and roadmap.

## Install (local dev)

```bash
pip install -e ".[dev]"
# for the LangGraph integration:
pip install -e ".[langgraph]"
```

## Quickstart

```python
from agentguard import PolicyEngine, Rule, Action, guard
from agentguard.policy import arg_exceeds

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

Run the full demo:

```bash
python examples/basic_example.py
```

## Declarative (YAML) policy

Policies don't have to be hand-written Python — load them from a file so a
non-engineer reviewer can read and edit the rules:

```python
from agentguard import load_policy_from_yaml

policy = load_policy_from_yaml("policy.yaml")
```

See `examples/policy.yaml` for the schema and `examples/yaml_policy_example.py`
for a runnable demo.

## LangGraph integration

```python
from agentguard.integrations.langgraph import guarded_tool_node

tool_node = guarded_tool_node([my_tool_a, my_tool_b], policy=policy)
# use tool_node exactly where you'd use langgraph.prebuilt.ToolNode(tools)
```

A blocked or approval-denied call comes back as a normal error `ToolMessage`
(`handle_tool_errors=BlockedByPolicy`), so the agent can react to it instead
of the graph run crashing. See `examples/langgraph_demo.py`.

## Slack approval

```python
from agentguard.integrations.slack import SlackApprovalHandler

approval_handler = SlackApprovalHandler(
    token="xoxb-...",       # Slack bot token, needs chat:write + reactions:read scopes
    channel="#agent-approvals",
)
```

Posts a message and polls for a ✅/❌ reaction — no webhook server required.
Denies by default if nobody responds within `timeout` seconds (fail-closed).

## Tests

```bash
pytest
```
