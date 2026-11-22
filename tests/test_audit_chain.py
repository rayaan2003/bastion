import json
import threading
from pathlib import Path

from bastion.audit import AuditLogger
from bastion.audit_chain import ChainReport, event_hash, verify_audit_log


def _write(path: Path, n: int, **kwargs) -> AuditLogger:
    audit = AuditLogger(log_path=str(path), **kwargs)
    for i in range(n):
        audit.record("send_email", {"to": f"user{i}", "n": i}, "allowed", "ok")
    return audit


def _lines(path: Path) -> list[str]:
    return path.read_text().splitlines()


def _rewrite(path: Path, lines: list[str]) -> None:
    path.write_text("".join(line + "\n" for line in lines))


def _problems(report: ChainReport) -> list[tuple[int, str]]:
    return [(b.line, b.problem) for b in report.breaks]


def test_events_are_linked_in_order(tmp_path):
    log = tmp_path / "audit.jsonl"
    _write(log, 3)
    events = [json.loads(line) for line in _lines(log)]

    assert [e["seq"] for e in events] == [0, 1, 2]
    assert events[0]["prev_hash"] == ""
    assert [e["prev_hash"] for e in events[1:]] == [e["hash"] for e in events[:-1]]
    assert len({e["chain_id"] for e in events}) == 1


def test_untouched_log_verifies(tmp_path):
    log = tmp_path / "audit.jsonl"
    _write(log, 5)
    assert verify_audit_log(log) == ChainReport(events=5, chains=1, unchained=0, breaks=[])


def test_edited_event_is_reported_once(tmp_path):
    log = tmp_path / "audit.jsonl"
    _write(log, 4)
    lines = _lines(log)
    lines[1] = lines[1].replace('"allowed"', '"blocked"')
    _rewrite(log, lines)

    assert _problems(verify_audit_log(log)) == [
        (2, "seq 1 was edited: its contents don't match its hash")
    ]


def test_edit_with_recomputed_hash_breaks_the_next_link(tmp_path):
    log = tmp_path / "audit.jsonl"
    _write(log, 3)
    lines = _lines(log)
    forged = json.loads(lines[1]) | {"action": "blocked"}
    forged["hash"] = event_hash(forged)
    lines[1] = json.dumps(forged)
    _rewrite(log, lines)

    assert _problems(verify_audit_log(log)) == [
        (3, "seq 2 doesn't link to seq 1: one of them was replaced")
    ]


def test_removed_events_are_reported_as_a_gap(tmp_path):
    log = tmp_path / "audit.jsonl"
    _write(log, 5)
    lines = _lines(log)
    _rewrite(log, lines[:1] + lines[3:])

    assert _problems(verify_audit_log(log)) == [(2, "events 1-2 are missing before seq 3")]


def test_removed_first_event_is_reported(tmp_path):
    log = tmp_path / "audit.jsonl"
    _write(log, 3)
    _rewrite(log, _lines(log)[1:])

    assert _problems(verify_audit_log(log)) == [(1, "event 0 is missing before seq 1")]


def test_swapped_events_are_reported(tmp_path):
    log = tmp_path / "audit.jsonl"
    _write(log, 3)
    a, b, c = _lines(log)
    _rewrite(log, [a, c, b])

    assert _problems(verify_audit_log(log)) == [
        (2, "event 1 is missing before seq 2"),
        (3, "seq 1 is out of order or repeated (expected 3)"),
    ]


def test_loggers_sharing_a_session_id_and_file_are_separate_chains(tmp_path):
    log = tmp_path / "audit.jsonl"
    first = AuditLogger(log_path=str(log), session_id="run-42")
    second = AuditLogger(log_path=str(log), session_id="run-42")
    for _ in range(3):
        first.record("a", {}, "allowed", "")
        second.record("b", {}, "allowed", "")

    assert verify_audit_log(log) == ChainReport(events=6, chains=2, unchained=0, breaks=[])


def test_concurrent_records_stay_in_seq_order(tmp_path):
    log = tmp_path / "audit.jsonl"
    audit = AuditLogger(log_path=str(log))

    def record_many() -> None:
        for _ in range(50):
            audit.record("t", {}, "allowed", "")

    threads = [threading.Thread(target=record_many) for _ in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert verify_audit_log(log).breaks == []


def test_args_that_json_changes_still_verify(tmp_path):
    log = tmp_path / "audit.jsonl"
    audit = AuditLogger(log_path=str(log), redact_args=False)
    audit.record("t", {"obj": object(), "pair": (1, 2), "by_id": {1: "x"}}, "allowed", "")

    assert verify_audit_log(log).breaks == []


def test_unchained_events_are_counted_not_reported(tmp_path):
    log = tmp_path / "audit.jsonl"
    legacy = {"id": "1", "session_id": "s", "tool_name": "t", "action": "allowed"}
    log.write_text(json.dumps(legacy) + "\n")
    _write(log, 2)

    assert verify_audit_log(log) == ChainReport(events=2, chains=1, unchained=1, breaks=[])


def test_stripping_an_events_hash_leaves_a_gap(tmp_path):
    log = tmp_path / "audit.jsonl"
    _write(log, 3)
    lines = _lines(log)
    stripped = json.loads(lines[1])
    del stripped["hash"]
    lines[1] = json.dumps(stripped)
    _rewrite(log, lines)

    report = verify_audit_log(log)
    assert report.unchained == 1
    assert _problems(report) == [(3, "event 1 is missing before seq 2")]


def test_lines_that_arent_events_are_reported(tmp_path):
    log = tmp_path / "audit.jsonl"
    _write(log, 1)
    log.write_text(log.read_text() + "not json\n[1, 2]\n\n")

    assert _problems(verify_audit_log(log)) == [
        (2, "not a JSON event"),
        (3, "not a JSON event"),
    ]


def _copy(path: Path) -> dict[str, dict[int, str]]:
    """What the dashboard would hold had it received every event in `path`."""
    chains: dict[str, dict[int, str]] = {}
    for line in _lines(path):
        event = json.loads(line)
        chains.setdefault(event["chain_id"], {})[event["seq"]] = event["hash"]
    return chains


def _against(copy: dict[str, dict[int, str]]):
    return lambda chain_id: copy.get(chain_id, {})


def test_log_matching_the_dashboard_verifies(tmp_path):
    log = tmp_path / "audit.jsonl"
    _write(log, 3)
    report = verify_audit_log(log, _against(_copy(log)))
    assert (report.breaks, report.warnings) == ([], [])


def test_rewritten_chain_passes_alone_but_not_against_the_dashboard(tmp_path):
    log = tmp_path / "audit.jsonl"
    _write(log, 3)
    dashboard = _copy(log)
    # Forge seq 1 and relink seq 2 after it, so the file is self-consistent.
    events = [json.loads(line) for line in _lines(log)]
    events[1]["action"] = "blocked"
    events[1]["hash"] = event_hash(events[1])
    events[2]["prev_hash"] = events[1]["hash"]
    events[2]["hash"] = event_hash(events[2])
    _rewrite(log, [json.dumps(e) for e in events])

    assert verify_audit_log(log).breaks == []
    assert _problems(verify_audit_log(log, _against(dashboard))) == [
        (2, "seq 1 differs from the dashboard's copy: one of them was changed"),
        (3, "seq 2 differs from the dashboard's copy: one of them was changed"),
    ]


def test_cut_off_end_passes_alone_but_not_against_the_dashboard(tmp_path):
    log = tmp_path / "audit.jsonl"
    _write(log, 5)
    dashboard = _copy(log)
    _rewrite(log, _lines(log)[:3])

    assert verify_audit_log(log).breaks == []
    assert _problems(verify_audit_log(log, _against(dashboard))) == [
        (3, "the log ends at seq 2 but the dashboard has events up to seq 4: "
            "events were cut from the end")
    ]


def test_events_the_dashboard_never_got_are_a_warning(tmp_path):
    log = tmp_path / "audit.jsonl"
    audit = _write(log, 5)
    dashboard = _copy(log)
    for seq in (2, 3):
        del dashboard[audit.chain_id][seq]

    report = verify_audit_log(log, _against(dashboard))
    assert report.breaks == []
    assert [(w.line, w.problem) for w in report.warnings] == [
        (3, "2 events never reached the dashboard, starting at seq 2")
    ]


def test_chain_the_dashboard_never_saw_is_a_warning(tmp_path):
    log = tmp_path / "audit.jsonl"
    _write(log, 2)

    report = verify_audit_log(log, _against({}))
    assert report.breaks == []
    assert [(w.line, w.problem) for w in report.warnings] == [
        (1, "the dashboard has no events from this chain")
    ]
