"""OpenAI Agents SDK integration.

Usage:

    from agentguard import PolicyEngine, Rule, Action
    from agentguard.integrations.openai_agents import guarded_tools

    policy = PolicyEngine()
    policy.add_rule(Rule(tool_pattern="delete_*", action=Action.BLOCK, reason="destructive"))

    agent = Agent(name="support-agent", tools=guarded_tools([my_tool_a, my_tool_b], policy=policy))

A blocked or approval-denied call does not raise — it returns a descriptive
string as the tool's result (`"Tool call blocked by policy: <reason>"`),
same idiom the SDK itself uses for a tool that raised an exception, so the
model sees why and can react instead of the run crashing.

Note: `ApprovalHandler.request_approval` is synchronous/blocking (same
interface used by the console, Slack and dashboard handlers). The Agents
SDK's tool invocation is async, so an approval wait here blocks the event
loop for its duration — fine for a single agent run, worth knowing if
you're running many agents concurrently on one loop.

Requires the `openai-agents` extra: pip install agentguard[openai-agents]
"""

from __future__ import annotations

import dataclasses
import json
from collections.abc import Iterable
from typing import TYPE_CHECKING, Any

from agentguard.approval import ApprovalHandler, ConsoleApprovalHandler
from agentguard.audit import AuditLogger
from agentguard.guard import evaluate_and_record
from agentguard.policy import PolicyEngine

if TYPE_CHECKING:
    from agents import FunctionTool


def guarded_tools(
    tools: Iterable[Any],
    *,
    policy: PolicyEngine,
    audit: AuditLogger | None = None,
    approval_handler: ApprovalHandler | None = None,
) -> list[FunctionTool]:
    """Wrap a list of `agents.FunctionTool` objects (as produced by
    `@function_tool`) with policy enforcement. Returns new tool objects;
    the originals passed in are not mutated.
    """
    try:
        from agents import FunctionTool
    except ImportError as e:
        raise ImportError(
            "openai-agents is required for this integration. "
            "Install with: pip install agentguard[openai-agents]"
        ) from e

    audit = audit or AuditLogger()
    approval_handler = approval_handler or ConsoleApprovalHandler()

    wrapped: list[FunctionTool] = []
    for tool in tools:
        if not isinstance(tool, FunctionTool):
            raise TypeError(
                f"Don't know how to guard tool of type {type(tool)!r} — expected "
                "agents.FunctionTool (from @function_tool)."
            )
        wrapped.append(
            _guard_function_tool(
                tool, policy=policy, audit=audit, approval_handler=approval_handler
            )
        )
    return wrapped


def _guard_function_tool(
    tool: FunctionTool,
    *,
    policy: PolicyEngine,
    audit: AuditLogger,
    approval_handler: ApprovalHandler,
) -> FunctionTool:
    original_invoke = tool.on_invoke_tool
    tool_name = tool.name

    async def guarded_invoke(ctx: Any, input_str: str) -> Any:
        try:
            call_args = json.loads(input_str) if input_str else {}
        except (TypeError, ValueError):
            call_args = {"_raw": input_str}

        allowed, reason = evaluate_and_record(
            tool_name, call_args, policy=policy, audit=audit, approval_handler=approval_handler
        )
        if not allowed:
            return f"Tool call blocked by policy: {reason}"

        return await original_invoke(ctx, input_str)

    return dataclasses.replace(tool, on_invoke_tool=guarded_invoke)
