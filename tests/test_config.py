import pytest

from agentguard import Action, PolicyConfigError, load_policy_from_yaml
from agentguard.config import policy_from_dict, policy_from_yaml_string
from agentguard.guard import BlockedByPolicy, guard


def test_load_policy_from_yaml_file(tmp_path):
    policy_file = tmp_path / "policy.yaml"
    policy_file.write_text(
        """
default_action: allow
rules:
  - name: block-deletes
    tool: "delete_*"
    action: block
    reason: "irreversible action"
  - name: approve-large-transfers
    tool: "transfer_funds"
    action: approve
    reason: "large transfers need a human"
    condition:
      type: arg_exceeds
      arg: amount
      threshold: 500
""",
        encoding="utf-8",
    )

    policy = load_policy_from_yaml(policy_file)
    assert len(policy.rules) == 2

    def delete_thing(id: str) -> str:
        return f"deleted {id}"

    fn = guard(delete_thing, policy=policy)
    with pytest.raises(BlockedByPolicy, match="irreversible action"):
        fn(id="1")


def test_condition_types_all_work():
    policy = policy_from_dict({
        "rules": [
            {
                "tool": "transfer_funds",
                "action": "approve",
                "condition": {"type": "arg_exceeds", "arg": "amount", "threshold": 100},
            },
            {
                "tool": "send_email",
                "action": "approve",
                "condition": {"type": "any_arg_contains", "substrings": ["external"]},
            },
            {
                "tool": "log_note",
                "action": "block",
                "condition": {
                    "type": "arg_matches_regex",
                    "arg": "body",
                    "pattern": r"\d{3}-\d{2}-\d{4}",
                },
            },
        ]
    })

    decision = policy.evaluate("transfer_funds", {"amount": 500})
    assert decision.action == Action.APPROVE

    decision = policy.evaluate("transfer_funds", {"amount": 10})
    assert decision.action == Action.ALLOW  # condition doesn't match -> falls through

    decision = policy.evaluate("send_email", {"to": "external@x.com"})
    assert decision.action == Action.APPROVE

    decision = policy.evaluate("log_note", {"body": "ssn is 123-45-6789"})
    assert decision.action == Action.BLOCK


def test_missing_required_rule_field_raises():
    with pytest.raises(PolicyConfigError, match="missing required field"):
        policy_from_dict({"rules": [{"tool": "delete_*"}]})  # no action


def test_unknown_action_raises():
    with pytest.raises(PolicyConfigError, match="unknown action"):
        policy_from_dict({"rules": [{"tool": "delete_*", "action": "nuke"}]})


def test_unknown_condition_type_raises():
    with pytest.raises(PolicyConfigError, match="unknown condition type"):
        policy_from_dict({
            "rules": [
                {"tool": "x", "action": "block", "condition": {"type": "not_a_real_type"}}
            ]
        })


def test_condition_missing_field_raises():
    with pytest.raises(PolicyConfigError, match="missing required field"):
        policy_from_dict({
            "rules": [
                {"tool": "x", "action": "approve", "condition": {"type": "arg_exceeds"}}
            ]
        })


def test_empty_config_is_default_allow():
    policy = policy_from_dict({})
    decision = policy.evaluate("anything", {})
    assert decision.action == Action.ALLOW


def test_policy_from_yaml_string_matches_file_loading():
    yaml_text = """
default_action: allow
rules:
  - name: block-deletes
    tool: "delete_*"
    action: block
    reason: "irreversible action"
"""
    policy = policy_from_yaml_string(yaml_text)
    decision = policy.evaluate("delete_user", {})
    assert decision.action == Action.BLOCK
    assert decision.reason == "irreversible action"


def test_policy_from_yaml_string_empty_text_is_default_allow():
    policy = policy_from_yaml_string("")
    decision = policy.evaluate("anything", {})
    assert decision.action == Action.ALLOW
