"""Wraps tool callables so every invocation passes through the policy engine
before it actually executes.

This is framework-agnostic: any Python callable works. Framework-specific
helpers (e.g. for LangGraph tool objects) live in bastion.integrations.*
and call back into `guard()`.
"""

from __future__ import annotations

import asyncio
import functools
import inspect
import uuid
from collections.abc import Callable, Iterable
from concurrent.futures import ThreadPoolExecutor
from typing import Any

from bastion.approval import (
    ApprovalDecision,
    ApprovalHandler,
    ApprovalRequest,
    ConsoleApprovalHandler,
)
from bastion.audit import AuditLogger
from bastion.policy import Action, PolicyEngine
from bastion.scanning import redact


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
    call_id: str | None = None,
) -> tuple[bool, str]:
    """Evaluate policy for a tool call, consult the approval handler if the
    rule says to, and record the outcome to the audit log either way.

    Every event is recorded under `call_id` (generated if omitted); pass the
    same id to `record_outcome()` once an allowed tool has run.

    Returns (allowed, reason). Shared by `guard()` and the framework
    integrations so the actual policy/audit/approval logic lives in exactly
    one place. What happens when not allowed — raise, return an error
    string, etc. — differs per framework, so that decision is left to the
    caller. Async callers use `evaluate_and_record_async()`.
    """
    request, settle = _evaluate(tool_name, args, policy=policy, audit=audit, call_id=call_id)
    return settle(approval_handler.request_approval(request) if request else None)


async def evaluate_and_record_async(
    tool_name: str,
    args: dict[str, Any],
    *,
    policy: PolicyEngine,
    audit: AuditLogger,
    approval_handler: ApprovalHandler,
    call_id: str | None = None,
) -> tuple[bool, str]:
    """`evaluate_and_record()` for code running on an event loop.

    Approval handlers block until a human answers, so the wait runs on a
    worker thread and other tool calls on the loop keep going.
    """
    request, settle = _evaluate(tool_name, args, policy=policy, audit=audit, call_id=call_id)
    if request is None:
        return settle(None)
    loop = asyncio.get_running_loop()
    answer = await loop.run_in_executor(_approval_waits, approval_handler.request_approval, request)
    return settle(answer)


# Not the loop's default executor: that pool is small and shared (the OpenAI
# Agents SDK runs sync tools on it), and a pending approval can hold a thread
# for minutes.
_approval_waits = ThreadPoolExecutor(max_workers=32, thread_name_prefix="bastion-approval")


def _evaluate(
    tool_name: str,
    args: dict[str, Any],
    *,
    policy: PolicyEngine,
    audit: AuditLogger,
    call_id: str | None,
) -> tuple[ApprovalRequest | None, Callable[[ApprovalDecision | None], tuple[bool, str]]]:
    """Evaluate policy and return the approval request it needs (None if it
    needs none) and a function that records and returns the final outcome
    once the caller has the approval decision."""
    call_id = call_id or str(uuid.uuid4())
    decision = policy.evaluate(tool_name, args)

    def record(action: str, reason: str, approver: str = "") -> None:
        audit.record(tool_name, args, action, reason, call_id=call_id, approver=approver)

    if decision.shadow is not None:
        record(f"would_{decision.shadow.action.value}", decision.shadow.reason)

    request = None
    if decision.action == Action.APPROVE:
        request = ApprovalRequest(
            tool_name=tool_name,
            args=args,
            reason=decision.reason,
            call_id=call_id,
            session_id=audit.session_id,
        )

    def settle(answer: ApprovalDecision | None) -> tuple[bool, str]:
        if decision.action == Action.BLOCK:
            record("blocked", decision.reason)
            return False, decision.reason
        if decision.action == Action.APPROVE:
            if answer is None or not answer.approved:
                record("denied", decision.reason, answer.approver if answer else "")
                return False, f"approval denied ({decision.reason})"
            record("approved", decision.reason, answer.approver)
            return True, decision.reason
        record("allowed", decision.reason)
        return True, decision.reason

    return request, settle


_MAX_ERROR_LENGTH = 1000


def record_outcome(
    audit: AuditLogger, tool_name: str, call_id: str, error: str | None = None
) -> None:
    """Record that an allowed tool call has run: `completed` if it returned,
    `failed` with `error` if it raised."""
    if error is None:
        audit.record(tool_name, {}, "completed", "", call_id=call_id)
        return
    # Exception text can quote the very args the log redacts.
    if audit.redact_args:
        error = redact(error)
    audit.record(tool_name, {}, "failed", error[:_MAX_ERROR_LENGTH], call_id=call_id)


def describe_error(error: BaseException) -> str:
    return f"{type(error).__name__}: {error}"


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
    Every decision is recorded via `audit`, and so is whether an allowed call
    then completed or raised.
    """
    name: str = tool_name if tool_name is not None else getattr(fn, "__name__", "unknown_tool")
    audit = audit or AuditLogger()
    approval_handler = approval_handler or ConsoleApprovalHandler()

    def enforce(args: tuple[Any, ...], kwargs: dict[str, Any]) -> str:
        call_id = str(uuid.uuid4())
        allowed, reason = evaluate_and_record(
            name,
            _build_args_dict(fn, args, kwargs),
            policy=policy,
            audit=audit,
            approval_handler=approval_handler,
            call_id=call_id,
        )
        if not allowed:
            raise BlockedByPolicy(name, reason)
        return call_id

    async def enforce_async(args: tuple[Any, ...], kwargs: dict[str, Any]) -> str:
        call_id = str(uuid.uuid4())
        allowed, reason = await evaluate_and_record_async(
            name,
            _build_args_dict(fn, args, kwargs),
            policy=policy,
            audit=audit,
            approval_handler=approval_handler,
            call_id=call_id,
        )
        if not allowed:
            raise BlockedByPolicy(name, reason)
        return call_id

    if inspect.iscoroutinefunction(fn):

        @functools.wraps(fn)
        async def async_wrapper(*args: Any, **kwargs: Any) -> Any:
            call_id = await enforce_async(args, kwargs)
            try:
                result = await fn(*args, **kwargs)
            except Exception as e:
                record_outcome(audit, name, call_id, describe_error(e))
                raise
            record_outcome(audit, name, call_id)
            return result

        return async_wrapper

    @functools.wraps(fn)
    def wrapper(*args: Any, **kwargs: Any) -> Any:
        call_id = enforce(args, kwargs)
        try:
            result = fn(*args, **kwargs)
        except Exception as e:
            record_outcome(audit, name, call_id, describe_error(e))
            raise
        record_outcome(audit, name, call_id)
        return result

    return wrapper


def guard_tools(
    tools: Iterable[Any],
    *,
    policy: PolicyEngine,
    audit: AuditLogger | None = None,
    approval_handler: ApprovalHandler | None = None,
) -> list[Any]:
    """Wrap a list of tools. Handles plain callables (sync or async) and
    LangChain StructuredTool-style objects (anything with `.func` and/or
    `.coroutine`).

    For LangChain tools we wrap `.func` and `.coroutine` in place so the tool
    object itself (name, description, schema) is unchanged and still usable
    directly in a LangGraph tool node. Both must be wrapped: `ainvoke` calls
    `.coroutine` directly when it's set, so guarding only `.func` would let
    every async invocation skip policy.
    """
    audit = audit or AuditLogger()
    approval_handler = approval_handler or ConsoleApprovalHandler()
    wrapped: list[Any] = []

    for tool in tools:
        is_langchain_tool = hasattr(tool, "func") or hasattr(tool, "coroutine")
        if callable(tool) and not is_langchain_tool:
            wrapped.append(
                guard(tool, policy=policy, audit=audit, approval_handler=approval_handler)
            )
            continue

        impls = [attr for attr in ("func", "coroutine") if callable(getattr(tool, attr, None))]
        if not impls:
            raise TypeError(
                f"Don't know how to guard tool of type {type(tool)!r} — expected a "
                "callable or an object with a callable `.func` or `.coroutine` "
                "attribute (LangChain tool)."
            )

        tool_name = getattr(tool, "name", None) or getattr(
            getattr(tool, impls[0]), "__name__", "unknown_tool"
        )
        for attr in impls:
            setattr(
                tool,
                attr,
                guard(
                    getattr(tool, attr),
                    policy=policy,
                    audit=audit,
                    approval_handler=approval_handler,
                    tool_name=tool_name,
                ),
            )
        wrapped.append(tool)

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
