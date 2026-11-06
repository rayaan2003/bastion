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
        client: Any | None = None,
    ) -> None:
        """
        client: inject a pre-built slack_sdk.WebClient (or a test double
        with matching chat_postMessage/reactions_get methods). If omitted,
        a real WebClient is built from `token`.
        """
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
        response = self.client.chat_postMessage(channel=self.channel, text=text)
        message_ts = response["ts"]

        deadline = time.monotonic() + self.timeout
        while time.monotonic() < deadline:
            reactions = self._reactions(message_ts)
            # Deny wins if both are present: one reviewer objecting is enough.
            if deniers := reactions.get(self.deny_emoji):
                return ApprovalDecision(approved=False, approver=f"slack:{deniers[0]}")
            if approvers := reactions.get(self.approve_emoji):
                return ApprovalDecision(approved=True, approver=f"slack:{approvers[0]}")
            time.sleep(self.poll_interval)

        # Fail closed: no reviewer response within timeout = denied.
        return ApprovalDecision(approved=False)

    def _reactions(self, message_ts: str) -> dict[str, list[str]]:
        """Reaction name -> ids of the users who reacted with it."""
        result = self.client.reactions_get(channel=self.channel, timestamp=message_ts)
        message: dict[str, Any] = result.get("message", {})
        return {r["name"]: list(r.get("users", [])) for r in message.get("reactions", [])}
