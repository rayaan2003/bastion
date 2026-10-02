"""OpenAI Agents SDK demo — guarded tools wired into an Agent.

Requires: pip install bastion[openai-agents]

Running the full agent loop needs an OpenAI API key (Runner.run calls the
model). This script shows the wiring; see tests/test_openai_agents_integration.py
for the guard behavior itself (allow/block/approve) verified by invoking
tools directly against the real `agents` package, no API key needed.

Run: python examples/openai_agents_demo.py
"""

from agents import Agent, function_tool

from bastion import Action, AuditLogger, PolicyEngine, Rule
from bastion.integrations.openai_agents import guarded_tools
from bastion.policy import any_arg_contains


@function_tool
def search_docs(query: str) -> str:
    """Search internal docs for a query."""
    return f"3 results for '{query}'"


@function_tool
def send_email(to: str, subject: str, body: str) -> str:
    """Send an email."""
    return f"sent to {to}"


@function_tool
def delete_user(user_id: str) -> str:
    """Delete a user account. Irreversible."""
    return f"deleted {user_id}"


def build_agent() -> Agent:
    policy = PolicyEngine()
    policy.add_rule(Rule(
        tool_pattern="delete_*",
        action=Action.BLOCK,
        reason="irreversible action, blocked by default policy",
    ))
    policy.add_rule(Rule(
        tool_pattern="send_email",
        action=Action.APPROVE,
        condition=any_arg_contains(["all-staff", "external"]),
        reason="broad-distribution emails require approval",
    ))

    audit = AuditLogger(log_path="examples/openai_agents_audit.jsonl")
    tools = guarded_tools([search_docs, send_email, delete_user], policy=policy, audit=audit)

    return Agent(name="support-agent", instructions="Help the user.", tools=tools)


if __name__ == "__main__":
    agent = build_agent()
    print(f"Built agent '{agent.name}' with {len(agent.tools)} guarded tools.")
    print("Run via agents.Runner.run(agent, ...) with an OPENAI_API_KEY set to execute for real.")
