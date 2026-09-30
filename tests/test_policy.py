import pytest

from agentguard import Action, AuditLogger, PolicyEngine, Rule, guard
from agentguard.approval import ApprovalHandler
from agentguard.guard import BlockedByPolicy
from agentguard.policy import any_arg_contains, arg_exceeds


def make_audit(tmp_path):
    return AuditLogger(log_path=str(tmp_path / "audit.jsonl"))


class AlwaysApprove(ApprovalHandler):
    def request_approval(self, tool_name, args, reason):
        return True


class AlwaysDeny(ApprovalHandler):
    def request_approval(self, tool_name, args, reason):
        return False


def test_default_allow(tmp_path):
    policy = PolicyEngine()
    fn = guard(lambda x: x * 2, policy=policy, audit=make_audit(tmp_path), tool_name="double")
    assert fn(3) == 6


def test_block_rule_raises(tmp_path):
    policy = PolicyEngine()
    policy.add_rule(Rule(tool_pattern="delete_*", action=Action.BLOCK, reason="no deletes"))

    def delete_thing(id: str) -> str:
        return f"deleted {id}"

    fn = guard(delete_thing, policy=policy, audit=make_audit(tmp_path))
    with pytest.raises(BlockedByPolicy, match="no deletes"):
        fn(id="123")


def test_approve_rule_allows_when_approved(tmp_path):
    policy = PolicyEngine()
    policy.add_rule(Rule(
        tool_pattern="transfer_funds",
        action=Action.APPROVE,
        condition=arg_exceeds("amount", 500),
        reason="large transfer",
    ))

    def transfer_funds(amount: float) -> str:
        return f"transferred {amount}"

    fn = guard(
        transfer_funds,
        policy=policy,
        audit=make_audit(tmp_path),
        approval_handler=AlwaysApprove(),
    )
    assert fn(amount=600) == "transferred 600"


def test_approve_rule_blocks_when_denied(tmp_path):
    policy = PolicyEngine()
    policy.add_rule(Rule(
        tool_pattern="transfer_funds",
        action=Action.APPROVE,
        condition=arg_exceeds("amount", 500),
        reason="large transfer",
    ))

    def transfer_funds(amount: float) -> str:
        return f"transferred {amount}"

    fn = guard(
        transfer_funds,
        policy=policy,
        audit=make_audit(tmp_path),
        approval_handler=AlwaysDeny(),
    )
    with pytest.raises(BlockedByPolicy):
        fn(amount=600)


def test_condition_below_threshold_is_allowed(tmp_path):
    policy = PolicyEngine()
    policy.add_rule(Rule(
        tool_pattern="transfer_funds",
        action=Action.APPROVE,
        condition=arg_exceeds("amount", 500),
        reason="large transfer",
    ))

    def transfer_funds(amount: float) -> str:
        return f"transferred {amount}"

    fn = guard(
        transfer_funds,
        policy=policy,
        audit=make_audit(tmp_path),
        approval_handler=AlwaysDeny(),
    )
    # below threshold -> rule doesn't match -> default allow, no approval needed
    assert fn(amount=10) == "transferred 10"


def test_any_arg_contains():
    cond = any_arg_contains(["external", "all-staff"])
    assert cond({"to": "external-partner@x.com"}) is True
    assert cond({"to": "internal@x.com"}) is False


def test_audit_log_written(tmp_path):
    policy = PolicyEngine()
    policy.add_rule(Rule(tool_pattern="delete_*", action=Action.BLOCK, reason="no deletes"))
    audit = make_audit(tmp_path)

    def delete_thing(id: str) -> str:
        return f"deleted {id}"

    fn = guard(delete_thing, policy=policy, audit=audit)
    with pytest.raises(BlockedByPolicy):
        fn(id="123")

    log_file = tmp_path / "audit.jsonl"
    assert log_file.exists()
    content = log_file.read_text()
    assert "blocked" in content
    assert "delete_thing" in content
