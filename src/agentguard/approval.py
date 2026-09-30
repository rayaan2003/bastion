"""Human-in-the-loop approval for tool calls flagged Action.APPROVE.

ApprovalHandler is the pluggable interface. ConsoleApprovalHandler is the v1
default (prompts in the terminal) so the SDK works standalone with zero
external services. A SlackApprovalHandler (posts to a channel with
Approve/Deny buttons and blocks until someone responds) is the next one to
build — see NOTES.md build plan.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any


class ApprovalHandler(ABC):
    @abstractmethod
    def request_approval(self, tool_name: str, args: dict[str, Any], reason: str) -> bool:
        """Return True if approved, False if denied. May block."""
        raise NotImplementedError


class ConsoleApprovalHandler(ApprovalHandler):
    def request_approval(self, tool_name: str, args: dict[str, Any], reason: str) -> bool:
        print(f"\n[agentguard] APPROVAL REQUIRED for tool '{tool_name}'")
        print(f"  args: {args}")
        print(f"  reason: {reason}")
        answer = input("  approve? [y/N]: ").strip().lower()
        return answer == "y"


class AutoDenyHandler(ApprovalHandler):
    """Useful for non-interactive environments (CI, tests) — denies anything
    that would otherwise require a human."""

    def request_approval(self, tool_name: str, args: dict[str, Any], reason: str) -> bool:
        return False
