"""Dashboard integration: ship audit events and route approvals through the
agentguard dashboard's HTTP API instead of a local JSONL file / Slack.

Uses only the standard library (urllib) - no extra dependency required to
talk to the dashboard.
"""

from __future__ import annotations

import json
import time
import urllib.request
from typing import Any

from agentguard.approval import ApprovalHandler
from agentguard.audit import AuditEvent, Sink


def _post_json(url: str, payload: dict[str, Any]) -> dict[str, Any]:
    data = json.dumps(payload).encode("utf-8")
    request = urllib.request.Request(
        url, data=data, headers={"Content-Type": "application/json"}, method="POST"
    )
    with urllib.request.urlopen(request, timeout=10) as response:
        result: dict[str, Any] = json.loads(response.read().decode("utf-8"))
        return result


def _get_json(url: str) -> dict[str, Any]:
    with urllib.request.urlopen(url, timeout=10) as response:
        result: dict[str, Any] = json.loads(response.read().decode("utf-8"))
        return result


def dashboard_audit_sink(base_url: str) -> Sink:
    """Build a Sink for AuditLogger that POSTs events to the dashboard's
    /api/events endpoint instead of writing a local JSONL file.

        AuditLogger(sink=dashboard_audit_sink("http://localhost:3000"))
    """
    url = f"{base_url.rstrip('/')}/api/events"

    def sink(event: AuditEvent) -> None:
        _post_json(url, {
            "id": event.id,
            "timestamp": event.timestamp,
            "session_id": event.session_id,
            "tool_name": event.tool_name,
            "args": event.args,
            "action": event.action,
            "reason": event.reason,
        })

    return sink


class DashboardApprovalHandler(ApprovalHandler):
    """Creates a pending approval in the dashboard and polls until a
    reviewer approves/denies it from the /approvals page there. Fails
    closed (denies) if nobody responds within `timeout`.
    """

    def __init__(self, base_url: str, *, poll_interval: float = 5.0, timeout: float = 300.0):
        self.base_url = base_url.rstrip("/")
        self.poll_interval = poll_interval
        self.timeout = timeout

    def request_approval(self, tool_name: str, args: dict[str, Any], reason: str) -> bool:
        created = _post_json(f"{self.base_url}/api/approvals", {
            "tool_name": tool_name,
            "args": args,
            "reason": reason,
        })
        approval_id = created["id"]

        deadline = time.monotonic() + self.timeout
        while time.monotonic() < deadline:
            current = _get_json(f"{self.base_url}/api/approvals/{approval_id}")
            if current["status"] == "approved":
                return True
            if current["status"] == "denied":
                return False
            time.sleep(self.poll_interval)

        return False  # fail closed: no reviewer response within timeout = denied
