import json
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest

from bastion import cli, mcp_proxy
from bastion.approval import ApprovalHandler, AutoDenyHandler
from bastion.approval.slack import SlackApprovalHandler
from bastion.audit import AuditLogger
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


def _chained_log(path: Path, n: int) -> Path:
    audit = AuditLogger(log_path=str(path))
    for _ in range(n):
        audit.record("t", {}, "allowed", "")
    return path


def test_verify_audit_passes_an_untouched_log(tmp_path, capsys):
    log = _chained_log(tmp_path / "audit.jsonl", 3)
    assert cli.main(["verify-audit", str(log)]) == 0
    assert capsys.readouterr().out == "no problems in 3 events across 1 chain\n"


def test_verify_audit_fails_and_names_the_line(tmp_path, capsys):
    log = _chained_log(tmp_path / "audit.jsonl", 3)
    lines = log.read_text().splitlines(keepends=True)
    log.write_text(lines[0] + lines[2])
    chain_id = json.loads(lines[0])["chain_id"]

    assert cli.main(["verify-audit", str(log)]) == 1
    assert capsys.readouterr().out == (
        f"line 2 (chain {chain_id}): event 1 is missing before seq 2\n"
        "1 problem in 2 events across 1 chain\n"
    )


def test_verify_audit_rejects_a_missing_file(tmp_path, capsys):
    with pytest.raises(SystemExit) as exit_info:
        cli.main(["verify-audit", str(tmp_path / "nope.jsonl")])
    assert exit_info.value.code == 2
    assert "nope.jsonl" in capsys.readouterr().err
