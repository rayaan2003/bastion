"""Tests against the real `claude_agent_sdk` package, not a mock of its
API. `guarded_can_use_tool()` is invoked directly the same way the SDK
calls it internally: an async (tool_name, input_data, context) callback.
"""

import asyncio
import json
import threading

import pytest

claude_agent_sdk = pytest.importorskip("claude_agent_sdk")

from claude_agent_sdk import (  # noqa: E402
    ClaudeAgentOptions,
    HookMatcher,
    PermissionResultAllow,
    PermissionResultDeny,
    ToolPermissionContext,
)

from bastion import Action, AuditLogger, PolicyEngine, Rule  # noqa: E402
from bastion.approval import ApprovalHandler  # noqa: E402
from bastion.integrations.claude_agent_sdk import (  # noqa: E402
    guarded_can_use_tool,
    guarded_pre_tool_use,
)


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


def test_shadow_rule_allows_and_records_would_block():
    actions: list[str] = []
    policy = PolicyEngine()
    policy.add_rule(Rule(tool_pattern="Bash", action=Action.BLOCK, shadow=True))
    audit = AuditLogger(sink=lambda e: actions.append(e.action))
    can_use_tool = guarded_can_use_tool(policy=policy, audit=audit, approval_handler=AlwaysDeny())

    result = call(can_use_tool, "Bash", {"command": "rm -rf /"})
    assert isinstance(result, PermissionResultAllow)
    assert actions == ["would_block", "allowed"]


# --- PreToolUse hook ---------------------------------------------------------


def run_hook(matcher: HookMatcher, tool_name: str, tool_input: dict) -> dict:
    """Invoke the hook the way the SDK does when the CLI sends a hook_callback:
    `await callback(input, tool_use_id, {"signal": None})`, then the result
    goes to the CLI as JSON."""
    hook_input = {
        "hook_event_name": "PreToolUse",
        "session_id": "sess-1",
        "transcript_path": "/tmp/t.jsonl",
        "cwd": "/tmp",
        "tool_name": tool_name,
        "tool_input": tool_input,
        "tool_use_id": "toolu_1",
    }
    [callback] = matcher.hooks
    output = asyncio.run(callback(hook_input, "toolu_1", {"signal": None}))
    json.dumps(output)
    return output


def _hook(policy: PolicyEngine, approval_handler=None, actions: list | None = None) -> HookMatcher:
    sink = (lambda e: actions.append(e.action)) if actions is not None else (lambda e: None)
    return guarded_pre_tool_use(
        policy=policy, audit=AuditLogger(sink=sink), approval_handler=approval_handler
    )


def _no_shell() -> PolicyEngine:
    return PolicyEngine().add_rule(
        Rule(tool_pattern="Bash", action=Action.BLOCK, reason="no shell access")
    )


def test_hook_matcher_covers_every_tool_and_fails_closed():
    matcher = _hook(_no_shell())
    assert matcher.matcher is None
    assert matcher.on_failure == "block"
    assert matcher.timeout == 600.0
    ClaudeAgentOptions(hooks={"PreToolUse": [matcher]})


def test_hook_blocks_with_deny_decision_and_reason():
    actions: list[str] = []
    output = run_hook(_hook(_no_shell(), actions=actions), "Bash", {"command": "rm -rf /"})

    specific = output["hookSpecificOutput"]
    assert specific["hookEventName"] == "PreToolUse"
    assert specific["permissionDecision"] == "deny"
    assert "no shell access" in specific["permissionDecisionReason"]
    assert actions == ["blocked"]


def test_hook_allowed_call_expresses_no_opinion():
    # Not permissionDecision "allow": that would also skip the SDK's own
    # permission checks, which bastion allowing a call shouldn't override.
    actions: list[str] = []
    output = run_hook(_hook(_no_shell(), actions=actions), "Read", {"file_path": "/etc/hosts"})
    assert output == {}
    assert actions == ["allowed"]


def test_hook_approval_approved_and_denied():
    policy = PolicyEngine().add_rule(
        Rule(tool_pattern="Write", action=Action.APPROVE, reason="writes need review")
    )
    assert run_hook(_hook(policy, AlwaysApprove()), "Write", {"file_path": "a"}) == {}

    denied = run_hook(_hook(policy, AlwaysDeny()), "Write", {"file_path": "a"})
    assert denied["hookSpecificOutput"]["permissionDecision"] == "deny"
    assert "approval denied" in denied["hookSpecificOutput"]["permissionDecisionReason"]


def test_hook_runs_approval_off_the_event_loop_thread():
    seen: list[bool] = []

    class RecordsThread(ApprovalHandler):
        def request_approval(self, tool_name, args, reason):
            seen.append(threading.current_thread() is threading.main_thread())
            return True

    policy = PolicyEngine().add_rule(Rule(tool_pattern="*", action=Action.APPROVE))
    run_hook(_hook(policy, RecordsThread()), "Bash", {"command": "ls"})
    assert seen == [False]


def test_hook_ignores_non_pre_tool_use_events():
    [callback] = _hook(_no_shell()).hooks
    stop_input = {
        "hook_event_name": "Stop",
        "session_id": "s",
        "transcript_path": "t",
        "cwd": "/",
        "stop_hook_active": False,
    }
    assert asyncio.run(callback(stop_input, None, {"signal": None})) == {}
