"""Enforce bastion policy on any MCP server's tool calls, with no code changes.

    bastion mcp-proxy --policy policy.yaml -- npx -y @modelcontextprotocol/server-github

The proxy sits between an MCP client (Claude Desktop, Cursor, Claude Code,
...) and one stdio MCP server, which it starts. Messages pass through
unchanged in both directions except `tools/call` requests. Those go through
policy first. Allowed calls are forwarded. Blocked or denied ones get an
error result the model can read, and the server never sees them.

It relays JSON-RPC lines instead of using the MCP SDK, so it needs no
dependency and passes resources, prompts, sampling and newer protocol
features through without knowing about them.
"""

from __future__ import annotations

import asyncio
import json
import sys
import threading
import uuid
from collections.abc import Sequence
from typing import IO, Any

from bastion.approval import ApprovalHandler
from bastion.audit import AuditLogger
from bastion.guard import describe_error, evaluate_and_record_async, record_outcome
from bastion.policy import PolicyEngine

# asyncio's default of 64 KiB per line is too small: a single result can
# carry a whole file.
_MAX_LINE = 256 * 1024 * 1024
_INVALID_REQUEST = -32600
_INVALID_PARAMS = -32602
# How long a server gets to exit after the client disconnects.
_SHUTDOWN_GRACE = 5.0
# Results must carry "resultType" from this protocol version on. Version
# strings are dates, so they compare as strings.
_RESULT_TYPE_SINCE = "2026-07-28"
_VERSION_META = "io.modelcontextprotocol/protocolVersion"


async def run_proxy(
    command: Sequence[str],
    *,
    policy: PolicyEngine,
    audit: AuditLogger,
    approval_handler: ApprovalHandler,
    client_in: IO[bytes] | None = None,
    client_out: IO[bytes] | None = None,
) -> int:
    """Start `command` as the upstream MCP server and relay between it and
    the client on `client_in`/`client_out` (default stdin/stdout) until
    either side closes. Returns the server's exit code."""
    upstream = await asyncio.create_subprocess_exec(
        *command, stdin=asyncio.subprocess.PIPE, stdout=asyncio.subprocess.PIPE, limit=_MAX_LINE
    )
    proxy = _Proxy(
        upstream,
        policy=policy,
        audit=audit,
        approval_handler=approval_handler,
        client_out=client_out or sys.stdout.buffer,
    )
    return await proxy.run(client_in or sys.stdin.buffer)


class _Proxy:
    def __init__(
        self,
        upstream: asyncio.subprocess.Process,
        *,
        policy: PolicyEngine,
        audit: AuditLogger,
        approval_handler: ApprovalHandler,
        client_out: IO[bytes],
    ) -> None:
        self.upstream = upstream
        self.policy = policy
        self.audit = audit
        self.approval_handler = approval_handler
        self.client_out = client_out
        # Keyed by the JSON-encoded request id, so 1 and "1" stay distinct.
        self.deciding: set[str] = set()
        self.cancelled: set[str] = set()
        self.forwarded: dict[str, tuple[str, str]] = {}  # -> (tool_name, call_id)
        self.tasks: set[asyncio.Task[None]] = set()
        # From `initialize`, before 2026-07-28; later requests carry their own.
        self.session_version = ""
        # Python 3.10's StreamWriter asserts if two drain() calls overlap.
        self.upstream_lock = asyncio.Lock()

    async def run(self, client_in: IO[bytes]) -> int:
        client_lines: asyncio.Queue[bytes] = asyncio.Queue()
        loop = asyncio.get_running_loop()

        # A thread rather than connect_read_pipe: that doesn't take a regular
        # file or console stdin, and isn't available on Windows' default loop.
        def read_client() -> None:
            for line in iter(client_in.readline, b""):
                loop.call_soon_threadsafe(client_lines.put_nowait, line)
            loop.call_soon_threadsafe(client_lines.put_nowait, b"")

        threading.Thread(target=read_client, name="bastion-mcp-client", daemon=True).start()

        relay_client = asyncio.ensure_future(self._relay_client(client_lines))
        await self._relay_upstream()
        relay_client.cancel()
        for task in self.tasks:
            task.cancel()
        return await self.upstream.wait()

    async def _relay_client(self, lines: asyncio.Queue[bytes]) -> None:
        assert self.upstream.stdin is not None
        while line := await lines.get():
            if line.strip():
                await self._from_client(line)
        self.upstream.stdin.close()
        try:
            await asyncio.wait_for(self.upstream.wait(), _SHUTDOWN_GRACE)
        except asyncio.TimeoutError:
            self.upstream.terminate()

    async def _relay_upstream(self) -> None:
        assert self.upstream.stdout is not None
        while line := await self.upstream.stdout.readline():
            self._from_upstream(line)

    async def _from_client(self, line: bytes) -> None:
        try:
            message = json.loads(line)
        except ValueError:
            # Unreadable here means it can't be checked, so it doesn't go through.
            _log(f"dropped a message from the client that isn't valid JSON: {line[:200]!r}")
            return

        if isinstance(message, list):
            if any(_is_tool_call(m) for m in message):
                # Batches were dropped from MCP in 2025-06-18; refuse the
                # whole batch rather than split one.
                self._reply_batch_error(message)
                return
        elif _is_tool_call(message):
            if "id" not in message:
                _log("dropped a tools/call sent without an id")
                return
            task = asyncio.ensure_future(self._tool_call(message))
            self.tasks.add(task)
            task.add_done_callback(self.tasks.discard)
            return
        elif isinstance(message, dict) and message.get("method") == "notifications/cancelled":
            params = message.get("params")
            request_id = params.get("requestId") if isinstance(params, dict) else None
            key = _key(request_id)
            if key in self.deciding:
                self.cancelled.add(key)

        await self._to_upstream(message)

    async def _tool_call(self, message: dict[str, Any]) -> None:
        request_id = message["id"]
        key = _key(request_id)
        params = message.get("params")
        name = params.get("name") if isinstance(params, dict) else None
        args = params.get("arguments", {}) if isinstance(params, dict) else None
        if args is None:
            args = {}
        if not isinstance(name, str) or not isinstance(args, dict):
            self._reply_error(
                request_id, _INVALID_PARAMS, "tools/call needs a string name and object arguments"
            )
            return

        call_id = str(uuid.uuid4())
        self.deciding.add(key)
        try:
            allowed, reason = await evaluate_and_record_async(
                name,
                args,
                policy=self.policy,
                audit=self.audit,
                approval_handler=self.approval_handler,
                call_id=call_id,
            )
        except Exception as e:
            # e.g. Slack unreachable. Fail closed, and say so in the audit log.
            reason = f"bastion couldn't decide: {describe_error(e)}"
            self.audit.record(name, args, "blocked", reason, call_id=call_id)
            allowed = False
        finally:
            self.deciding.discard(key)

        if key in self.cancelled:
            # The client gave up while a human was deciding; per spec, no reply.
            self.cancelled.discard(key)
            if allowed:
                record_outcome(self.audit, name, call_id, "cancelled by the client before it ran")
            return
        if not allowed:
            result: dict[str, Any] = {
                "content": [{"type": "text", "text": f"Tool call blocked by policy: {reason}"}],
                "isError": True,
            }
            if (_request_version(params) or self.session_version) >= _RESULT_TYPE_SINCE:
                result["resultType"] = "complete"
            self._reply(request_id, result)
            return
        self.forwarded[key] = (name, call_id)
        await self._to_upstream(message)

    def _from_upstream(self, line: bytes) -> None:
        try:
            message = json.loads(line)
        except ValueError:
            message = None
        if isinstance(message, dict) and "method" not in message:
            call = self.forwarded.pop(_key(message.get("id")), None)
            if call is not None:
                self._record_outcome(*call, message)
            result = message.get("result")
            if isinstance(result, dict) and "serverInfo" in result:
                version = result.get("protocolVersion")
                self.session_version = version if isinstance(version, str) else ""
        self._write_client(line if line.endswith(b"\n") else line + b"\n")

    def _record_outcome(self, tool_name: str, call_id: str, response: dict[str, Any]) -> None:
        error = response.get("error")
        if error is not None:
            detail = error.get("message", "") if isinstance(error, dict) else str(error)
            record_outcome(self.audit, tool_name, call_id, f"MCP error: {detail}")
            return
        result = response.get("result")
        if not isinstance(result, dict):
            record_outcome(self.audit, tool_name, call_id)
            return
        if result.get("resultType") == "input_required" or "task" in result:
            # Not finished: the client retries with more input, or polls a
            # task. A retry is a new tools/call and is checked again.
            return
        if result.get("isError"):
            text = " ".join(
                str(c.get("text", ""))
                for c in result.get("content", [])
                if isinstance(c, dict) and c.get("type") == "text"
            )
            record_outcome(self.audit, tool_name, call_id, text or "tool reported an error")
            return
        record_outcome(self.audit, tool_name, call_id)

    async def _to_upstream(self, message: Any) -> None:
        assert self.upstream.stdin is not None
        # Re-encoded, not the client's original bytes: the server must see
        # exactly what was checked, even if its JSON parser treats duplicate
        # keys or odd escapes differently.
        try:
            data = json.dumps(message, allow_nan=False).encode() + b"\n"
        except ValueError:
            _log("dropped a message from the client containing NaN or Infinity")
            return
        async with self.upstream_lock:
            try:
                self.upstream.stdin.write(data)
                await self.upstream.stdin.drain()
            except (BrokenPipeError, ConnectionResetError):
                pass  # the server exited; _relay_upstream sees EOF and stops

    def _reply(self, request_id: Any, result: dict[str, Any]) -> None:
        self._write_json({"jsonrpc": "2.0", "id": request_id, "result": result})

    def _reply_error(self, request_id: Any, code: int, message: str) -> None:
        self._write_json(
            {"jsonrpc": "2.0", "id": request_id, "error": {"code": code, "message": message}}
        )

    def _reply_batch_error(self, batch: list[Any]) -> None:
        error = {
            "code": _INVALID_REQUEST,
            "message": "bastion: batches containing tools/call aren't allowed",
        }
        replies = [
            {"jsonrpc": "2.0", "id": m["id"], "error": error}
            for m in batch
            if isinstance(m, dict) and "id" in m and "method" in m
        ]
        if replies:
            self._write_json(replies)

    def _write_json(self, message: Any) -> None:
        self._write_client(json.dumps(message).encode() + b"\n")

    def _write_client(self, data: bytes) -> None:
        self.client_out.write(data)
        self.client_out.flush()


def _is_tool_call(message: Any) -> bool:
    return isinstance(message, dict) and message.get("method") == "tools/call"


def _request_version(params: Any) -> str:
    meta = params.get("_meta") if isinstance(params, dict) else None
    version = meta.get(_VERSION_META) if isinstance(meta, dict) else None
    return version if isinstance(version, str) else ""


def _key(request_id: Any) -> str:
    return json.dumps(request_id)


def _log(text: str) -> None:
    # stdout is the MCP channel, so anything human-readable goes to stderr,
    # which MCP clients show in their server logs.
    print(f"[bastion] {text}", file=sys.stderr, flush=True)
