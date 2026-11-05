from bastion import Action, AuditLogger, PolicyEngine, Rule, contains_pii, guard
from bastion.audit import AuditEvent
from bastion.guard import BlockedByPolicy


def _logger(**kwargs) -> tuple[AuditLogger, list[AuditEvent]]:
    events: list[AuditEvent] = []
    return AuditLogger(sink=events.append, **kwargs), events


def test_pii_in_string_args_is_redacted():
    audit, events = _logger()
    audit.record("lookup", {"q": "ssn 123-45-6789 for a.b@example.com"}, "allowed", "ok")
    assert events[0].args == {"q": "ssn [REDACTED:ssn_us] for [REDACTED:email]"}


def test_nested_values_are_redacted_and_structure_kept():
    audit, events = _logger()
    audit.record(
        "send",
        {"to": ["a.b@example.com", "ok"], "meta": {"key": "AKIAABCDEFGHIJKLMNOP", "n": 3}},
        "allowed",
        "ok",
    )
    assert events[0].args == {
        "to": ["[REDACTED:email]", "ok"],
        "meta": {"key": "[REDACTED:aws_access_key_id]", "n": 3},
    }


def test_numeric_card_number_is_redacted():
    audit, events = _logger()
    audit.record("charge", {"card": 4111111111111111, "amount": 40.5}, "allowed", "ok")
    assert events[0].args == {"card": "[REDACTED:credit_card]", "amount": 40.5}


def test_clean_args_are_logged_unchanged():
    audit, events = _logger()
    args = {"q": "weather in Paris", "limit": 5, "exact": True, "tags": None}
    audit.record("search", args, "allowed", "ok")
    assert events[0].args == args


def test_redact_args_false_logs_raw_args():
    audit, events = _logger(redact_args=False)
    audit.record("lookup", {"q": "123-45-6789"}, "allowed", "ok")
    assert events[0].args == {"q": "123-45-6789"}


def test_policy_and_tool_still_see_raw_args():
    received: list[str] = []

    def lookup(q: str) -> str:
        received.append(q)
        return "ok"

    policy = PolicyEngine().add_rule(
        Rule("lookup", Action.BLOCK, condition=contains_pii(["credit_card"]), reason="card")
    )
    audit, events = _logger()
    guarded = guard(lookup, policy=policy, audit=audit)

    guarded(q="ssn 123-45-6789")
    assert received == ["ssn 123-45-6789"]
    try:
        guarded(q="card 4111111111111111")
    except BlockedByPolicy:
        pass
    else:
        raise AssertionError("policy should still see the raw card number")
    assert [e.args for e in events] == [
        {"q": "ssn [REDACTED:ssn_us]"},
        {"q": "card [REDACTED:credit_card]"},
    ]


def test_caller_args_dict_is_not_mutated():
    audit, _ = _logger()
    args = {"q": "123-45-6789", "nested": {"e": "a.b@example.com"}}
    audit.record("lookup", args, "allowed", "ok")
    assert args == {"q": "123-45-6789", "nested": {"e": "a.b@example.com"}}
