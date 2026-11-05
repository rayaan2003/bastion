# bastion

[![PyPI](https://img.shields.io/pypi/v/bastionguard.svg)](https://pypi.org/project/bastionguard/)
[![CI](https://github.com/rayaan2003/bastion/actions/workflows/ci.yml/badge.svg)](https://github.com/rayaan2003/bastion/actions/workflows/ci.yml)
[![Python](https://img.shields.io/pypi/pyversions/bastionguard.svg)](https://pypi.org/project/bastionguard/)
[![License](https://img.shields.io/badge/license-Apache%202.0-blue.svg)](LICENSE)

Policy enforcement for AI agent tool calls. Before a tool runs, bastion
decides whether the agent may call it, needs a human to approve it, or is
blocked — and logs the decision.

It runs in your agent's process, works with LangGraph, the OpenAI Agents
SDK and the Claude Agent SDK, and has no dependencies beyond PyYAML.

```python
from bastion import Action, PolicyEngine, Rule, guard
from bastion.policy import arg_exceeds

policy = PolicyEngine()
policy.add_rule(Rule("delete_*", Action.BLOCK, reason="irreversible"))
policy.add_rule(Rule(
    "refund",
    Action.APPROVE,
    condition=arg_exceeds("amount", 100),
    reason="refunds over $100 need a human",
))

refund = guard(refund, policy=policy)
delete_customer = guard(delete_customer, policy=policy)
```

```text
>>> refund(order_id="ord_1", amount=40)
'refunded $40 on ord_1'
>>> refund(order_id="ord_2", amount=250)       # reviewer says no
BlockedByPolicy: Tool call 'refund' blocked by policy: approval denied (refunds over $100 need a human)
>>> delete_customer(customer_id="cus_9")
BlockedByPolicy: Tool call 'delete_customer' blocked by policy: irreversible
```

## Install

```bash
pip install bastionguard
```

The package is `bastionguard` on PyPI; the import is `bastion`. Framework
and Slack support are extras:

```bash
pip install "bastionguard[langgraph]"          # or openai-agents, claude-agent-sdk, slack
```

Python 3.10+.

## Policies

A policy is an ordered list of rules. Each rule matches a tool name (glob
pattern) and, optionally, a condition on the call's arguments. The first
matching rule decides; if nothing matches, `default_action` applies
(`allow` unless you set it).

| Action | Effect |
|---|---|
| `allow` | the tool runs |
| `block` | the tool doesn't run; the agent gets the reason |
| `approve` | an approval handler asks a human; runs only if approved |

Policies can live in YAML, so they can be reviewed without reading Python:

```yaml
# policy.yaml
default_action: allow

rules:
  - name: no-deletes
    tool: "delete_*"
    action: block
    reason: irreversible

  # Allow-list by ordering: internal mail goes through, anything else needs a human.
  - tool: send_email
    action: allow
    condition: { type: arg_matches_regex, arg: to, pattern: '^[^@\s]+@yourco\.com$' }
  - tool: send_email
    action: approve
    reason: external recipient

  - tool: "*"
    action: block
    reason: arguments contain PII or credentials
    condition: { type: contains_pii, categories: [ssn_us, credit_card, aws_secret_access_key] }
```

```python
from bastion import load_policy_from_yaml
policy = load_policy_from_yaml("policy.yaml")
```

Built-in conditions:

| YAML `type` | Python | Matches when |
|---|---|---|
| `arg_exceeds` | `arg_exceeds(arg, threshold)` | the argument is a number above `threshold` |
| `arg_matches_regex` | `arg_matches_regex(arg, pattern)` | the argument matches `pattern` |
| `any_arg_contains` | `any_arg_contains(substrings)` | any argument contains one of `substrings` (case-insensitive) |
| `contains_pii` | `contains_pii(categories)` | any argument contains a detected [PII/secret](#piisecrets-scanning) |

In Python, a condition is any `Callable[[dict], bool]` over the arguments.

### Shadow mode

Run a policy against real traffic before it's allowed to block anything.
Shadow rules are evaluated and logged as `would_block`, `would_approve` or
`would_allow`, but not enforced, and they never ask a human.

```yaml
shadow: true          # the whole policy
rules:
  - tool: "send_*"
    action: approve
    shadow: true      # or a single rule inside an enforced policy
```

A shadow rule can't change what's enforced: evaluation moves past it to the
rules behind it.

## Frameworks

**LangGraph** — a drop-in replacement for `ToolNode`. A blocked call comes
back as an error `ToolMessage`, so the agent can react instead of the graph
crashing. Sync and async tools are both covered.

```python
from bastion.integrations.langgraph import guarded_tool_node

tool_node = guarded_tool_node([search_docs, send_email], policy=policy)
```

**OpenAI Agents SDK** — wraps `@function_tool` tools. A blocked call returns
`"Tool call blocked by policy: <reason>"` as the tool result.

```python
from bastion.integrations.openai_agents import guarded_tools

agent = Agent(name="support", tools=guarded_tools([search_docs, send_email], policy=policy))
```

**Claude Agent SDK** — a `PreToolUse` hook. It sees every tool call,
built-in (Bash, Write, ...) and MCP alike, including tools pre-allowed by
`allowed_tools` and under `permission_mode="bypassPermissions"`. A blocked
call is denied with the reason; an allowed one is left to the SDK's normal
permission checks. If the hook itself fails, the call is blocked.

```python
from bastion.integrations.claude_agent_sdk import guarded_pre_tool_use

options = ClaudeAgentOptions(hooks={"PreToolUse": [guarded_pre_tool_use(policy=policy)]})
```

Keep the hook's `timeout` (default 600s) above your approval handler's,
or the SDK stops waiting before the reviewer answers.

**Anything else** — `guard(fn, policy=...)` wraps any callable, sync or
async, and raises `BlockedByPolicy`.

Runnable versions of each are in [`examples/`](examples).

## Approvals

`approve` rules call an `ApprovalHandler`. The default prompts in the
terminal. The Slack and dashboard handlers deny if nobody answers before
the timeout.

```python
from bastion.approval.slack import SlackApprovalHandler

# Posts to the channel and waits for a ✅ or ❌ reaction. Needs a bot token
# with chat:write and reactions:read; no webhook server.
approvals = SlackApprovalHandler(token="xoxb-...", channel="#agent-approvals", timeout=300)
guarded = guard(refund, policy=policy, approval_handler=approvals)
```

The [dashboard](#dashboard) provides an approval queue as well
(`DashboardApprovalHandler`). For your own channel, subclass
`ApprovalHandler` and implement `request_approval(tool_name, args, reason) -> bool`.

## Audit log

Every decision is recorded. By default it's appended to
`bastion_audit.jsonl`:

```json
{
  "id": "5c183b31-6364-4dca-b154-599220c73ba3",
  "timestamp": 1793897709.573623,
  "session_id": "sess_7f3a",
  "tool_name": "delete_customer",
  "args": {"customer_id": "cus_9"},
  "action": "blocked",
  "reason": "irreversible"
}
```

`action` is one of `allowed`, `blocked`, `approved`, `denied`, or
`would_*` for shadow rules. To send events elsewhere, pass any
`Callable[[AuditEvent], None]`:

```python
from bastion import AuditLogger
audit = AuditLogger(session_id="run-42", sink=my_sink)
guarded = guard(refund, policy=policy, audit=audit)
```

## PII/secrets scanning

Regex detectors for `email`, `phone_us`, `ssn_us`, `credit_card` (Luhn
checked), `aws_access_key_id`, `aws_secret_access_key`, `generic_api_key`
(OpenAI, GitHub, Slack token formats) and `private_key_block`. Use them as
a policy condition (`contains_pii`, above), or directly on any text such as
a model response:

```python
from bastion import enforce_text_policy

safe = enforce_text_policy(llm_output, categories=["email", "ssn_us"], on_detect="redact")
# "contact [REDACTED:email]"
```

These are patterns, not a DLP classifier: they catch the common, expensive
leaks and will miss things.

## Dashboard

[`dashboard/`](dashboard) is a self-hosted Next.js + Postgres app with an
audit log viewer, an approval queue and a policy editor. The SDK talks to
it over HTTP with an API key:

```python
from bastion.dashboard import (
    DashboardApprovalHandler,
    dashboard_audit_sink,
    load_policy_from_dashboard,
)

url, key = "https://bastion.yourco.internal", "..."
policy = load_policy_from_dashboard(url, key)
audit = AuditLogger(sink=dashboard_audit_sink(url, key))
approvals = DashboardApprovalHandler(url, key)
```

Audit events are sent on a background thread, so a slow or unreachable
dashboard doesn't hold up tool calls. Setup and deployment:
[dashboard/README.md](dashboard/README.md).

## Status

Pre-1.0: the API may still change between minor versions, and changes are
listed in [CHANGELOG.md](CHANGELOG.md). Next up is in
[docs/roadmap.md](docs/roadmap.md), and how it's built is in
[docs/architecture.md](docs/architecture.md).

Known limitations:

- Approval handlers are synchronous. The Claude Agent SDK hook runs them
  on a worker thread, but with the OpenAI Agents SDK a pending approval
  blocks the event loop.
- The dashboard has one shared login and one API key; there are no users
  or projects yet.

## Contributing

Issues and PRs are welcome — see [CONTRIBUTING.md](CONTRIBUTING.md). Report
security issues privately as described in [SECURITY.md](SECURITY.md).

## License

[Apache 2.0](LICENSE)
