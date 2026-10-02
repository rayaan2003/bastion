"""Wraps tool callables so every invocation passes through the policy engine
before it actually executes.

This is framework-agnostic: any Python callable works. Framework-specific
helpers (e.g. for LangGraph tool objects) live in bastion.integrations.*
and call back into `guard()`.
"""

from __future__ import annotations

import functools
import inspect
from collections.abc import Callable, Iterable
from typing import Any

from bastion.approval import ApprovalHandler, ConsoleApprovalHandler
from bastion.audit import AuditLogger
from bastion.policy import Action, PolicyEngine


class BlockedByPolicy(Exception):
    def __init__(self, tool_name: str, reason: str):
        self.tool_name = tool_name
        self.reason = reason
        super().__init__(f"Tool call '{tool_name}' blocked by policy: {reason}")


def evaluate_and_record(
    tool_name: str,
    args: dict[str, Any],
    *,
    policy: PolicyEngine,
    audit: AuditLogger,
    approval_handler: ApprovalHandler,
) -> tuple[bool, str]:
    """Evaluate policy for a tool call, consult the approval handler if the
    rule says to, and record the outcome to the audit log either way.

    Returns (allowed, reason). Shared by `guard()` and the framework
    integrations (LangGraph wraps tools directly so doesn't need this;
    OpenAI Agents SDK and Claude Agent SDK do) so the actual policy/audit/
    approval logic lives in exactly one place. What happens when not
    allowed — raise, return an error string, etc. — differs per framework,
    so that decision is left to the caller.
    """
    decision = policy.evaluate(tool_name, args)

    if decision.action == Action.BLOCK:
        audit.record(tool_name, args, "blocked", decision.reason)
        return False, decision.reason

    if decision.action == Action.APPROVE:
        approved = approval_handler.request_approval(tool_name, args, decision.reason)
        if not approved:
            reason = f"approval denied ({decision.reason})"
            audit.record(tool_name, args, "denied", decision.reason)
            return False, reason
        audit.record(tool_name, args, "approved", decision.reason)
        return True, decision.reason

    audit.record(tool_name, args, "allowed", decision.reason)
    return True, decision.reason


def guard(
    fn: Callable[..., Any],
    *,
    policy: PolicyEngine,
    audit: AuditLogger | None = None,
    approval_handler: ApprovalHandler | None = None,
    tool_name: str | None = None,
) -> Callable[..., Any]:
    """Wrap a single tool function with policy enforcement.

    On call: build an args dict from the call, evaluate the policy, then
    ALLOW (call through), BLOCK (raise BlockedByPolicy), or APPROVE (ask the
    approval_handler; proceed if approved, else raise BlockedByPolicy).
    Every outcome is recorded via `audit`.
    """
    name: str = tool_name if tool_name is not None else getattr(fn, "__name__", "unknown_tool")
    audit = audit or AuditLogger()
    approval_handler = approval_handler or ConsoleApprovalHandler()

    @functools.wraps(fn)
    def wrapper(*args: Any, **kwargs: Any) -> Any:
        call_args = _build_args_dict(fn, args, kwargs)
        allowed, reason = evaluate_and_record(
            name, call_args, policy=policy, audit=audit, approval_handler=approval_handler
        )
        if not allowed:
            raise BlockedByPolicy(name, reason)
        return fn(*args, **kwargs)

    return wrapper


def guard_tools(
    tools: Iterable[Any],
    *,
    policy: PolicyEngine,
    audit: AuditLogger | None = None,
    approval_handler: ApprovalHandler | None = None,
) -> list[Any]:
    """Wrap a list of tools. Handles plain callables and LangChain/LangGraph
    BaseTool-style objects (anything with a `.func` or `._run`/`.invoke`).

    For LangChain StructuredTool/BaseTool instances we wrap `.func` in place
    so the tool object itself (name, description, schema) is unchanged and
    still usable directly in a LangGraph tool node.
    """
    audit = audit or AuditLogger()
    approval_handler = approval_handler or ConsoleApprovalHandler()
    wrapped: list[Any] = []

    for tool in tools:
        if callable(tool) and not hasattr(tool, "func"):
            wrapped.append(
                guard(tool, policy=policy, audit=audit, approval_handler=approval_handler)
            )
            continue

        if hasattr(tool, "func") and callable(tool.func):
            tool_name = getattr(tool, "name", getattr(tool.func, "__name__", "unknown_tool"))
            tool.func = guard(
                tool.func,
                policy=policy,
                audit=audit,
                approval_handler=approval_handler,
                tool_name=tool_name,
            )
            wrapped.append(tool)
            continue

        raise TypeError(
            f"Don't know how to guard tool of type {type(tool)!r} — expected a "
            "callable or an object with a `.func` attribute (LangChain tool)."
        )

    return wrapped


def _build_args_dict(
    fn: Callable[..., Any], args: tuple[Any, ...], kwargs: dict[str, Any]
) -> dict[str, Any]:
    try:
        sig = inspect.signature(fn)
        bound = sig.bind_partial(*args, **kwargs)
        bound.apply_defaults()
        return dict(bound.arguments)
    except (TypeError, ValueError):
        return {"_args": args, **kwargs}
