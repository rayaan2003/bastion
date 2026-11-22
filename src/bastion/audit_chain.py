"""Hash chaining for the audit log, so edited, missing or reordered events
can be detected.

Each AuditLogger is one chain: its events carry `chain_id`, `seq` (0, 1,
2, ...), `prev_hash` (the previous event's `hash`, "" for the first) and
`hash`. A chain only proves the log is internally consistent: whoever can
rewrite the file can recompute every hash, and dropping a chain's last
events leaves a shorter valid chain. Catching that needs a copy of the
latest hashes kept somewhere else.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any


def event_hash(fields: dict[str, Any]) -> str:
    """SHA-256 of an event's fields, excluding `hash` itself."""
    content = {k: v for k, v in fields.items() if k != "hash"}
    # Round-trip first so the hash is of what a JSONL sink writes, and can be
    # recomputed from the file: non-JSON values become their str(), tuples
    # lists, and non-string keys strings (which sort_keys can't compare).
    normalized = json.loads(json.dumps(content, default=str))
    canonical = json.dumps(normalized, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class ChainBreak:
    line: int
    chain_id: str
    problem: str


@dataclass(frozen=True)
class ChainReport:
    events: int
    chains: int
    # Events with no hash: written before bastion chained events, or stripped.
    # A stripped event still shows up as a gap in its chain.
    unchained: int
    breaks: list[ChainBreak]


def verify_audit_log(path: str | Path) -> ChainReport:
    """Check every chain in a JSONL audit log, in file order."""
    tips: dict[str, tuple[int, str]] = {}
    breaks: list[ChainBreak] = []
    events = unchained = 0

    with Path(path).open(encoding="utf-8") as f:
        for line_number, line in enumerate(f, start=1):
            if not line.strip():
                continue
            try:
                event = json.loads(line)
            except json.JSONDecodeError:
                event = None
            if not isinstance(event, dict):
                breaks.append(ChainBreak(line_number, "", "not a JSON event"))
                continue
            if "hash" not in event:
                unchained += 1
                continue
            events += 1

            chain_id, seq, prev_hash = (event.get(k) for k in ("chain_id", "seq", "prev_hash"))
            if not isinstance(chain_id, str) or not isinstance(seq, int):
                breaks.append(ChainBreak(line_number, "", "missing chain_id or seq"))
                continue

            for problem in _problems(event, seq, prev_hash, tips.get(chain_id)):
                breaks.append(ChainBreak(line_number, chain_id, problem))
            # Continue from this event even if it's broken, so one tampered
            # spot is reported once rather than on every later event.
            tips[chain_id] = (seq, event["hash"])

    return ChainReport(events=events, chains=len(tips), unchained=unchained, breaks=breaks)


def _problems(
    event: dict[str, Any], seq: int, prev_hash: Any, tip: tuple[int, str] | None
) -> list[str]:
    """What's wrong with `event`, given the last event seen in its chain."""
    problems = []
    if event_hash(event) != event["hash"]:
        problems.append(f"seq {seq} was edited: its contents don't match its hash")

    expected_seq, expected_prev = (tip[0] + 1, tip[1]) if tip else (0, "")
    if seq == expected_seq + 1:
        problems.append(f"event {expected_seq} is missing before seq {seq}")
    elif seq > expected_seq:
        problems.append(f"events {expected_seq}-{seq - 1} are missing before seq {seq}")
    elif seq < expected_seq:
        problems.append(f"seq {seq} is out of order or repeated (expected {expected_seq})")
    elif prev_hash != expected_prev and seq == 0:
        problems.append("seq 0 has a prev_hash, but it should start its chain")
    elif prev_hash != expected_prev:
        problems.append(f"seq {seq} doesn't link to seq {seq - 1}: one of them was replaced")
    return problems
