import logging

import pytest

from bastion import Action, AuditLogger, PolicyEngine, Rule, guard
from bastion.approval import ApprovalDecision, ApprovalHandler
from bastion.config import PolicyConfigError, policy_from_yaml_string
from bastion.guard import BlockedByPolicy


class RecordingApprover(ApprovalHandler):
    def __init__(self) -> None:
        self.calls: list[str] = []

    def request_approval(self, request):
        self.calls.append(request.tool_name)
        return ApprovalDecision(approved=True)


def _audit() -> tuple[AuditLogger, list[tuple[str, str]]]:
    # Decisions only; completed/failed outcomes are covered in test_guard.py.
    events: list[tuple[str, str]] = []

    def sink(e):
        if e.action not in ("completed", "failed"):
            events.append((e.action, e.reason))

    return AuditLogger(sink=sink), events


def delete_user(user_id: str) -> str:
    return f"deleted {user_id}"


def _run(policy: PolicyEngine, approver: ApprovalHandler | None = None):
    audit, events = _audit()
    approver = approver or RecordingApprover()
    fn = guard(delete_user, policy=policy, audit=audit, approval_handler=approver)
    return fn, events


def test_shadow_block_rule_lets_call_through_and_records_would_block():
    policy = PolicyEngine().add_rule(
        Rule(tool_pattern="delete_*", action=Action.BLOCK, reason="irreversible", shadow=True)
    )
    fn, events = _run(policy)

    assert fn(user_id="u1") == "deleted u1"
    assert events == [
        ("would_block", "irreversible"),
        ("allowed", "no matching rule — default allow"),
    ]


def test_shadow_approve_rule_never_asks_a_human():
    approver = RecordingApprover()
    policy = PolicyEngine().add_rule(
        Rule(tool_pattern="delete_*", action=Action.APPROVE, reason="needs review", shadow=True)
    )
    fn, events = _run(policy, approver)

    assert fn(user_id="u1") == "deleted u1"
    assert approver.calls == []
    assert [a for a, _ in events] == ["would_approve", "allowed"]


def test_shadow_rule_ahead_of_enforced_rule_does_not_weaken_it():
    policy = PolicyEngine()
    policy.add_rule(Rule(tool_pattern="delete_*", action=Action.ALLOW, shadow=True))
    policy.add_rule(Rule(tool_pattern="delete_*", action=Action.BLOCK, reason="irreversible"))
    fn, events = _run(policy)

    with pytest.raises(BlockedByPolicy, match="irreversible"):
        fn(user_id="u1")
    assert [a for a, _ in events] == ["would_allow", "blocked"]


def test_no_shadow_event_when_shadow_outcome_matches_enforced_outcome():
    policy = PolicyEngine()
    policy.add_rule(Rule(tool_pattern="delete_*", action=Action.BLOCK, shadow=True))
    policy.add_rule(Rule(tool_pattern="delete_*", action=Action.BLOCK, reason="irreversible"))
    fn, events = _run(policy)

    with pytest.raises(BlockedByPolicy):
        fn(user_id="u1")
    assert [a for a, _ in events] == ["blocked"]


def test_only_first_matching_shadow_rule_counts():
    calls: list[str] = []

    def second_condition(args):
        calls.append("second")
        return True

    policy = PolicyEngine()
    policy.add_rule(Rule(tool_pattern="delete_*", action=Action.BLOCK, shadow=True))
    policy.add_rule(
        Rule(
            tool_pattern="delete_*",
            action=Action.APPROVE,
            condition=second_condition,
            shadow=True,
        )
    )
    fn, events = _run(policy)

    fn(user_id="u1")
    assert [a for a, _ in events] == ["would_block", "allowed"]
    assert calls == []


def test_shadow_rule_whose_condition_raises_does_not_break_the_call(caplog):
    def broken(args):
        raise KeyError("oops")

    policy = PolicyEngine().add_rule(
        Rule(
            tool_pattern="delete_*", action=Action.BLOCK, condition=broken, shadow=True, name="new"
        )
    )
    fn, events = _run(policy)

    with caplog.at_level(logging.WARNING, logger="bastion"):
        assert fn(user_id="u1") == "deleted u1"
    assert [a for a, _ in events] == ["allowed"]
    assert "shadow rule 'new' condition raised" in caplog.text


def test_engine_wide_shadow_enforces_nothing():
    approver = RecordingApprover()
    policy = PolicyEngine(shadow=True)
    policy.add_rule(Rule(tool_pattern="delete_*", action=Action.BLOCK, reason="irreversible"))
    fn, events = _run(policy, approver)

    assert fn(user_id="u1") == "deleted u1"
    assert events == [
        ("would_block", "irreversible"),
        ("allowed", "shadow mode — policy not enforced"),
    ]


def test_engine_wide_shadow_covers_default_action():
    policy = PolicyEngine(default_action=Action.BLOCK, shadow=True)
    fn, events = _run(policy)

    assert fn(user_id="u1") == "deleted u1"
    assert [a for a, _ in events] == ["would_block", "allowed"]


def test_default_reason_names_the_actual_default_action():
    decision = PolicyEngine(default_action=Action.BLOCK).evaluate("anything", {})
    assert decision.reason == "no matching rule — default block"


def test_yaml_per_rule_and_top_level_shadow():
    policy = policy_from_yaml_string("""
rules:
  - tool: "delete_*"
    action: block
    shadow: true
""")
    assert policy.rules[0].shadow is True
    assert policy.shadow is False

    policy = policy_from_yaml_string("""
shadow: true
rules:
  - tool: "delete_*"
    action: block
""")
    assert policy.shadow is True
    assert policy.evaluate("delete_user", {}).action == Action.ALLOW


@pytest.mark.parametrize(
    "yaml_text",
    [
        "shadow: yes please\nrules: []",
        "rules:\n  - tool: x\n    action: block\n    shadow: 1",
    ],
)
def test_yaml_non_boolean_shadow_is_rejected(yaml_text):
    with pytest.raises(PolicyConfigError, match="shadow must be true or false"):
        policy_from_yaml_string(yaml_text)
