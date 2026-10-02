"""Claude Agent SDK integration.

Usage:

    from claude_agent_sdk import ClaudeAgentOptions
    from agentguard import PolicyEngine, Rule, Action
    from agentguard.integrations.claude_agent_sdk import guarded_can_use_tool

    policy = PolicyEngine()
    policy.add_rule(Rule(tool_pattern="Bash", action=Action.BLOCK, reason="no shell access"))

    options = ClaudeAgentOptions(can_use_tool=guarded_can_use_tool(policy=policy))

This hooks into the SDK's own permission system (`can_use_tool`), which the
SDK calls for every tool invocation — built-in tools (Bash, Read, Write,
...) and custom tools registered via `create_sdk_mcp_server` alike. Unlike
the LangGraph/OpenAI Agents integrations, nothing needs to be wrapped
per-tool; one callback covers everything. (The SDK only invokes
`can_use_tool` according to its own `permission_mode` semantics — consult
the SDK's docs for how that interacts with built-in auto-allow rules.)

Requires the `claude-agent-sdk` extra: pip install agentguard[claude-agent-sdk]
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from agentguard.approval import ApprovalHandler, ConsoleApprovalHandler
from agentguard.audit import AuditLogger
from agentguard.guard import evaluate_and_record
from agentguard.policy import PolicyEngine

if TYPE_CHECKING:
    from claude_agent_sdk import CanUseTool, ToolPermissionContext


def guarded_can_use_tool(
    *,
    policy: PolicyEngine,
    audit: AuditLogger | None = None,
    approval_handler: ApprovalHandler | None = None,
) -> CanUseTool:
    """Build a `can_use_tool` callback for `ClaudeAgentOptions`."""
    try:
        from claude_agent_sdk import PermissionResultAllow, PermissionResultDeny
    except ImportError as e:
        raise ImportError(
            "claude-agent-sdk is required for this integration. "
            "Install with: pip install agentguard[claude-agent-sdk]"
        ) from e

    audit = audit or AuditLogger()
    approval_handler = approval_handler or ConsoleApprovalHandler()

    async def can_use_tool(
        tool_name: str, input_data: dict[str, Any], context: ToolPermissionContext
    ) -> PermissionResultAllow | PermissionResultDeny:
        allowed, reason = evaluate_and_record(
            tool_name, input_data, policy=policy, audit=audit, approval_handler=approval_handler
        )
        if allowed:
            return PermissionResultAllow()
        return PermissionResultDeny(message=f"Blocked by agentguard policy: {reason}")

    return can_use_tool
