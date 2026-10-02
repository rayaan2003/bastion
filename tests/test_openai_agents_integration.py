"""Tests against the real `agents` package (openai-agents), not a mock of
its API. Tool invocation is exercised the same way the SDK's own Runner
does internally: build a ToolContext and call tool.on_invoke_tool(ctx, json_str).
"""

import asyncio

import pytest

agents = pytest.importorskip("agents")

from agents import function_tool  # noqa: E402
from agents.tool_context import ToolContext  # noqa: E402

from agentguard import Action, AuditLogger, PolicyEngine, Rule  # noqa: E402
from agentguard.approval import ApprovalHandler  # noqa: E402
from agentguard.integrations.openai_agents import guarded_tools  # noqa: E402


class AlwaysApprove(ApprovalHandler):
    def request_approval(self, tool_name, args, reason):
        return True


class AlwaysDeny(ApprovalHandler):
    def request_approval(self, tool_name, args, reason):
        return False


def make_ctx(tool_name: str, args_json: str) -> ToolContext:
    return ToolContext(
        context=None, tool_name=tool_name, tool_call_id="call_1", tool_arguments=args_json
    )


def invoke(tool, args_json: str):
    ctx = make_ctx(tool.name, args_json)
    return asyncio.run(tool.on_invoke_tool(ctx, args_json))


@function_tool
def delete_user(user_id: str) -> str:
    """Delete a user account."""
    return f"deleted {user_id}"


@function_tool
def search_docs(query: str) -> str:
    """Search internal docs."""
    return f"3 results for '{query}'"


def make_policy() -> PolicyEngine:
    policy = PolicyEngine()
    policy.add_rule(Rule(tool_pattern="delete_*", action=Action.BLOCK, reason="irreversible"))
    return policy


def test_allowed_call_passes_through(tmp_path):
    audit = AuditLogger(log_path=str(tmp_path / "audit.jsonl"))
    [guarded_search] = guarded_tools([search_docs], policy=make_policy(), audit=audit)

    result = invoke(guarded_search, '{"query": "refund policy"}')
    assert result == "3 results for 'refund policy'"


def test_blocked_call_returns_descriptive_string_not_raise(tmp_path):
    audit = AuditLogger(log_path=str(tmp_path / "audit.jsonl"))
    [guarded_delete] = guarded_tools([delete_user], policy=make_policy(), audit=audit)

    result = invoke(guarded_delete, '{"user_id": "u123"}')
    assert isinstance(result, str)
    assert "blocked" in result.lower()
    assert "irreversible" in result


def test_approved_call_passes_through(tmp_path):
    policy = PolicyEngine()
    policy.add_rule(Rule(
        tool_pattern="delete_*", action=Action.APPROVE, reason="needs human sign-off"
    ))
    audit = AuditLogger(log_path=str(tmp_path / "audit.jsonl"))
    [guarded_delete] = guarded_tools(
        [delete_user], policy=policy, audit=audit, approval_handler=AlwaysApprove()
    )

    result = invoke(guarded_delete, '{"user_id": "u123"}')
    assert result == "deleted u123"


def test_denied_approval_returns_descriptive_string(tmp_path):
    policy = PolicyEngine()
    policy.add_rule(Rule(
        tool_pattern="delete_*", action=Action.APPROVE, reason="needs human sign-off"
    ))
    audit = AuditLogger(log_path=str(tmp_path / "audit.jsonl"))
    [guarded_delete] = guarded_tools(
        [delete_user], policy=policy, audit=audit, approval_handler=AlwaysDeny()
    )

    result = invoke(guarded_delete, '{"user_id": "u123"}')
    assert isinstance(result, str)
    assert "denied" in result.lower()


def test_original_tool_not_mutated(tmp_path):
    audit = AuditLogger(log_path=str(tmp_path / "audit.jsonl"))
    [guarded_delete] = guarded_tools([delete_user], policy=make_policy(), audit=audit)

    assert guarded_delete is not delete_user
    assert guarded_delete.on_invoke_tool is not delete_user.on_invoke_tool
    # the original, unwrapped tool still executes normally
    result = asyncio.run(
        delete_user.on_invoke_tool(make_ctx("delete_user", '{"user_id": "x"}'), '{"user_id": "x"}')
    )
    assert result == "deleted x"


def test_audit_log_records_block(tmp_path):
    log_path = tmp_path / "audit.jsonl"
    audit = AuditLogger(log_path=str(log_path))
    [guarded_delete] = guarded_tools([delete_user], policy=make_policy(), audit=audit)

    invoke(guarded_delete, '{"user_id": "u123"}')

    content = log_path.read_text()
    assert "blocked" in content
    assert "delete_user" in content


def test_guarding_non_function_tool_raises_type_error(tmp_path):
    audit = AuditLogger(log_path=str(tmp_path / "audit.jsonl"))
    with pytest.raises(TypeError, match=r"agents\.FunctionTool"):
        guarded_tools(["not a tool"], policy=make_policy(), audit=audit)
