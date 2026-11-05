"""Claude Agent SDK integration.

Usage:

    from claude_agent_sdk import ClaudeAgentOptions
    from bastion import PolicyEngine, Rule, Action
    from bastion.integrations.claude_agent_sdk import guarded_pre_tool_use

    policy = PolicyEngine()
    policy.add_rule(Rule(tool_pattern="Bash", action=Action.BLOCK, reason="no shell access"))

    options = ClaudeAgentOptions(hooks={"PreToolUse": [guarded_pre_tool_use(policy=policy)]})

`guarded_pre_tool_use()` is the one to use: a PreToolUse hook runs for every
tool call, built-in (Bash, Read, Write, ...) and MCP alike, whatever the
permission settings.

`guarded_can_use_tool()` hooks the SDK's permission prompt instead, which the
SDK skips for tools pre-allowed by `allowed_tools` or settings files and for
everything under `permission_mode="bypassPermissions"` — bastion never sees
those calls.

Requires the `claude-agent-sdk` extra: pip install bastionguard[claude-agent-sdk]
"""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING, Any

from bastion.approval import ApprovalHandler, ConsoleApprovalHandler
from bastion.audit import AuditLogger
from bastion.guard import evaluate_and_record
from bastion.policy import PolicyEngine

if TYPE_CHECKING:
    from claude_agent_sdk import (
        CanUseTool,
        HookContext,
        HookInput,
        HookJSONOutput,
        HookMatcher,
        ToolPermissionContext,
    )


def guarded_can_use_tool(
    *,
    policy: PolicyEngine,
    audit: AuditLogger | None = None,
    approval_handler: ApprovalHandler | None = None,
) -> CanUseTool:
    """Build a `can_use_tool` callback for `ClaudeAgentOptions`. Prefer
    `guarded_pre_tool_use()`, which the SDK can't skip — see module docstring.
    """
    try:
        from claude_agent_sdk import PermissionResultAllow, PermissionResultDeny
    except ImportError as e:
        raise ImportError(
            "claude-agent-sdk is required for this integration. "
            "Install with: pip install bastionguard[claude-agent-sdk]"
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
        return PermissionResultDeny(message=f"Blocked by bastion policy: {reason}")

    return can_use_tool


def guarded_pre_tool_use(
    *,
    policy: PolicyEngine,
    audit: AuditLogger | None = None,
    approval_handler: ApprovalHandler | None = None,
    timeout: float = 600.0,
) -> HookMatcher:
    """Build a PreToolUse `HookMatcher` that enforces policy on every tool
    call:

        ClaudeAgentOptions(hooks={"PreToolUse": [guarded_pre_tool_use(policy=policy)]})

    timeout: seconds the SDK waits for the hook. It has to cover an approval
    wait, so keep it above your approval handler's own timeout — the SDK's
    default of 60s would cut off a Slack or dashboard approval.

    The matcher fails closed (`on_failure="block"`): if the hook raises, the
    tool call is blocked, not allowed.
    """
    try:
        from claude_agent_sdk import HookMatcher
    except ImportError as e:
        raise ImportError(
            "claude-agent-sdk is required for this integration. "
            "Install with: pip install bastionguard[claude-agent-sdk]"
        ) from e

    audit = audit or AuditLogger()
    approval_handler = approval_handler or ConsoleApprovalHandler()

    async def pre_tool_use(
        input_data: HookInput, tool_use_id: str | None, context: HookContext
    ) -> HookJSONOutput:
        if input_data["hook_event_name"] != "PreToolUse":
            return {}

        # Approval handlers block until a human answers; run them on a worker
        # thread so the wait doesn't stall the SDK's event loop.
        allowed, reason = await asyncio.to_thread(
            evaluate_and_record,
            input_data["tool_name"],
            input_data["tool_input"],
            policy=policy,
            audit=audit,
            approval_handler=approval_handler,
        )
        if allowed:
            # No opinion rather than "allow": a PreToolUse allow also skips the
            # SDK's own permission checks, which bastion shouldn't override.
            return {}
        return {
            "hookSpecificOutput": {
                "hookEventName": "PreToolUse",
                "permissionDecision": "deny",
                "permissionDecisionReason": f"Blocked by bastion policy: {reason}",
            }
        }

    return HookMatcher(matcher=None, hooks=[pre_tool_use], timeout=timeout, on_failure="block")
