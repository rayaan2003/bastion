"""Claude Agent SDK demo — bastion enforcing policy through a PreToolUse hook.

Requires: pip install bastionguard[claude-agent-sdk]

Running a full query (claude_agent_sdk.query(...) / ClaudeSDKClient) shells
out to the Claude Code CLI and needs it installed and authenticated. This
script shows the wiring and calls the hook directly, the same way the SDK
does when the CLI asks it about a tool call — see
tests/test_claude_agent_sdk_integration.py for the full behavior.

Run: python examples/claude_agent_sdk_demo.py
"""

import asyncio

from claude_agent_sdk import ClaudeAgentOptions

from bastion import Action, AuditLogger, PolicyEngine, Rule
from bastion.integrations.claude_agent_sdk import guarded_pre_tool_use


def build_options() -> ClaudeAgentOptions:
    policy = PolicyEngine()
    policy.add_rule(Rule(
        tool_pattern="Bash",
        action=Action.BLOCK,
        reason="no shell access for this agent",
    ))
    policy.add_rule(Rule(
        tool_pattern="mcp__*__delete_*",
        action=Action.BLOCK,
        reason="irreversible action, blocked by default policy",
    ))

    audit = AuditLogger(log_path="examples/claude_agent_sdk_audit.jsonl")
    hook = guarded_pre_tool_use(policy=policy, audit=audit)

    # A PreToolUse hook sees every tool call, even with allowed_tools or
    # permission_mode="bypassPermissions" set.
    return ClaudeAgentOptions(
        hooks={"PreToolUse": [hook]},
        allowed_tools=["Read", "Bash"],
    )


async def main() -> None:
    options = build_options()
    assert options.hooks is not None
    [callback] = options.hooks["PreToolUse"][0].hooks
    print("Built ClaudeAgentOptions with a bastion PreToolUse hook.")

    for tool_name, tool_input in [
        ("Read", {"file_path": "/etc/hosts"}),
        ("Bash", {"command": "rm -rf /"}),
    ]:
        hook_input = {
            "hook_event_name": "PreToolUse",
            "session_id": "demo",
            "transcript_path": "",
            "cwd": ".",
            "tool_name": tool_name,
            "tool_input": tool_input,
            "tool_use_id": "toolu_demo",
        }
        result = await callback(hook_input, "toolu_demo", {"signal": None})
        print(f"{tool_name} ->", result or "no objection")

    print("\nRun a real query via claude_agent_sdk.query(options=options, ...) "
          "with the Claude Code CLI installed to execute for real.")


if __name__ == "__main__":
    asyncio.run(main())
