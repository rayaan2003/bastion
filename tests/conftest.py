import asyncio
import threading
from collections.abc import Awaitable, Callable
from concurrent.futures import ThreadPoolExecutor
from typing import Any

import pytest

from bastion.approval import ApprovalDecision, ApprovalHandler, ApprovalRequest


class HeldApproval(ApprovalHandler):
    """Approves once released; until then blocks, like a human who hasn't
    answered in Slack yet."""

    def __init__(self) -> None:
        self.waiting = threading.Event()
        self.release = threading.Event()

    def request_approval(self, request: ApprovalRequest) -> ApprovalDecision:
        self.waiting.set()
        if not self.release.wait(timeout=5):
            raise AssertionError("approval was never released")
        return ApprovalDecision(approved=True, approver="test:approver")

    def run_alongside(
        self,
        needs_approval: Callable[[], Awaitable[Any]],
        allowed: Callable[[], Awaitable[Any]],
    ) -> tuple[Any, Any]:
        """Start `needs_approval`, and while its approval is pending run
        `allowed` to completion. Returns both results.

        The loop's default executor gets a single thread, so this also
        fails if the approval wait occupies it: the OpenAI Agents SDK runs
        sync tools there.
        """

        async def scenario() -> tuple[Any, Any]:
            asyncio.get_running_loop().set_default_executor(ThreadPoolExecutor(max_workers=1))
            pending = asyncio.ensure_future(needs_approval())

            async def approval_requested() -> None:
                while not self.waiting.is_set():
                    await asyncio.sleep(0.01)

            await asyncio.wait_for(approval_requested(), timeout=2)
            try:
                allowed_result = await asyncio.wait_for(allowed(), timeout=2)
            finally:
                self.release.set()
            return await pending, allowed_result

        return asyncio.run(scenario())


@pytest.fixture
def held_approval() -> HeldApproval:
    return HeldApproval()

