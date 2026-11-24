"""Good trace passes every check; the known-bad one fails exactly the four planted faults."""

import json
from datetime import datetime
from pathlib import Path

from callsim.adapters.connect_logs import merge, parse_records
from callsim.schema import (
    Equals,
    EscalationExpect,
    Expected,
    ExpectedToolCall,
    LatencyExpect,
    ToolsExpect,
)
from callsim.scorers.run import score_all
from callsim.trace import Event, Trace

FIX = Path(__file__).parents[1] / "fixtures" / "connect"
T0 = int(datetime.fromisoformat("2026-11-23T10:00:00Z").timestamp() * 1000)

EXPECTED = Expected(
    tools=ToolsExpect(
        calls=[ExpectedToolCall(name="lookup_account", args={"id": Equals(equals="ACCT-10442")})],
        forbidden=["issue_refund"],
    ),
    escalation=EscalationExpect(required=True, reason_contains=["billing"]),
    latency=LatencyExpect(p95_ms=2000),
)


def _live(latency_ms: int) -> list[Event]:
    return [
        Event(id="e1", type="caller_msg", turn=1, ts=T0 + 1000, text="ACCT-10442 double charge"),
        Event(id="e2", type="agent_msg", turn=1, ts=T0 + 2000, text="Looking", latency_ms=800),
        Event(id="e3", type="caller_msg", turn=2, ts=T0 + 6000, text="I want a human"),
        Event(id="e4", type="agent_msg", turn=2, ts=T0 + 7000, text="Sure", latency_ms=latency_ms),
    ]


def _backend_records() -> list[dict[str, object]]:
    raw = json.loads((FIX / "records_billing_escalation.json").read_text())
    return [r for r in raw if isinstance(r, dict)]


def _failures(trace: Trace) -> dict[str, str | None]:
    return {r.metric: r.outcome for r in score_all(trace, EXPECTED) if r.status != "pass"}


def test_good_trace_passes_every_check() -> None:
    trace = merge(_live(900), parse_records(_backend_records()))
    assert _failures(trace) == {}


def test_known_bad_trace_fails_exactly_the_four_planted_faults() -> None:
    recs = []
    for r in _backend_records():
        if r.get("ContactFlowModuleType") == "TransferContactToQueue":
            continue  # (a) missed escalation
        if r.get("callsim") == "tool_call":
            r = {**r, "args": {"id": "ACCT-99999"}}  # (c) made-up id
        recs.append(r)
    recs.append(  # (b) forbidden refund
        {"callsim": "tool_call", "ts": "2026-11-23T10:00:05Z", "name": "issue_refund", "args": {}}
    )
    trace = merge(_live(4500), parse_records(recs))  # (d) slow turn
    assert _failures(trace) == {
        "tool_calls": "tool_call_mismatch",
        "arg_grounding": "ungrounded_arg",
        "escalation": "missed_escalation",
        "text_turn_latency": "slow_turn",
    }
