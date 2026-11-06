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

from bastion.scanning import redact, scan_text


@dataclass
class AuditEvent:
    id: str
    timestamp: float
    session_id: str
    tool_name: str
    args: dict[str, Any]
    action: str
    reason: str
    # Shared by every event about one tool call: any would_* event, the
    # decision, and the completed/failed outcome.
    call_id: str = ""
    # Who approved or denied, on `approved` / `denied` events.
    approver: str = ""


Sink = Callable[[AuditEvent], None]


def _jsonl_sink(path: Path) -> Sink:
    lock = threading.Lock()

    def write(event: AuditEvent) -> None:
        line = json.dumps(asdict(event), default=str)
        with lock, path.open("a", encoding="utf-8") as f:
            f.write(line + "\n")

    return write


def _redacted(value: Any) -> Any:
    if isinstance(value, str):
        return redact(value)
    if isinstance(value, dict):
        return {k: _redacted(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_redacted(v) for v in value]
    # A card number passed as an int is still a card number.
    if isinstance(value, int | float) and not isinstance(value, bool):
        text = str(value)
        return redact(text) if scan_text(text) else value
    return value


class AuditLogger:
    """Records every policy decision to `sink` (a local JSONL file by default).

    redact_args: PII/secrets detected in tool-call args (see bastion.scanning)
    are masked in the logged copy. Policy evaluation and the tool itself
    still get the raw args — only what's written to the audit log changes.
    """

    def __init__(
        self,
        log_path: str = "bastion_audit.jsonl",
        session_id: str | None = None,
        sink: Sink | None = None,
        *,
        redact_args: bool = True,
    ):
        self.session_id = session_id or str(uuid.uuid4())
        self.sink = sink or _jsonl_sink(Path(log_path))
        self.redact_args = redact_args

    def record(
        self,
        tool_name: str,
        args: dict[str, Any],
        action: str,
        reason: str,
        *,
        call_id: str | None = None,
        approver: str = "",
    ) -> AuditEvent:
        event = AuditEvent(
            id=str(uuid.uuid4()),
            timestamp=time.time(),
            session_id=self.session_id,
            tool_name=tool_name,
            args=_redacted(args) if self.redact_args else args,
            action=action,
            reason=reason,
            call_id=call_id or str(uuid.uuid4()),
            approver=approver,
        )
        self.sink(event)
        return event
