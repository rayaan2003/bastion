"""The MCP proxy between a real MCP client and server, both from the
official SDK, launched the way an MCP client config would launch it."""

import asyncio
import json
import sys
from pathlib import Path

import pytest

pytest.importorskip("mcp")

from mcp import Client, StdioServerParameters

NOTES_SERVER = str(Path(__file__).parent / "mcp_servers" / "notes.py")


def _through_proxy(tmp_path: Path, policy_yaml: str) -> tuple[StdioServerParameters, Path]:
    policy = tmp_path / "policy.yaml"
    policy.write_text(policy_yaml)
    audit_log = tmp_path / "audit.jsonl"
    params = StdioServerParameters(
        command=sys.executable,
        args=[
            "-m", "bastion", "mcp-proxy",
            "--policy", str(policy),
            "--audit-log", str(audit_log),
            "--", sys.executable, NOTES_SERVER,
        ],
    )
    return params, audit_log


def test_policy_is_enforced_between_a_real_client_and_server(tmp_path):
    params, audit_log = _through_proxy(
        tmp_path,
        'rules:\n  - tool: "delete_*"\n    action: block\n    reason: "notes are permanent"\n',
    )

    async def session():
        async with Client(params) as client:
            tools = await client.list_tools()
            read = await client.call_tool("read_note", {"name": "todo"})
            delete = await client.call_tool("delete_note", {"name": "todo"})
            read_again = await client.call_tool("read_note", {"name": "todo"})
            return tools, read, delete, read_again

    tools, read, delete, read_again = asyncio.run(session())

    assert sorted(t.name for t in tools.tools) == ["delete_note", "read_note"]
    assert not read.is_error
    assert read.content[0].text == "buy milk"
    assert delete.is_error
    assert delete.content[0].text == "Tool call blocked by policy: notes are permanent"
    assert read_again.content[0].text == "buy milk", "the blocked delete must not have run"

    events = [json.loads(line) for line in audit_log.read_text().splitlines()]
    assert [(e["tool_name"], e["action"]) for e in events] == [
        ("read_note", "allowed"),
        ("read_note", "completed"),
        ("delete_note", "blocked"),
        ("read_note", "allowed"),
        ("read_note", "completed"),
    ]
