"""LangGraph integration.

Usage:

    from bastion import PolicyEngine, Rule, Action
    from bastion.integrations.langgraph import guarded_tool_node

    policy = PolicyEngine()
    policy.add_rule(Rule(tool_pattern="delete_*", action=Action.BLOCK, reason="destructive"))

    tool_node = guarded_tool_node([my_tool_a, my_tool_b], policy=policy)
    # use tool_node in your StateGraph exactly as you would ToolNode(tools)

Requires the `langgraph` extra: pip install bastion[langgraph]
"""

from __future__ import annotations

from collections.abc import Iterable
from typing import TYPE_CHECKING, Any

from bastion.approval import ApprovalHandler
from bastion.audit import AuditLogger
from bastion.guard import BlockedByPolicy, guard_tools
from bastion.policy import PolicyEngine

if TYPE_CHECKING:
    from langgraph.prebuilt import ToolNode


def guarded_tool_node(
    tools: Iterable[Any],
    *,
    policy: PolicyEngine,
    audit: AuditLogger | None = None,
    approval_handler: ApprovalHandler | None = None,
) -> ToolNode:
    """Return a LangGraph ToolNode built from policy-wrapped tools.

    This is a drop-in replacement for `langgraph.prebuilt.ToolNode(tools)` —
    every tool call the graph makes through the returned node passes through
    the policy engine first.

    A blocked or approval-denied call raises `BlockedByPolicy`. `ToolNode`
    is configured to catch that specifically and turn it into an error
    `ToolMessage` (`handle_tool_errors=BlockedByPolicy`), so the agent sees
    "this action was denied" as a normal tool result and can react to it —
    the graph run doesn't crash. Any other exception still propagates.
    """
    try:
        from langgraph.prebuilt import ToolNode
    except ImportError as e:
        raise ImportError(
            "langgraph is required for this integration. "
            "Install with: pip install bastion[langgraph]"
        ) from e

    wrapped_tools = guard_tools(
        tools, policy=policy, audit=audit, approval_handler=approval_handler
    )
    return ToolNode(wrapped_tools, handle_tool_errors=BlockedByPolicy)
