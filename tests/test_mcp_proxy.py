"""The MCP proxy at the protocol level: raw JSON-RPC lines in, against a
dependency-free server that reports exactly what reached it.
test_mcp_proxy_sdk.py drives it with the real MCP SDK on both ends."""

import asyncio
import json
import os
import select
import sys
import threading
import time
from pathlib import Path
from typing import Any

import pytest

from bastion import Action, AuditLogger, PolicyEngine, Rule
from bastion.approval import ApprovalDecision, ApprovalHandler, AutoDenyHandler
from bastion.audit import AuditEvent
from bastion.mcp_proxy import run_proxy

ECHO_SERVER = str(Path(__file__).parent / "mcp_servers" / "echo.py")

pytestmark = pytest.mark.skipif(sys.platform == "win32", reason="select() on pipes")


class Proxy:
    """run_proxy() on a thread, with the test playing the MCP client."""

    def __init__(self, policy: PolicyEngine, approval_handler: ApprovalHandler | None = None):
        self.events: list[AuditEvent] = []
        client_in_r, client_in_w = os.pipe()
        client_out_r, client_out_w = os.pipe()
        self._to_proxy = os.fdopen(client_in_w, "wb")
        self._from_proxy = os.fdopen(client_out_r, "rb")
        proxy_in, proxy_out = os.fdopen(client_in_r, "rb"), os.fdopen(client_out_w, "wb")
        self.exit_codes: list[int] = []

        def run() -> None:
            code = asyncio.run(
                run_proxy(
                    [sys.executable, ECHO_SERVER],
                    policy=policy,
                    audit=AuditLogger(sink=self.events.append),
                    approval_handler=approval_handler or AutoDenyHandler(),
                    client_in=proxy_in,
                    client_out=proxy_out,
                )
            )
            self.exit_codes.append(code)
            proxy_out.close()

        self._thread = threading.Thread(target=run, daemon=True)
        self._thread.start()
        self._next_id = 100

    def send_line(self, line: bytes) -> None:
        self._to_proxy.write(line + b"\n")
        self._to_proxy.flush()

    def send(self, message: Any) -> None:
        self.send_line(json.dumps(message).encode())

    def request(self, method: str, params: dict[str, Any] | None = None) -> Any:
        self._next_id += 1
        self.send({"jsonrpc": "2.0", "id": self._next_id, "method": method, "params": params})
        return self.recv()

    def call(self, name: str, arguments: dict[str, Any], request_id: Any = 1) -> None:
        self.send(
            {
                "jsonrpc": "2.0",
                "id": request_id,
                "method": "tools/call",
                "params": {"name": name, "arguments": arguments},
            }
        )

    def recv(self, timeout: float = 5) -> Any:
        ready, _, _ = select.select([self._from_proxy], [], [], timeout)
        assert ready, "no message from the proxy"
        return json.loads(self._from_proxy.readline())

    def nothing_to_recv(self) -> bool:
        return not select.select([self._from_proxy], [], [], 0.3)[0]

    def server_received(self) -> list[Any]:
        return self.request("test/received")["result"]["messages"]

    def server_received_lines(self) -> list[str]:
        return self.request("test/received")["result"]["lines"]

    def close(self) -> None:
        self._to_proxy.close()
        self._thread.join(timeout=10)


@pytest.fixture
def make_proxy():
    proxies: list[Proxy] = []

    def make(policy: PolicyEngine, approval_handler: ApprovalHandler | None = None) -> Proxy:
        proxy = Proxy(policy, approval_handler)
        proxies.append(proxy)
        return proxy

    yield make
    for proxy in proxies:
        proxy.close()


def _no_deletes() -> PolicyEngine:
    return PolicyEngine().add_rule(Rule("delete_*", Action.BLOCK, reason="irreversible"))


def _actions(proxy: Proxy) -> list[tuple[str, str]]:
    return [(e.tool_name, e.action) for e in proxy.events]


def test_allowed_call_reaches_the_server_and_its_result_the_client(make_proxy):
    proxy = make_proxy(_no_deletes())
    proxy.call("read_note", {"name": "todo"})

    response = proxy.recv()
    assert response["id"] == 1
    assert response["result"]["content"][0]["text"] == '{"name": "todo"}'
    assert _actions(proxy) == [("read_note", "allowed"), ("read_note", "completed")]
    assert proxy.events[0].call_id == proxy.events[1].call_id


def test_blocked_call_is_answered_by_the_proxy_and_never_reaches_the_server(make_proxy):
    proxy = make_proxy(_no_deletes())
    proxy.call("delete_note", {"name": "todo"}, request_id="abc")

    response = proxy.recv()
    assert response["id"] == "abc"
    assert response["result"]["isError"] is True
    assert response["result"]["content"][0]["text"] == "Tool call blocked by policy: irreversible"
    assert proxy.server_received() == []
    assert _actions(proxy) == [("delete_note", "blocked")]


def test_other_messages_pass_through_untouched(make_proxy):
    proxy = make_proxy(_no_deletes())
    assert proxy.request("initialize", {"protocolVersion": "2026-07-28"})["result"] == {
        "method": "initialize"
    }
    proxy.send({"jsonrpc": "2.0", "method": "notifications/initialized"})
    assert proxy.request("tools/list")["result"] == {"method": "tools/list"}
    assert [m["method"] for m in proxy.server_received()] == [
        "initialize",
        "notifications/initialized",
        "tools/list",
    ]
    assert proxy.events == []


def test_tool_error_result_is_audited_as_failed_with_redaction(make_proxy):
    proxy = make_proxy(_no_deletes())
    proxy.call("fail", {})

    assert proxy.recv()["result"]["isError"] is True
    assert _actions(proxy) == [("fail", "allowed"), ("fail", "failed")]
    assert proxy.events[1].reason == "card [REDACTED:credit_card] declined"


def test_input_required_result_records_no_outcome_yet(make_proxy):
    proxy = make_proxy(_no_deletes())
    proxy.call("needs_input", {})

    assert proxy.recv()["result"]["resultType"] == "input_required"
    assert _actions(proxy) == [("needs_input", "allowed")]


def test_messages_keep_flowing_while_an_approval_is_pending(make_proxy, held_approval):
    policy = PolicyEngine().add_rule(Rule("delete_*", Action.APPROVE, reason="sign-off"))
    proxy = make_proxy(policy, held_approval)
    proxy.call("delete_note", {"name": "todo"}, request_id=7)
    assert held_approval.waiting.wait(timeout=5)

    assert proxy.request("tools/list")["result"] == {"method": "tools/list"}
    held_approval.release.set()

    assert proxy.recv()["id"] == 7
    assert _actions(proxy) == [("delete_note", "approved"), ("delete_note", "completed")]
    assert proxy.events[0].approver == "test:approver"


def test_call_cancelled_during_approval_never_runs(make_proxy, held_approval):
    policy = PolicyEngine().add_rule(Rule("delete_*", Action.APPROVE, reason="sign-off"))
    proxy = make_proxy(policy, held_approval)
    proxy.call("delete_note", {"name": "todo"}, request_id=7)
    assert held_approval.waiting.wait(timeout=5)
    proxy.send(
        {"jsonrpc": "2.0", "method": "notifications/cancelled", "params": {"requestId": 7}}
    )
    # The proxy handles client messages in order, so once this answers, it
    # has seen the cancellation.
    assert [m["method"] for m in proxy.server_received()] == ["notifications/cancelled"]
    held_approval.release.set()

    assert proxy.nothing_to_recv()
    assert [m["method"] for m in proxy.server_received()] == [
        "notifications/cancelled",
        "test/received",
    ]
    deadline = time.monotonic() + 5
    while len(proxy.events) < 2 and time.monotonic() < deadline:
        time.sleep(0.01)
    assert _actions(proxy) == [("delete_note", "approved"), ("delete_note", "failed")]
    assert proxy.events[1].reason == "cancelled by the client before it ran"


def test_approval_handler_error_blocks_the_call(make_proxy):
    class Unreachable(ApprovalHandler):
        def request_approval(self, request):
            raise ConnectionError("slack is down")

    policy = PolicyEngine().add_rule(Rule("delete_*", Action.APPROVE))
    proxy = make_proxy(policy, Unreachable())
    proxy.call("delete_note", {"name": "todo"})

    assert proxy.recv()["result"]["isError"] is True
    assert proxy.server_received() == []
    assert _actions(proxy) == [("delete_note", "blocked")]
    assert "ConnectionError: slack is down" in proxy.events[0].reason


def test_denied_approval_is_answered_by_the_proxy(make_proxy):
    class Deny(ApprovalHandler):
        def request_approval(self, request):
            return ApprovalDecision(approved=False, approver="test:denier")

    policy = PolicyEngine().add_rule(Rule("delete_*", Action.APPROVE, reason="sign-off"))
    proxy = make_proxy(policy, Deny())
    proxy.call("delete_note", {"name": "todo"})

    text = proxy.recv()["result"]["content"][0]["text"]
    assert text == "Tool call blocked by policy: approval denied (sign-off)"
    assert proxy.server_received() == []


def test_batch_containing_a_tool_call_is_refused_whole(make_proxy):
    proxy = make_proxy(_no_deletes())
    proxy.send(
        [
            {"jsonrpc": "2.0", "id": 1, "method": "tools/list"},
            {"jsonrpc": "2.0", "id": 2, "method": "tools/call", "params": {"name": "read_note"}},
        ]
    )

    replies = proxy.recv()
    assert [(r["id"], r["error"]["code"]) for r in replies] == [(1, -32600), (2, -32600)]
    assert proxy.server_received() == []


def test_unparseable_and_id_less_tool_calls_are_dropped(make_proxy):
    proxy = make_proxy(_no_deletes())
    proxy.send_line(b'{"jsonrpc": "2.0", "id": 1, "method": "tools/call"')
    proxy.send({"jsonrpc": "2.0", "method": "tools/call", "params": {"name": "delete_note"}})

    assert proxy.server_received() == []
    assert proxy.events == []


def test_server_sees_the_message_as_checked_not_the_raw_bytes(make_proxy):
    # Python keeps the last duplicate key. Re-encoding means a server whose
    # parser keeps the first can't be handed a different method than the one
    # the proxy checked.
    proxy = make_proxy(_no_deletes())
    proxy.send_line(
        b'{"jsonrpc": "2.0", "id": 1, "method": "tools/call", "method": "tools/list"}'
    )
    assert proxy.recv()["result"] == {"method": "tools/list"}
    [line] = proxy.server_received_lines()
    assert line.count('"method"') == 1
    assert json.loads(line) == {"jsonrpc": "2.0", "id": 1, "method": "tools/list"}


def test_malformed_tool_call_params_are_rejected(make_proxy):
    proxy = make_proxy(_no_deletes())
    proxy.send(
        {"jsonrpc": "2.0", "id": 1, "method": "tools/call", "params": {"name": "x", "arguments": 3}}
    )
    assert proxy.recv()["error"]["code"] == -32602
    assert proxy.server_received() == []


def test_proxy_exits_with_the_server_when_the_client_disconnects(make_proxy):
    proxy = make_proxy(_no_deletes())
    proxy.close()
    assert proxy.exit_codes == [0]


@pytest.mark.parametrize(
    ("meta", "result_type"),
    [
        ({"io.modelcontextprotocol/protocolVersion": "2026-07-28"}, "complete"),
        ({}, None),
    ],
)
def test_blocked_reply_matches_the_requests_protocol_version(make_proxy, meta, result_type):
    # 2026-07-28 clients reject a result without resultType; older ones
    # don't know the field.
    proxy = make_proxy(_no_deletes())
    proxy.send(
        {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "tools/call",
            "params": {"name": "delete_note", "arguments": {}, "_meta": meta},
        }
    )
    assert proxy.recv()["result"].get("resultType") == result_type
