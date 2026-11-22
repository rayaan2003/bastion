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

from bastion.audit_chain import event_hash
from bastion.scanning import redact_value


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
    # Hash chain linking every event from one AuditLogger; see
    # bastion.audit_chain.
    chain_id: str = ""
    seq: int = 0
    prev_hash: str = ""
    hash: str = ""


Sink = Callable[[AuditEvent], None]


def _jsonl_sink(path: Path) -> Sink:
    lock = threading.Lock()

    def write(event: AuditEvent) -> None:
        line = json.dumps(asdict(event), default=str)
        with lock, path.open("a", encoding="utf-8") as f:
            f.write(line + "\n")

    return write


class AuditLogger:
    """Records every policy decision to `sink` (a local JSONL file by default).

    redact_args: PII/secrets detected in tool-call args (see bastion.scanning)
    are masked in the logged copy. Policy evaluation and the tool itself
    still get the raw args — only what's written to the audit log changes.

    Events are hash-chained (bastion.audit_chain), so `bastion verify-audit`
    can tell if any were edited, removed or reordered.
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
        # Its own id, not session_id: callers choose session ids, and two
        # loggers sharing one would otherwise look like a broken chain.
        self.chain_id = str(uuid.uuid4())
        self._seq = 0
        self._last_hash = ""
        self._lock = threading.Lock()

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
        # Held through the sink call so events reach it in seq order, even
        # when approval waits record from several threads at once.
        with self._lock:
            event = AuditEvent(
                id=str(uuid.uuid4()),
                timestamp=time.time(),
                session_id=self.session_id,
                tool_name=tool_name,
                args=redact_value(args) if self.redact_args else args,
                action=action,
                reason=reason,
                call_id=call_id or str(uuid.uuid4()),
                approver=approver,
                chain_id=self.chain_id,
                seq=self._seq,
                prev_hash=self._last_hash,
            )
            event.hash = event_hash(asdict(event))
            # Advanced before the sink runs: if it fails, the lost event
            # shows up as a gap rather than vanishing without a trace.
            self._seq += 1
            self._last_hash = event.hash
            self.sink(event)
        return event
