"""Audit logging — every tool call decision gets recorded here.

v1: append-only local JSONL file. Swap `sink` for a network call to a hosted
backend later without changing call sites.
"""

from __future__ import annotations

import json
import threading
import time
import uuid
from collections.abc import Callable
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any


@dataclass
class AuditEvent:
    id: str
    timestamp: float
    session_id: str
    tool_name: str
    args: dict[str, Any]
    action: str
    reason: str


Sink = Callable[[AuditEvent], None]


def _jsonl_sink(path: Path) -> Sink:
    lock = threading.Lock()

    def write(event: AuditEvent) -> None:
        line = json.dumps(asdict(event), default=str)
        with lock, path.open("a", encoding="utf-8") as f:
            f.write(line + "\n")

    return write


class AuditLogger:
    def __init__(self, log_path: str = "agentguard_audit.jsonl", session_id: str | None = None,
                 sink: Sink | None = None):
        self.session_id = session_id or str(uuid.uuid4())
        self.sink = sink or _jsonl_sink(Path(log_path))

    def record(self, tool_name: str, args: dict[str, Any], action: str, reason: str) -> AuditEvent:
        event = AuditEvent(
            id=str(uuid.uuid4()),
            timestamp=time.time(),
            session_id=self.session_id,
            tool_name=tool_name,
            args=args,
            action=action,
            reason=reason,
        )
        self.sink(event)
        return event
