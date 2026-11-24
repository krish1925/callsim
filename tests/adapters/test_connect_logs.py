import json
from datetime import datetime
from pathlib import Path
from typing import Any

from callsim.adapters.connect_logs import estimate_skew, merge, parse_records, rows_to_records
from callsim.trace import Event

FIX = Path(__file__).parents[2] / "fixtures" / "connect"
T0 = int(datetime.fromisoformat("2026-11-23T10:00:00Z").timestamp() * 1000)


def _records() -> list[dict[str, Any]]:
    return [
        r
        for r in json.loads((FIX / "records_billing_escalation.json").read_text())
        if isinstance(r, dict)
    ]


def _caller(i: int, turn: int, ms: int) -> Event:
    return Event(id=f"e{i}", type="caller_msg", turn=turn, ts=T0 + ms, text="x")


def test_parse_maps_all_event_types_sorted() -> None:
    ev = parse_records(_records())
    assert [e.type for e in ev] == ["intent_detected", "tool_call", "tool_result", "transfer"]
    assert ev[1].args == {"id": "ACCT-10442"}
    assert ev[3].queue == "BillingQueue" and ev[3].attributes["reason"] == "billing dispute CH-77"
    assert all(e.source == "backend" for e in ev)


def test_rows_to_records_skips_non_json() -> None:
    rows = [[{"field": "@message", "value": '{"a": 1}'}], [{"field": "@message", "value": "plain"}]]
    assert rows_to_records(rows) == [{"a": 1}]


def test_merge_assigns_turns_and_ids_after_live() -> None:
    live = [_caller(1, 1, 1000), _caller(2, 2, 6000)]
    t = merge(live, parse_records(_records()))
    by_type = {e.type: e for e in t.events if e.source == "backend"}
    assert by_type["tool_call"].turn == 1  # 4.2s, after turn-1 send at 1s, before turn 2 at 6s
    assert by_type["transfer"].turn == 2
    assert by_type["tool_call"].id == "e4" and by_type["transfer"].id == "e6"
    assert by_type["transfer"].raw is not None and "ts_backend" in by_type["transfer"].raw
    assert [e.ts for e in t.events] == sorted(e.ts for e in t.events)


def test_backward_skew_is_corrected_forward_gap_is_not() -> None:
    backend = parse_records(_records())
    ahead = [_caller(1, 1, 5000)]  # caller send recorded 5s later than the first backend event
    assert estimate_skew(ahead, backend) > 0
    prompt = [_caller(1, 1, 500)]  # normal: backend events come after the send
    assert estimate_skew(prompt, backend) == 0


def test_backend_before_first_send_gets_turn_zero_without_skew() -> None:
    assert merge([], parse_records(_records())).events[0].turn == 0
