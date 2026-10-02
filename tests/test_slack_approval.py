from typing import Any

from bastion.integrations.slack import SlackApprovalHandler


class FakeSlackClient:
    """Stands in for slack_sdk.WebClient: records the posted message and
    returns a scripted sequence of reaction states on each poll."""

    def __init__(self, reaction_sequence: list[set[str]]):
        self.reaction_sequence = reaction_sequence
        self.poll_count = 0
        self.posted: dict[str, Any] | None = None

    def chat_postMessage(self, channel: str, text: str) -> dict[str, Any]:
        self.posted = {"channel": channel, "text": text}
        return {"ts": "123.456"}

    def reactions_get(self, channel: str, timestamp: str) -> dict[str, Any]:
        index = min(self.poll_count, len(self.reaction_sequence) - 1)
        names = self.reaction_sequence[index]
        self.poll_count += 1
        return {"message": {"reactions": [{"name": n} for n in names]}}


def test_approved_after_reaction_appears():
    client = FakeSlackClient(reaction_sequence=[set(), {"white_check_mark"}])
    handler = SlackApprovalHandler(
        token="xoxb-fake", channel="#approvals", poll_interval=0, timeout=5, client=client
    )
    assert handler.request_approval("delete_user", {"id": "1"}, "irreversible") is True
    assert client.posted is not None
    assert "delete_user" in client.posted["text"]


def test_denied_on_deny_reaction():
    client = FakeSlackClient(reaction_sequence=[{"x"}])
    handler = SlackApprovalHandler(
        token="xoxb-fake", channel="#approvals", poll_interval=0, timeout=5, client=client
    )
    assert handler.request_approval("delete_user", {"id": "1"}, "irreversible") is False


def test_denied_on_timeout_with_no_reaction():
    client = FakeSlackClient(reaction_sequence=[set()])
    handler = SlackApprovalHandler(
        token="xoxb-fake", channel="#approvals", poll_interval=0.01, timeout=0.05, client=client
    )
    assert handler.request_approval("delete_user", {"id": "1"}, "irreversible") is False
