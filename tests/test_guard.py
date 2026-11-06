import asyncio
import contextlib

import pytest

from bastion import Action, AuditLogger, PolicyEngine, Rule, guard
from bastion.approval import (
    ApprovalDecision,
    ApprovalHandler,
    ApprovalRequest,
    AutoDenyHandler,
)
from bastion.audit import AuditEvent
from bastion.guard import BlockedByPolicy


def _guarded(fn, policy: PolicyEngine | None = None):
    events: list[AuditEvent] = []
    audit = AuditLogger(sink=events.append)
    wrapped = guard(
        fn, policy=policy or PolicyEngine(), audit=audit, approval_handler=AutoDenyHandler()
    )
    return wrapped, events


def _actions(events: list[AuditEvent]) -> list[str]:
    return [e.action for e in events]


def test_completed_call_records_decision_then_outcome_under_one_call_id():
    def lookup(q: str) -> str:
        return "ok"

    fn, events = _guarded(lookup)
    assert fn(q="x") == "ok"

    assert _actions(events) == ["allowed", "completed"]
    assert events[0].call_id == events[1].call_id != ""
    assert events[1].args == {}


def test_each_call_gets_its_own_call_id():
    fn, events = _guarded(lambda: "ok")
    fn()
    fn()
    assert events[0].call_id != events[2].call_id


def test_raising_tool_records_failed_with_redacted_error_and_reraises():
    def lookup(q: str) -> str:
        raise ValueError(f"no record for {q}")

    fn, events = _guarded(lookup)
    with pytest.raises(ValueError, match="123-45-6789"):
        fn(q="123-45-6789")

    assert _actions(events) == ["allowed", "failed"]
    assert events[1].reason == "ValueError: no record for [REDACTED:ssn_us]"
    assert events[0].call_id == events[1].call_id


def test_blocked_and_denied_calls_have_no_outcome_event():
    policy = PolicyEngine()
    policy.add_rule(Rule("delete_*", Action.BLOCK))
    policy.add_rule(Rule("refund", Action.APPROVE))

    def delete_x() -> None: ...
    def refund() -> None: ...

    delete, d_events = _guarded(delete_x, policy)
    approve, a_events = _guarded(refund, policy)
    with pytest.raises(BlockedByPolicy):
        delete()
    with pytest.raises(BlockedByPolicy):
        approve()

    assert _actions(d_events) == ["blocked"]
    assert _actions(a_events) == ["denied"]


def test_shadow_event_shares_the_call_id():
    policy = PolicyEngine().add_rule(Rule("lookup", Action.BLOCK, shadow=True))

    def lookup() -> str:
        return "ok"

    fn, events = _guarded(lookup, policy)
    fn()
    assert _actions(events) == ["would_block", "allowed", "completed"]
    assert len({e.call_id for e in events}) == 1


def test_async_tool_outcomes():
    async def ok() -> str:
        return "ok"

    async def boom() -> str:
        raise RuntimeError("down")

    ok_fn, ok_events = _guarded(ok)
    boom_fn, boom_events = _guarded(boom)
    assert asyncio.run(ok_fn()) == "ok"
    with pytest.raises(RuntimeError):
        asyncio.run(boom_fn())

    assert _actions(ok_events) == ["allowed", "completed"]
    assert _actions(boom_events) == ["allowed", "failed"]
    assert boom_events[1].reason == "RuntimeError: down"


def test_record_generates_call_id_when_not_given():
    events: list[AuditEvent] = []
    AuditLogger(sink=events.append).record("t", {}, "allowed", "r")
    assert events[0].call_id


class _Recording(ApprovalHandler):
    def __init__(self, decision: ApprovalDecision) -> None:
        self.decision = decision
        self.requests: list[ApprovalRequest] = []

    def request_approval(self, request: ApprovalRequest) -> ApprovalDecision:
        self.requests.append(request)
        return self.decision


@pytest.mark.parametrize(
    ("decision", "expected"),
    [
        (ApprovalDecision(approved=True, approver="slack:U1"), ["approved", "completed"]),
        (ApprovalDecision(approved=False, approver="slack:U2"), ["denied"]),
        (ApprovalDecision(approved=False), ["denied"]),
    ],
)
def test_approver_is_audited_and_request_carries_the_call_ids(decision, expected):
    handler = _Recording(decision)
    events: list[AuditEvent] = []
    policy = PolicyEngine().add_rule(Rule("refund", Action.APPROVE, reason="needs review"))

    def refund(amount: int) -> str:
        return "ok"

    fn = guard(
        refund,
        policy=policy,
        audit=AuditLogger(session_id="sess-7", sink=events.append),
        approval_handler=handler,
    )
    with contextlib.suppress(BlockedByPolicy):
        fn(amount=500)

    assert _actions(events) == expected
    assert events[0].approver == decision.approver
    [request] = handler.requests
    assert request == ApprovalRequest(
        tool_name="refund",
        args={"amount": 500},
        reason="needs review",
        call_id=events[0].call_id,
        session_id="sess-7",
    )


def test_async_calls_keep_running_while_an_approval_is_pending(held_approval):
    async def refund() -> str:
        return "refunded"

    async def lookup() -> str:
        return "found"

    events: list[AuditEvent] = []
    audit = AuditLogger(sink=events.append)
    policy = PolicyEngine().add_rule(Rule("refund", Action.APPROVE, reason="money"))
    guarded_refund = guard(refund, policy=policy, audit=audit, approval_handler=held_approval)
    guarded_lookup = guard(lookup, policy=policy, audit=audit, approval_handler=held_approval)

    results = held_approval.run_alongside(guarded_refund, guarded_lookup)

    assert results == ("refunded", "found")
    assert [(e.tool_name, e.action) for e in events] == [
        ("lookup", "allowed"),
        ("lookup", "completed"),
        ("refund", "approved"),
        ("refund", "completed"),
    ]


def test_async_approval_denied_raises():
    async def refund() -> str:
        return "refunded"

    policy = PolicyEngine().add_rule(Rule("refund", Action.APPROVE, reason="money"))
    fn, events = _guarded(refund, policy)
    with pytest.raises(BlockedByPolicy, match="approval denied"):
        asyncio.run(fn())
    assert [(e.action, e.approver) for e in events] == [("denied", "auto-deny")]
