"""End to end: the real Python SDK against a running dashboard and Postgres.

Skipped unless BASTION_E2E_URL points at a dashboard. CI's `dashboard-e2e`
job starts one on a database seeded with the v0.1.0 schema plus one row
written the v0.1.0 way, so these tests also prove the startup migrations.
"""

import http.client
import json
import os
import threading
import time
import urllib.parse
import uuid
from typing import Any

import pytest

from bastion import Action, AuditLogger, PolicyEngine, Rule, guard
from bastion.approval import ApprovalDecision, ApprovalRequest
from bastion.dashboard import (
    DashboardApprovalHandler,
    dashboard_audit_sink,
    load_policy_from_dashboard,
)

URL = os.environ.get("BASTION_E2E_URL", "")
API_KEY = os.environ.get("BASTION_E2E_API_KEY", "")
PASSWORD = os.environ.get("BASTION_E2E_PASSWORD", "")

pytestmark = pytest.mark.skipif(not URL, reason="needs a running dashboard (BASTION_E2E_URL)")


def _request(
    method: str, path: str, *, body: bytes | None = None, headers: dict[str, str] | None = None
) -> tuple[int, dict[str, str], str]:
    # http.client rather than urllib: no redirect following, and no cookie
    # jar dropping the dashboard's Secure session cookie over plain http.
    parsed = urllib.parse.urlparse(URL)
    conn = http.client.HTTPConnection(parsed.hostname or "localhost", parsed.port, timeout=30)
    try:
        conn.request(method, path, body=body, headers=headers or {})
        response = conn.getresponse()
        return response.status, dict(response.getheaders()), response.read().decode()
    finally:
        conn.close()


def _api(method: str, path: str, payload: dict[str, Any] | None = None, key: str = API_KEY):
    headers = {"Authorization": f"Bearer {key}", "Content-Type": "application/json"}
    body = json.dumps(payload).encode() if payload is not None else None
    status, _, text = _request(method, path, body=body, headers=headers)
    return status, json.loads(text) if text else None


def _form(path: str, fields: dict[str, str], cookie: str = "") -> tuple[int, str]:
    headers = {"Content-Type": "application/x-www-form-urlencoded"}
    if cookie:
        headers["Cookie"] = cookie
    status, response_headers, _ = _request(
        "POST", path, body=urllib.parse.urlencode(fields).encode(), headers=headers
    )
    return status, response_headers.get("Location", "")


def _events(**query: str) -> list[dict[str, Any]]:
    status, data = _api("GET", f"/api/events?{urllib.parse.urlencode(query)}")
    assert status == 200
    return sorted(data["events"], key=lambda e: e["timestamp"])


@pytest.fixture(scope="module")
def session_cookie() -> str:
    parsed = urllib.parse.urlparse(URL)
    conn = http.client.HTTPConnection(parsed.hostname or "localhost", parsed.port, timeout=30)
    conn.request(
        "POST",
        "/api/auth/login",
        body=urllib.parse.urlencode({"password": PASSWORD}).encode(),
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )
    response = conn.getresponse()
    set_cookie = response.getheader("Set-Cookie") or ""
    conn.close()
    assert response.status == 303
    assert set_cookie, "login didn't set a session cookie"
    return set_cookie.split(";", 1)[0]


def _page(path: str, cookie: str) -> tuple[int, str, str]:
    status, headers, text = _request("GET", path, headers={"Cookie": cookie})
    return status, text, headers.get("Location", "")


def test_api_rejects_a_wrong_key():
    status, _ = _api("GET", "/api/events", key="wrong-key")
    assert status == 401


def test_row_written_before_the_migrations_survives_them():
    [legacy] = _events(session_id="legacy-sess")
    assert legacy["id"] == "legacy-1"
    assert legacy["call_id"] is None
    assert legacy["approver"] is None


def test_events_round_trip_with_outcomes_and_redaction():
    session = f"e2e-{uuid.uuid4()}"
    sink = dashboard_audit_sink(URL, API_KEY)
    audit = AuditLogger(session_id=session, sink=sink)

    def lookup(q: str) -> str:
        return "ok"

    def charge(card: str) -> str:
        raise RuntimeError(f"declined card {card}")

    guard(lookup, policy=PolicyEngine(), audit=audit)(q="hello")
    with pytest.raises(RuntimeError):
        guard(charge, policy=PolicyEngine(), audit=audit)(card="4111111111111111")
    assert sink.flush(timeout=30)

    rows = _events(session_id=session)
    by_tool = {
        tool: [r["action"] for r in rows if r["tool_name"] == tool] for tool in ("lookup", "charge")
    }
    assert by_tool == {"lookup": ["allowed", "completed"], "charge": ["allowed", "failed"]}

    charge_rows = [r for r in rows if r["tool_name"] == "charge"]
    assert charge_rows[0]["args"] == {"card": "[REDACTED:credit_card]"}
    assert charge_rows[1]["reason"] == "RuntimeError: declined card [REDACTED:credit_card]"
    assert charge_rows[0]["call_id"] == charge_rows[1]["call_id"]
    assert [r["action"] for r in _events(call_id=charge_rows[0]["call_id"])] == [
        "allowed",
        "failed",
    ]


@pytest.fixture(scope="module")
def approved_call() -> str:
    """Run one approval through the dashboard and approve it via the API, the
    way a reviewer's decision reaches the SDK. Returns the call_id."""
    session = f"e2e-{uuid.uuid4()}"
    sink = dashboard_audit_sink(URL, API_KEY)
    audit = AuditLogger(session_id=session, sink=sink)
    handler = DashboardApprovalHandler(URL, API_KEY, poll_interval=0.2, timeout=60)
    policy = PolicyEngine().add_rule(Rule("refund", Action.APPROVE, reason="refunds need review"))

    def refund(amount: int) -> str:
        return f"refunded {amount}"

    results: list[Any] = []
    worker = threading.Thread(
        target=lambda: results.append(
            guard(refund, policy=policy, audit=audit, approval_handler=handler)(amount=250)
        )
    )
    worker.start()

    pending: dict[str, Any] | None = None
    deadline = time.monotonic() + 30
    while pending is None and time.monotonic() < deadline:
        _, data = _api("GET", "/api/approvals?status=pending")
        pending = next((a for a in data["approvals"] if a["session_id"] == session), None)
        time.sleep(0.2)
    assert pending is not None, "approval request never reached the dashboard"
    assert pending["tool_name"] == "refund"
    assert pending["call_id"]

    decide_path = f"/api/approvals/{pending['id']}/decide"
    status, decided = _api("POST", decide_path, {"decision": "approved"})
    assert status == 200
    assert decided["decided_by"] == "api"
    again, _ = _api("POST", decide_path, {"decision": "denied"})
    assert again == 404, "an already-decided approval must not be overwritten"

    worker.join(timeout=30)
    assert results == ["refunded 250"]
    assert sink.flush(timeout=30)
    call_id: str = pending["call_id"]
    return call_id


def test_dashboard_approval_records_the_approver(approved_call):
    rows = _events(call_id=approved_call)
    assert [(r["action"], r["approver"]) for r in rows] == [
        ("approved", "dashboard:api"),
        ("completed", None),
    ]


def test_dashboard_approval_handler_returns_the_decision():
    # The fixture covers the guard() path; this checks the handler's own
    # return value against a real decision.
    handler = DashboardApprovalHandler(URL, API_KEY, poll_interval=0.2, timeout=60)
    session = f"e2e-{uuid.uuid4()}"
    decisions: list[ApprovalDecision] = []
    request = ApprovalRequest("wire", {"amount": 9}, "check", f"call-{uuid.uuid4()}", session)
    worker = threading.Thread(target=lambda: decisions.append(handler.request_approval(request)))
    worker.start()

    pending = None
    deadline = time.monotonic() + 30
    while pending is None and time.monotonic() < deadline:
        _, data = _api("GET", "/api/approvals?status=pending")
        pending = next((a for a in data["approvals"] if a["call_id"] == request.call_id), None)
        time.sleep(0.2)
    assert pending is not None
    _api("POST", f"/api/approvals/{pending['id']}/decide", {"decision": "denied"})
    worker.join(timeout=30)

    assert decisions == [ApprovalDecision(approved=False, approver="dashboard:api")]


def test_ui_requires_login():
    status, _, location = _page("/audit", cookie="")
    assert status in (302, 307)
    assert "/login" in location


def test_audit_page_shows_the_call_trail_and_approver(session_cookie, approved_call):
    status, html, _ = _page(f"/audit?call_id={approved_call}", session_cookie)
    assert status == 200
    assert "by dashboard:api" in html
    assert html.count('class="border-b border-neutral-900"') == 2


def test_policy_saved_in_the_ui_is_enforced_by_the_sdk(session_cookie):
    tool = f"e2e_tool_{uuid.uuid4().hex[:8]}"
    yaml_text = f'rules:\n  - tool: "{tool}"\n    action: block\n    reason: "set from the UI"\n'

    status, location = _form("/policy/save", {"yaml_text": yaml_text}, session_cookie)
    assert status == 303
    assert "saved=1" in location

    status, location = _form("/policy/save", {"yaml_text": "rules: [unclosed"}, session_cookie)
    assert status == 303
    assert "error=" in location

    # The invalid save above must not have replaced the valid one.
    decision = load_policy_from_dashboard(URL, API_KEY).evaluate(tool, {})
    assert decision.action == Action.BLOCK
    assert decision.reason == "set from the UI"
