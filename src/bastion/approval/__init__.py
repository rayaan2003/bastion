"""Human-in-the-loop approval for tool calls flagged Action.APPROVE.

ApprovalHandler is the pluggable interface. ConsoleApprovalHandler is the
default (prompts in the terminal) so the SDK works standalone with zero
external services. Other channels: bastion.approval.slack, bastion.dashboard.
"""

from __future__ import annotations

import getpass
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class ApprovalRequest:
    tool_name: str
    # Raw, not redacted: a reviewer usually needs the real values to decide.
    args: dict[str, Any]
    reason: str
    # Same ids as the call's audit events, so a channel can link back to them.
    call_id: str
    session_id: str


@dataclass(frozen=True)
class ApprovalDecision:
    approved: bool
    # Who decided, as the channel identifies them ("slack:U024BE7LH",
    # "console:alice"). Empty when nobody did, e.g. the request timed out.
    approver: str = ""


class ApprovalHandler(ABC):
    @abstractmethod
    def request_approval(self, request: ApprovalRequest) -> ApprovalDecision:
        """Ask a human whether `request` may run. May block until they answer."""
        raise NotImplementedError


class ConsoleApprovalHandler(ApprovalHandler):
    def request_approval(self, request: ApprovalRequest) -> ApprovalDecision:
        print(f"\n[bastion] APPROVAL REQUIRED for tool '{request.tool_name}'")
        print(f"  args: {request.args}")
        print(f"  reason: {request.reason}")
        answer = input("  approve? [y/N]: ").strip().lower()
        return ApprovalDecision(approved=answer == "y", approver=f"console:{_local_user()}")


class AutoDenyHandler(ApprovalHandler):
    """Useful for non-interactive environments (CI, tests) — denies anything
    that would otherwise require a human."""

    def request_approval(self, request: ApprovalRequest) -> ApprovalDecision:
        return ApprovalDecision(approved=False, approver="auto-deny")


def _local_user() -> str:
    try:
        return getpass.getuser()
    except (OSError, KeyError):
        # No login name in some containers; still record that it was local.
        return "unknown"
