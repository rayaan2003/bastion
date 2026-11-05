"""OpenAI Agents SDK integration.

Usage:

    from bastion import PolicyEngine, Rule, Action
    from bastion.integrations.openai_agents import guarded_tools

    policy = PolicyEngine()
    policy.add_rule(Rule(tool_pattern="delete_*", action=Action.BLOCK, reason="destructive"))

    agent = Agent(name="support-agent", tools=guarded_tools([my_tool_a, my_tool_b], policy=policy))

A blocked or approval-denied call does not raise — it returns a descriptive
string as the tool's result (`"Tool call blocked by policy: <reason>"`),
same idiom the SDK itself uses for a tool that raised an exception, so the
model sees why and can react instead of the run crashing.

Each call's outcome is audited as `completed` or `failed`. By default the
SDK's `@function_tool` turns an exception into an error-string result
(`failure_error_function`), so such errors show up as `completed`; pass
`failure_error_function=None` to have them raise and be audited as `failed`.

Note: `ApprovalHandler.request_approval` is synchronous/blocking (same
interface used by the console, Slack and dashboard handlers). The Agents
SDK's tool invocation is async, so an approval wait here blocks the event
loop for its duration — fine for a single agent run, worth knowing if
you're running many agents concurrently on one loop.

Requires the `openai-agents` extra: pip install bastionguard[openai-agents]
"""

from __future__ import annotations

import dataclasses
import json
import uuid
from collections.abc import Iterable
from typing import TYPE_CHECKING, Any

from bastion.approval import ApprovalHandler, ConsoleApprovalHandler
from bastion.audit import AuditLogger
from bastion.guard import describe_error, evaluate_and_record, record_outcome
from bastion.policy import PolicyEngine

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
            "Install with: pip install bastionguard[openai-agents]"
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

        call_id = getattr(ctx, "tool_call_id", None) or str(uuid.uuid4())
        allowed, reason = evaluate_and_record(
            tool_name,
            call_args,
            policy=policy,
            audit=audit,
            approval_handler=approval_handler,
            call_id=call_id,
        )
        if not allowed:
            return f"Tool call blocked by policy: {reason}"

        try:
            result = await original_invoke(ctx, input_str)
        except Exception as e:
            record_outcome(audit, tool_name, call_id, describe_error(e))
            raise
        record_outcome(audit, tool_name, call_id)
        return result

    return dataclasses.replace(tool, on_invoke_tool=guarded_invoke)
