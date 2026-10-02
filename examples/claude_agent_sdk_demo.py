"""Claude Agent SDK demo — guarded_can_use_tool wired into ClaudeAgentOptions.

Requires: pip install agentguard[claude-agent-sdk]

Running a full query (claude_agent_sdk.query(...) / ClaudeSDKClient) shells
out to the Claude Code CLI and needs it installed and authenticated. This
script shows the wiring and calls the callback directly (the same way the
SDK calls it internally) to prove it works without needing that CLI - see
tests/test_claude_agent_sdk_integration.py for the full allow/block/approve
behavior.

Run: python examples/claude_agent_sdk_demo.py
"""

import asyncio

from claude_agent_sdk import ClaudeAgentOptions, ToolPermissionContext

from agentguard import Action, AuditLogger, PolicyEngine, Rule
from agentguard.integrations.claude_agent_sdk import guarded_can_use_tool


def build_options() -> ClaudeAgentOptions:
    policy = PolicyEngine()
    policy.add_rule(Rule(
        tool_pattern="Bash",
        action=Action.BLOCK,
        reason="no shell access for this agent",
    ))
    policy.add_rule(Rule(
        tool_pattern="delete_*",
        action=Action.BLOCK,
        reason="irreversible action, blocked by default policy",
    ))

    audit = AuditLogger(log_path="examples/claude_agent_sdk_audit.jsonl")
    can_use_tool = guarded_can_use_tool(policy=policy, audit=audit)

    # One callback covers every tool call the agent makes - built-in
    # (Bash, Read, Write, ...) and custom MCP tools alike.
    return ClaudeAgentOptions(can_use_tool=can_use_tool)


async def main() -> None:
    options = build_options()
    print("Built ClaudeAgentOptions with a guarded can_use_tool callback.")

    # Call it the same way the SDK does internally, no CLI/network needed.
    ctx = ToolPermissionContext()
    allowed = await options.can_use_tool("Read", {"file_path": "/etc/hosts"}, ctx)
    blocked = await options.can_use_tool("Bash", {"command": "rm -rf /"}, ctx)
    print("Read ->", allowed)
    print("Bash ->", blocked)

    print("\nRun a real query via claude_agent_sdk.query(options=options, ...) "
          "with the Claude Code CLI installed to execute for real.")


if __name__ == "__main__":
    asyncio.run(main())
