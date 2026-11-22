from collections.abc import Callable
from typing import Any

import pytest

from bastion import cli, mcp_proxy
from bastion.approval import ApprovalHandler, AutoDenyHandler
from bastion.approval.slack import SlackApprovalHandler
from bastion.dashboard import DashboardApprovalHandler


@pytest.fixture
def start_proxy(monkeypatch, tmp_path) -> Callable[..., ApprovalHandler]:
    """Runs `bastion mcp-proxy` with the given flags up to the point it
    would start the server, and returns the approval handler it built."""
    started: dict[str, Any] = {}

    async def fake_run_proxy(server: list[str], **kwargs: Any) -> int:
        started.update(kwargs, server=server)
        return 0

    monkeypatch.setattr(mcp_proxy, "run_proxy", fake_run_proxy)
    monkeypatch.setenv("SLACK_BOT_TOKEN", "xoxb-fake")
    monkeypatch.setenv("BASTION_DASHBOARD_API_KEY", "key")
    policy = tmp_path / "policy.yaml"
    policy.write_text("default_action: allow\n")

    def start(*flags: str) -> ApprovalHandler:
        argv = ["mcp-proxy", "--policy", str(policy), "--audit-log", str(tmp_path / "a.jsonl")]
        assert cli.main([*argv, *flags, "--", "server", "--arg"]) == 0
        assert started["server"] == ["server", "--arg"]
        handler: ApprovalHandler = started["approval_handler"]
        return handler

    return start


def test_approvals_deny_by_default(start_proxy):
    assert isinstance(start_proxy(), AutoDenyHandler)


def test_slack_approvals_show_raw_args_unless_asked(start_proxy):
    pytest.importorskip("slack_sdk")
    handler = start_proxy("--approval", "slack", "--slack-channel", "#a")
    assert isinstance(handler, SlackApprovalHandler)
    assert handler.redact_args is False


def test_redact_approval_args_reaches_slack(start_proxy):
    pytest.importorskip("slack_sdk")
    handler = start_proxy(
        "--approval", "slack", "--slack-channel", "#a", "--redact-approval-args"
    )
    assert isinstance(handler, SlackApprovalHandler)
    assert handler.redact_args is True


def test_redact_approval_args_reaches_the_dashboard(start_proxy):
    handler = start_proxy(
        "--approval", "dashboard",
        "--dashboard-url", "http://127.0.0.1:1",
        "--redact-approval-args",
    )
    assert isinstance(handler, DashboardApprovalHandler)
    assert handler.redact_args is True
