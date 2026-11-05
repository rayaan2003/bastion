"""Tests against the real installed langchain_core / langgraph packages, not
a mock of their API."""

import asyncio

import pytest

pytest.importorskip("langchain_core")

from langchain_core.tools import StructuredTool, tool

from bastion import Action, AuditLogger, PolicyEngine, Rule
from bastion.guard import BlockedByPolicy, guard_tools


def _block_deletes() -> PolicyEngine:
    return PolicyEngine().add_rule(
        Rule(tool_pattern="delete_*", action=Action.BLOCK, reason="irreversible")
    )


def _events() -> tuple[AuditLogger, list[str]]:
    actions: list[str] = []
    return AuditLogger(sink=lambda e: actions.append(e.action)), actions


def test_async_only_tool_is_guarded():
    @tool
    async def delete_db(name: str) -> str:
        """Delete a database."""
        return f"deleted {name}"

    audit, actions = _events()
    [guarded] = guard_tools([delete_db], policy=_block_deletes(), audit=audit)

    with pytest.raises(BlockedByPolicy, match="irreversible"):
        asyncio.run(guarded.ainvoke({"name": "prod"}))
    assert actions == ["blocked"]


def test_async_only_tool_allowed_call_runs():
    @tool
    async def lookup(name: str) -> str:
        """Look something up."""
        return f"found {name}"

    audit, actions = _events()
    [guarded] = guard_tools([lookup], policy=_block_deletes(), audit=audit)

    assert asyncio.run(guarded.ainvoke({"name": "x"})) == "found x"
    assert actions == ["allowed"]


def test_tool_with_both_sync_and_async_is_guarded_on_both_paths():
    def _sync(name: str) -> str:
        return f"deleted {name}"

    async def _async(name: str) -> str:
        return f"deleted {name}"

    delete_db = StructuredTool.from_function(
        func=_sync, coroutine=_async, name="delete_db", description="Delete a database."
    )
    audit, actions = _events()
    [guarded] = guard_tools([delete_db], policy=_block_deletes(), audit=audit)

    with pytest.raises(BlockedByPolicy):
        guarded.invoke({"name": "prod"})
    with pytest.raises(BlockedByPolicy):
        asyncio.run(guarded.ainvoke({"name": "prod"}))
    assert actions == ["blocked", "blocked"]
