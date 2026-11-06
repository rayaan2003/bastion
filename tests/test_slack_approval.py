from typing import Any

from bastion.approval import ApprovalDecision, ApprovalRequest
from bastion.approval.slack import SlackApprovalHandler


class FakeSlackClient:
    """Stands in for slack_sdk.WebClient: records the posted message and
    returns a scripted sequence of reaction states on each poll, shaped like
    Slack's reactions.get response ({"name", "users", "count"} per reaction)."""

    def __init__(self, reaction_sequence: list[dict[str, list[str]]]):
        self.reaction_sequence = reaction_sequence
        self.poll_count = 0
        self.posted: dict[str, Any] | None = None

    def chat_postMessage(self, channel: str, text: str) -> dict[str, Any]:
        self.posted = {"channel": channel, "text": text}
        return {"ts": "123.456"}

    def reactions_get(self, channel: str, timestamp: str) -> dict[str, Any]:
        index = min(self.poll_count, len(self.reaction_sequence) - 1)
        reactions = self.reaction_sequence[index]
        self.poll_count += 1
        return {
            "message": {
                "reactions": [
                    {"name": name, "users": users, "count": len(users)}
                    for name, users in reactions.items()
                ]
            }
        }


def _request() -> ApprovalRequest:
    return ApprovalRequest(
        tool_name="delete_user",
        args={"id": "1"},
        reason="irreversible",
        call_id="call-123",
        session_id="sess-1",
    )


def _handler(client: FakeSlackClient, **kwargs: Any) -> SlackApprovalHandler:
    kwargs.setdefault("poll_interval", 0)
    kwargs.setdefault("timeout", 5)
    return SlackApprovalHandler(token="xoxb-fake", channel="#approvals", client=client, **kwargs)


def test_approved_after_reaction_appears_records_who_reacted():
    client = FakeSlackClient([{}, {"white_check_mark": ["U024BE7LH"]}])
    decision = _handler(client).request_approval(_request())

    assert decision == ApprovalDecision(approved=True, approver="slack:U024BE7LH")
    assert client.posted is not None
    assert "delete_user" in client.posted["text"]
    assert "call-123" in client.posted["text"]


def test_denied_on_deny_reaction_records_who_reacted():
    client = FakeSlackClient([{"x": ["U0DENIER"]}])
    decision = _handler(client).request_approval(_request())
    assert decision == ApprovalDecision(approved=False, approver="slack:U0DENIER")


def test_deny_wins_when_both_reactions_present():
    client = FakeSlackClient([{"white_check_mark": ["U0APPROVER"], "x": ["U0DENIER"]}])
    decision = _handler(client).request_approval(_request())
    assert decision == ApprovalDecision(approved=False, approver="slack:U0DENIER")


def test_denied_on_timeout_with_no_approver():
    client = FakeSlackClient([{}])
    decision = _handler(client, poll_interval=0.01, timeout=0.05).request_approval(_request())
    assert decision == ApprovalDecision(approved=False, approver="")
