"""Tests against the real `claude_agent_sdk` package, not a mock of its
API. `guarded_can_use_tool()` is invoked directly the same way the SDK
calls it internally: an async (tool_name, input_data, context) callback.
"""

import asyncio

import pytest

claude_agent_sdk = pytest.importorskip("claude_agent_sdk")

from claude_agent_sdk import (  # noqa: E402
    PermissionResultAllow,
    PermissionResultDeny,
    ToolPermissionContext,
)

from bastion import Action, AuditLogger, PolicyEngine, Rule  # noqa: E402
from bastion.approval import ApprovalHandler  # noqa: E402
from bastion.integrations.claude_agent_sdk import guarded_can_use_tool  # noqa: E402


class AlwaysApprove(ApprovalHandler):
    def request_approval(self, tool_name, args, reason):
        return True


class AlwaysDeny(ApprovalHandler):
    def request_approval(self, tool_name, args, reason):
        return False


def call(can_use_tool, tool_name: str, input_data: dict):
    return asyncio.run(can_use_tool(tool_name, input_data, ToolPermissionContext()))


def test_allowed_tool_returns_permission_result_allow(tmp_path):
    policy = PolicyEngine()
    policy.add_rule(Rule(tool_pattern="Bash", action=Action.BLOCK, reason="no shell"))
    audit = AuditLogger(log_path=str(tmp_path / "audit.jsonl"))
    can_use_tool = guarded_can_use_tool(policy=policy, audit=audit)

    result = call(can_use_tool, "Read", {"file_path": "/etc/hosts"})
    assert isinstance(result, PermissionResultAllow)


def test_blocked_tool_returns_permission_result_deny_with_reason(tmp_path):
    policy = PolicyEngine()
    policy.add_rule(Rule(tool_pattern="Bash", action=Action.BLOCK, reason="no shell access"))
    audit = AuditLogger(log_path=str(tmp_path / "audit.jsonl"))
    can_use_tool = guarded_can_use_tool(policy=policy, audit=audit)

    result = call(can_use_tool, "Bash", {"command": "rm -rf /"})
    assert isinstance(result, PermissionResultDeny)
    assert "no shell access" in result.message


def test_approved_tool_returns_allow(tmp_path):
    policy = PolicyEngine()
    policy.add_rule(Rule(tool_pattern="Bash", action=Action.APPROVE, reason="needs sign-off"))
    audit = AuditLogger(log_path=str(tmp_path / "audit.jsonl"))
    can_use_tool = guarded_can_use_tool(
        policy=policy, audit=audit, approval_handler=AlwaysApprove()
    )

    result = call(can_use_tool, "Bash", {"command": "ls"})
    assert isinstance(result, PermissionResultAllow)


def test_denied_approval_returns_deny(tmp_path):
    policy = PolicyEngine()
    policy.add_rule(Rule(tool_pattern="Bash", action=Action.APPROVE, reason="needs sign-off"))
    audit = AuditLogger(log_path=str(tmp_path / "audit.jsonl"))
    can_use_tool = guarded_can_use_tool(
        policy=policy, audit=audit, approval_handler=AlwaysDeny()
    )

    result = call(can_use_tool, "Bash", {"command": "ls"})
    assert isinstance(result, PermissionResultDeny)
    assert "denied" in result.message.lower()


def test_covers_custom_mcp_tool_names_same_as_builtins(tmp_path):
    # can_use_tool is one callback for every tool - built-in (Bash, Read,
    # Write) and custom MCP tools alike. Confirm a custom-style tool name
    # is evaluated identically, not treated as a special case.
    policy = PolicyEngine()
    policy.add_rule(Rule(tool_pattern="delete_*", action=Action.BLOCK, reason="irreversible"))
    audit = AuditLogger(log_path=str(tmp_path / "audit.jsonl"))
    can_use_tool = guarded_can_use_tool(policy=policy, audit=audit)

    result = call(can_use_tool, "delete_user", {"user_id": "u123"})
    assert isinstance(result, PermissionResultDeny)


def test_audit_log_records_deny(tmp_path):
    log_path = tmp_path / "audit.jsonl"
    policy = PolicyEngine()
    policy.add_rule(Rule(tool_pattern="Bash", action=Action.BLOCK, reason="no shell access"))
    audit = AuditLogger(log_path=str(log_path))
    can_use_tool = guarded_can_use_tool(policy=policy, audit=audit)

    call(can_use_tool, "Bash", {"command": "ls"})

    content = log_path.read_text()
    assert "blocked" in content
    assert "Bash" in content
