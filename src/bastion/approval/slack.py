"""Slack-based human-in-the-loop approval.

Posts a message to a Slack channel and waits for a reviewer to react with an
emoji (default: white_check_mark to approve, x to deny). Deliberately uses
reaction polling rather than Slack's Block Kit button + Interactivity API,
because buttons require a webhook server running somewhere to receive the
click payload — reaction polling needs only a bot token, so it works from
a plain script with no server to host.

Requires the `slack` extra: pip install bastionguard[slack]
"""

from __future__ import annotations

import time
from collections.abc import Iterable
from typing import Any

from bastion.approval import ApprovalDecision, ApprovalHandler, ApprovalRequest


class SlackApprovalHandler(ApprovalHandler):
    def __init__(
        self,
        token: str,
        channel: str,
        *,
        approve_emoji: str = "white_check_mark",
        deny_emoji: str = "x",
        poll_interval: float = 5.0,
        timeout: float = 300.0,
        approvers: Iterable[str] | None = None,
        client: Any | None = None,
    ) -> None:
        """
        approvers: Slack user ids (`U024BE7LH`) who may decide. Reactions
        from anyone else, approve or deny, are ignored. None lets anyone in
        the channel decide.

        client: inject a pre-built slack_sdk.WebClient (or a test double
        with matching chat_postMessage/reactions_get methods). If omitted,
        a real WebClient is built from `token`.
        """
        if isinstance(approvers, str):
            # frozenset("U024BE7LH") would allow single characters.
            raise TypeError("approvers takes a list of user ids, not one string")
        self.approvers = frozenset(approvers) if approvers is not None else None
        if self.approvers is not None and not self.approvers:
            raise ValueError("approvers is empty, so no one could approve anything")
        if client is None:
            try:
                from slack_sdk import WebClient
            except ImportError as e:
                raise ImportError(
                    "slack_sdk is required for SlackApprovalHandler. "
                    "Install with: pip install bastionguard[slack]"
                ) from e
            client = WebClient(token=token)

        self.client = client
        self.channel = channel
        self.approve_emoji = approve_emoji
        self.deny_emoji = deny_emoji
        self.poll_interval = poll_interval
        self.timeout = timeout

    def request_approval(self, request: ApprovalRequest) -> ApprovalDecision:
        text = (
            f":rotating_light: *Approval required* for tool `{request.tool_name}`\n"
            f"*Args:* `{request.args}`\n"
            f"*Reason:* {request.reason}\n"
            f"*Call:* `{request.call_id}`\n\n"
            f"React :{self.approve_emoji}: to approve or :{self.deny_emoji}: to deny "
            f"(times out in {int(self.timeout)}s)."
        )
        if self.approvers is not None:
            # <@id> mentions notify the reviewers, too.
            reviewers = ", ".join(f"<@{user}>" for user in sorted(self.approvers))
            text += f"\nOnly {reviewers} can decide."
        response = self.client.chat_postMessage(channel=self.channel, text=text)
        message_ts = response["ts"]

        deadline = time.monotonic() + self.timeout
        while time.monotonic() < deadline:
            reactions = self._reactions(message_ts)
            # Deny wins if both are present: one reviewer objecting is enough.
            if denier := self._first_reviewer(reactions.get(self.deny_emoji, [])):
                return ApprovalDecision(approved=False, approver=f"slack:{denier}")
            if approver := self._first_reviewer(reactions.get(self.approve_emoji, [])):
                return ApprovalDecision(approved=True, approver=f"slack:{approver}")
            time.sleep(self.poll_interval)

        # Fail closed: no reviewer response within timeout = denied.
        return ApprovalDecision(approved=False)

    def _first_reviewer(self, users: list[str]) -> str | None:
        return next((u for u in users if self.approvers is None or u in self.approvers), None)

    def _reactions(self, message_ts: str) -> dict[str, list[str]]:
        """Reaction name -> ids of the users who reacted with it."""
        # full=True: without it Slack may truncate each reaction's user list,
        # which could hide the one allowed reviewer among other reactions.
        result = self.client.reactions_get(channel=self.channel, timestamp=message_ts, full=True)
        message: dict[str, Any] = result.get("message", {})
        return {r["name"]: list(r.get("users", [])) for r in message.get("reactions", [])}
