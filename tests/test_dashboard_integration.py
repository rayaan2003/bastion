import json
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest

from agentguard.audit import AuditEvent
from agentguard.integrations.dashboard import DashboardApprovalHandler, dashboard_audit_sink


class _FakeDashboardServer:
    """A minimal stand-in for the real dashboard's API, serving real HTTP
    on a background thread, so the SDK's urllib calls are exercised for
    real rather than mocked."""

    def __init__(self, approve_after: int = 1):
        self.received_events: list[dict] = []
        self.approvals: dict[str, dict] = {}
        self.get_counts: dict[str, int] = {}
        self.approve_after = approve_after

        handler = self._make_handler()
        self.httpd = HTTPServer(("127.0.0.1", 0), handler)
        self.port = self.httpd.server_address[1]
        self.thread = threading.Thread(target=self.httpd.serve_forever, daemon=True)
        self.thread.start()

    @property
    def base_url(self) -> str:
        return f"http://127.0.0.1:{self.port}"

    def shutdown(self) -> None:
        self.httpd.shutdown()
        self.thread.join(timeout=2)

    def _make_handler(self):
        server = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, fmt, *args):
                pass  # silence request logging in test output

            def _send_json(self, status: int, payload: dict) -> None:
                body = json.dumps(payload).encode("utf-8")
                self.send_response(status)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def do_POST(self):
                length = int(self.headers.get("Content-Length", 0))
                body = json.loads(self.rfile.read(length) or b"{}")

                if self.path == "/api/events":
                    server.received_events.append(body)
                    self._send_json(201, {"ok": True})
                    return

                if self.path == "/api/approvals":
                    approval_id = f"appr-{len(server.approvals) + 1}"
                    server.approvals[approval_id] = {"id": approval_id, "status": "pending", **body}
                    server.get_counts[approval_id] = 0
                    self._send_json(201, server.approvals[approval_id])
                    return

                self._send_json(404, {"error": "not found"})

            def do_GET(self):
                prefix = "/api/approvals/"
                if self.path.startswith(prefix):
                    approval_id = self.path[len(prefix):]
                    server.get_counts[approval_id] = server.get_counts.get(approval_id, 0) + 1
                    if server.get_counts[approval_id] >= server.approve_after:
                        server.approvals[approval_id]["status"] = "approved"
                    self._send_json(200, server.approvals[approval_id])
                    return
                self._send_json(404, {"error": "not found"})

        return Handler


@pytest.fixture
def fake_server():
    server = _FakeDashboardServer(approve_after=2)
    yield server
    server.shutdown()


def test_dashboard_audit_sink_posts_event(fake_server):
    sink = dashboard_audit_sink(fake_server.base_url)
    event = AuditEvent(
        id="evt-1",
        timestamp=123.0,
        session_id="sess-1",
        tool_name="delete_user",
        args={"id": "u1"},
        action="blocked",
        reason="irreversible",
    )
    sink(event)

    assert len(fake_server.received_events) == 1
    assert fake_server.received_events[0]["tool_name"] == "delete_user"
    assert fake_server.received_events[0]["action"] == "blocked"


def test_dashboard_approval_handler_polls_until_approved(fake_server):
    handler = DashboardApprovalHandler(fake_server.base_url, poll_interval=0.01, timeout=5)
    result = handler.request_approval("transfer_funds", {"amount": 600}, "large transfer")
    assert result is True


def test_dashboard_approval_handler_denies_on_timeout():
    server = _FakeDashboardServer(approve_after=10_000)  # never approves within the timeout
    try:
        handler = DashboardApprovalHandler(server.base_url, poll_interval=0.01, timeout=0.1)
        result = handler.request_approval("transfer_funds", {"amount": 600}, "large transfer")
        assert result is False
    finally:
        server.shutdown()
