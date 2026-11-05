"""Client for the bastion dashboard (dashboard/ in this repo): ship audit
events, route approvals, and fetch policy over its HTTP API.

Uses only the standard library (urllib) - no extra dependency required to
talk to the dashboard. The dashboard's /api/* routes require an API key
(`Authorization: Bearer <key>`, see dashboard/.env.example) - separate from
the browser session cookie a human reviewer uses to log into the UI.
"""

from __future__ import annotations

import atexit
import json
import logging
import queue
import threading
import time
import urllib.request
from typing import Any

from bastion.approval import ApprovalHandler
from bastion.audit import AuditEvent
from bastion.config import policy_from_yaml_string
from bastion.policy import PolicyEngine

_log = logging.getLogger("bastion")

# Enough to ride out a short dashboard outage without unbounded memory growth.
_MAX_PENDING_EVENTS = 10_000


def _post_json(url: str, payload: dict[str, Any], api_key: str) -> dict[str, Any]:
    data = json.dumps(payload, default=str).encode("utf-8")
    request = urllib.request.Request(
        url,
        data=data,
        headers={"Content-Type": "application/json", "Authorization": f"Bearer {api_key}"},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=10) as response:
        result: dict[str, Any] = json.loads(response.read().decode("utf-8"))
        return result


def _get_json(url: str, api_key: str) -> dict[str, Any]:
    request = urllib.request.Request(url, headers={"Authorization": f"Bearer {api_key}"})
    with urllib.request.urlopen(request, timeout=10) as response:
        result: dict[str, Any] = json.loads(response.read().decode("utf-8"))
        return result


class DashboardAuditSink:
    """An AuditLogger sink that ships events to the dashboard's /api/events
    endpoint on a background thread.

    Tool calls never wait on the dashboard and never fail because of it: a
    dashboard that is slow, down, or rejecting the API key gets a logged
    warning (on the `bastion` logger) and the event is dropped. Policy
    enforcement itself is local and unaffected. Pending events are flushed
    at interpreter exit, so short-lived scripts don't lose their last events.
    """

    def __init__(self, base_url: str, api_key: str) -> None:
        self.url = f"{base_url.rstrip('/')}/api/events"
        self.api_key = api_key
        self._queue: queue.Queue[AuditEvent] = queue.Queue(maxsize=_MAX_PENDING_EVENTS)
        self._worker = threading.Thread(target=self._run, name="bastion-audit-sink", daemon=True)
        self._worker.start()
        atexit.register(self.flush)

    def __call__(self, event: AuditEvent) -> None:
        try:
            self._queue.put_nowait(event)
        except queue.Full:
            _log.warning(
                "dashboard audit queue full, dropping event %s (%s)", event.id, event.tool_name
            )

    def flush(self, timeout: float = 10.0) -> bool:
        """Block until every queued event has been sent or has failed.
        Returns False if `timeout` elapsed first."""
        deadline = time.monotonic() + timeout
        # Queue.join() has no timeout, so wait on its condition directly.
        with self._queue.all_tasks_done:
            while self._queue.unfinished_tasks:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    return False
                self._queue.all_tasks_done.wait(remaining)
        return True

    def _run(self) -> None:
        while True:
            event = self._queue.get()
            try:
                _post_json(
                    self.url,
                    {
                        "id": event.id,
                        "timestamp": event.timestamp,
                        "session_id": event.session_id,
                        "tool_name": event.tool_name,
                        "args": event.args,
                        "action": event.action,
                        "reason": event.reason,
                        "call_id": event.call_id,
                    },
                    self.api_key,
                )
            except Exception:
                _log.warning(
                    "failed to ship audit event %s to %s", event.id, self.url, exc_info=True
                )
            finally:
                self._queue.task_done()


def dashboard_audit_sink(base_url: str, api_key: str) -> DashboardAuditSink:
    """Build a sink for AuditLogger that ships events to the dashboard
    instead of writing a local JSONL file:

        AuditLogger(sink=dashboard_audit_sink("http://localhost:3000", api_key))
    """
    return DashboardAuditSink(base_url, api_key)


def load_policy_from_dashboard(base_url: str, api_key: str) -> PolicyEngine:
    """Fetch the policy currently set on the dashboard's /policy page and
    build a PolicyEngine from it - lets a reviewer edit rules in the UI
    instead of hand-editing a local policy.yaml.

        policy = load_policy_from_dashboard("http://localhost:3000", api_key)

    Fetches once at call time; call it again (e.g. on a timer) to pick up
    edits made after the agent process started. Raises ValueError if no
    policy has been saved on the dashboard yet.
    """
    data = _get_json(f"{base_url.rstrip('/')}/api/policy", api_key)
    yaml_text = data.get("yaml_text")
    if not yaml_text:
        raise ValueError(
            "dashboard has no policy configured yet - set one at the dashboard's /policy page"
        )
    return policy_from_yaml_string(yaml_text)


class DashboardApprovalHandler(ApprovalHandler):
    """Creates a pending approval in the dashboard and polls until a
    reviewer approves/denies it from the /approvals page there. Fails
    closed (denies) if nobody responds within `timeout`.
    """

    def __init__(
        self,
        base_url: str,
        api_key: str,
        *,
        poll_interval: float = 5.0,
        timeout: float = 300.0,
    ):
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.poll_interval = poll_interval
        self.timeout = timeout

    def request_approval(self, tool_name: str, args: dict[str, Any], reason: str) -> bool:
        created = _post_json(
            f"{self.base_url}/api/approvals",
            {"tool_name": tool_name, "args": args, "reason": reason},
            self.api_key,
        )
        approval_id = created["id"]

        deadline = time.monotonic() + self.timeout
        while time.monotonic() < deadline:
            current = _get_json(f"{self.base_url}/api/approvals/{approval_id}", self.api_key)
            if current["status"] == "approved":
                return True
            if current["status"] == "denied":
                return False
            time.sleep(self.poll_interval)

        return False  # fail closed: no reviewer response within timeout = denied
