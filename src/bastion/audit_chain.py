"""Hash chaining for the audit log, so edited, missing or reordered events
can be detected.

Each AuditLogger is one chain: its events carry `chain_id`, `seq` (0, 1,
2, ...), `prev_hash` (the previous event's `hash`, "" for the first) and
`hash`. A chain only proves the log is internally consistent: whoever can
rewrite the file can recompute every hash, and dropping a chain's last
events leaves a shorter valid chain. Catching that needs a copy kept
somewhere else: pass `against=` to compare with the dashboard's.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

# chain_id -> {seq: hash} for every event the dashboard holds in that chain.
ChainLookup = Callable[[str], dict[int, str]]


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
class ChainFinding:
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
    breaks: list[ChainFinding]
    # Worth knowing but not evidence of tampering, e.g. events that never
    # reached the dashboard.
    warnings: list[ChainFinding] = field(default_factory=list)


def verify_audit_log(path: str | Path, against: ChainLookup | None = None) -> ChainReport:
    """Check every chain in a JSONL audit log, in file order.

    against: look up another copy of each chain (the dashboard's) and
    compare. That catches what the file alone can't: an event rewritten
    with its hash recomputed, and events cut from the end of a chain.
    """
    tips: dict[str, tuple[int, str]] = {}
    # chain_id -> {seq: (line, hash)}, only needed to compare with `against`.
    local: dict[str, dict[int, tuple[int, str]]] = {}
    breaks: list[ChainFinding] = []
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
                breaks.append(ChainFinding(line_number, "", "not a JSON event"))
                continue
            if "hash" not in event:
                unchained += 1
                continue
            events += 1

            chain_id, seq, prev_hash = (event.get(k) for k in ("chain_id", "seq", "prev_hash"))
            if not isinstance(chain_id, str) or not isinstance(seq, int):
                breaks.append(ChainFinding(line_number, "", "missing chain_id or seq"))
                continue

            for problem in _problems(event, seq, prev_hash, tips.get(chain_id)):
                breaks.append(ChainFinding(line_number, chain_id, problem))
            # Continue from this event even if it's broken, so one tampered
            # spot is reported once rather than on every later event.
            tips[chain_id] = (seq, event["hash"])
            if against is not None:
                local.setdefault(chain_id, {})[seq] = (line_number, event["hash"])

    warnings: list[ChainFinding] = []
    if against is not None:
        for chain_id, links in local.items():
            chain_breaks, chain_warnings = _compare(chain_id, links, against(chain_id))
            breaks += chain_breaks
            warnings += chain_warnings
        breaks.sort(key=lambda b: b.line)
    return ChainReport(
        events=events, chains=len(tips), unchained=unchained, breaks=breaks, warnings=warnings
    )


def _compare(
    chain_id: str, local: dict[int, tuple[int, str]], dashboard: dict[int, str]
) -> tuple[list[ChainFinding], list[ChainFinding]]:
    """Breaks and warnings from comparing one chain with the dashboard's copy."""
    breaks: list[ChainFinding] = []
    warnings: list[ChainFinding] = []

    def line(seq: int) -> int:
        return local[seq][0]

    for seq, (_, hash_) in sorted(local.items()):
        if seq in dashboard and dashboard[seq] != hash_:
            problem = f"seq {seq} differs from the dashboard's copy: one of them was changed"
            breaks.append(ChainFinding(line(seq), chain_id, problem))

    last = max(local)
    if dashboard and max(dashboard) > last:
        problem = (
            f"the log ends at seq {last} but the dashboard has events up to seq "
            f"{max(dashboard)}: events were cut from the end"
        )
        breaks.append(ChainFinding(line(last), chain_id, problem))

    unsent = sorted(seq for seq in local if seq not in dashboard)
    if not dashboard:
        problem = "the dashboard has no events from this chain"
        warnings.append(ChainFinding(line(min(local)), chain_id, problem))
    elif unsent:
        events = f"{len(unsent)} event{'' if len(unsent) == 1 else 's'}"
        problem = f"{events} never reached the dashboard, starting at seq {unsent[0]}"
        warnings.append(ChainFinding(line(unsent[0]), chain_id, problem))
    return breaks, warnings


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
