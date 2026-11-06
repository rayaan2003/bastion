"""The `bastion` command."""

from __future__ import annotations

import argparse
import asyncio
import os
from collections.abc import Sequence
from pathlib import Path

from bastion.approval import ApprovalHandler, AutoDenyHandler
from bastion.audit import AuditLogger
from bastion.config import PolicyConfigError, load_policy_from_yaml
from bastion.policy import PolicyEngine

DEFAULT_AUDIT_LOG = Path.home() / ".bastion" / "audit.jsonl"


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="bastion")
    commands = parser.add_subparsers(dest="command", required=True)
    proxy = commands.add_parser(
        "mcp-proxy",
        help="enforce a policy on an MCP server's tool calls",
        description=(
            "Start an MCP server and relay between it and the MCP client on "
            "stdin/stdout, checking every tools/call against the policy."
        ),
        epilog="example: bastion mcp-proxy --policy policy.yaml -- npx -y some-mcp-server",
    )
    proxy.add_argument("--policy", type=Path, help="YAML policy file")
    proxy.add_argument(
        "--audit-log",
        type=Path,
        default=DEFAULT_AUDIT_LOG,
        help="JSONL audit log (default: ~/.bastion/audit.jsonl)",
    )
    proxy.add_argument(
        "--dashboard-url",
        help=(
            "send audit events to this dashboard instead of --audit-log, and load the "
            "policy from it when --policy is omitted. API key: $BASTION_DASHBOARD_API_KEY"
        ),
    )
    proxy.add_argument(
        "--approval",
        choices=["deny", "slack", "dashboard"],
        default="deny",
        help=(
            "who decides `approve` rules (default: deny them). The terminal can't "
            "prompt here: stdin is the MCP connection."
        ),
    )
    proxy.add_argument("--slack-channel", help="channel for --approval slack ($SLACK_BOT_TOKEN)")
    proxy.add_argument(
        "--slack-approver",
        action="append",
        metavar="USER_ID",
        help="Slack user id allowed to decide; repeat for several (default: anyone)",
    )
    proxy.add_argument("server", nargs=argparse.REMAINDER, help="-- then the MCP server command")

    args = parser.parse_args(argv)
    server = args.server[1:] if args.server[:1] == ["--"] else args.server
    if not server:
        parser.error("give the MCP server command after --")

    try:
        policy = _policy(args)
        audit = _audit(args)
        handler = _approval_handler(args)
    except (PolicyConfigError, OSError, ValueError, ImportError) as e:
        parser.error(str(e))

    from bastion.mcp_proxy import run_proxy

    return asyncio.run(run_proxy(server, policy=policy, audit=audit, approval_handler=handler))


def _policy(args: argparse.Namespace) -> PolicyEngine:
    if args.policy:
        return load_policy_from_yaml(args.policy)
    if args.dashboard_url:
        from bastion.dashboard import load_policy_from_dashboard

        return load_policy_from_dashboard(args.dashboard_url, _env("BASTION_DASHBOARD_API_KEY"))
    raise ValueError("give a policy: --policy FILE, or --dashboard-url to use the dashboard's")


def _audit(args: argparse.Namespace) -> AuditLogger:
    if args.dashboard_url:
        from bastion.dashboard import dashboard_audit_sink

        sink = dashboard_audit_sink(args.dashboard_url, _env("BASTION_DASHBOARD_API_KEY"))
        return AuditLogger(sink=sink)
    args.audit_log.parent.mkdir(parents=True, exist_ok=True)
    return AuditLogger(log_path=str(args.audit_log))


def _approval_handler(args: argparse.Namespace) -> ApprovalHandler:
    if args.approval == "slack":
        if not args.slack_channel:
            raise ValueError("--approval slack needs --slack-channel")
        from bastion.approval.slack import SlackApprovalHandler

        return SlackApprovalHandler(
            _env("SLACK_BOT_TOKEN"), args.slack_channel, approvers=args.slack_approver
        )
    if args.approval == "dashboard":
        if not args.dashboard_url:
            raise ValueError("--approval dashboard needs --dashboard-url")
        from bastion.dashboard import DashboardApprovalHandler

        return DashboardApprovalHandler(args.dashboard_url, _env("BASTION_DASHBOARD_API_KEY"))
    return AutoDenyHandler()


def _env(name: str) -> str:
    value = os.environ.get(name)
    if not value:
        raise ValueError(f"${name} isn't set")
    return value

