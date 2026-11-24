"""Turn CloudWatch records for one ContactId into backend trace events and merge them.

Pure functions only: the Logs Insights query lives in the Connect adapter, so this
module is testable from fixtures with no AWS access.

ASSUMED RECORD SHAPES (verify against real logs during the console setup step):
  flow log   {"ContactId", "Timestamp", "ContactFlowModuleType", "Parameters": {...}, "Results": ...}
  lambda log {"callsim": "tool_call"|"tool_result"|"intent", "contact_id", "ts", ...}
The Lambda lines are ours (we write the Lambda), so that shape is controlled. The flow-log
shape is from memory of the Connect docs and may need adjusting.
"""

import json
import statistics
from datetime import datetime
from typing import Any

from callsim.trace import Event, Trace

TRANSFER_BLOCKS = {"TransferContactToQueue", "Transfer"}


def rows_to_records(rows: list[list[dict[str, str]]]) -> list[dict[str, Any]]:
    """GetQueryResults rows -> parsed JSON from each @message. Non-JSON lines are skipped."""
    out: list[dict[str, Any]] = []
    for row in rows:
        msg = next((c["value"] for c in row if c.get("field") == "@message"), None)
        if msg is None:
            continue
        try:
            rec = json.loads(msg)
        except json.JSONDecodeError:
            continue
        if isinstance(rec, dict):
            out.append(rec)
    return out


def _ms(ts: str | float) -> int:
    if isinstance(ts, int | float):
        return int(ts)
    return int(datetime.fromisoformat(ts).timestamp() * 1000)


def parse_records(records: list[dict[str, Any]]) -> list[Event]:
    """Backend events with turn=0 and temporary ids; merge() assigns both."""
    events: list[Event] = []

    def add(type_: str, ts: int, **kw: Any) -> None:
        events.append(Event(id="", type=type_, turn=0, ts=ts, source="backend", **kw))

    for rec in records:
        kind = rec.get("callsim")
        if kind == "tool_call":
            add("tool_call", _ms(rec["ts"]), name=rec["name"], args=rec.get("args", {}), raw=rec)
        elif kind == "tool_result":
            add("tool_result", _ms(rec["ts"]), name=rec["name"], result=rec.get("result"), raw=rec)
        elif kind == "intent":
            add("intent_detected", _ms(rec["ts"]), name=rec["intent"], raw=rec)
        elif rec.get("ContactFlowModuleType") in TRANSFER_BLOCKS:
            params = rec.get("Parameters", {})
            attrs = {str(k): str(v) for k, v in params.get("Attributes", {}).items()}
            queue = params.get("Queue") or params.get("QueueName")
            add("transfer", _ms(rec["Timestamp"]), queue=queue, attributes=attrs, raw=rec)
    return sorted(events, key=lambda e: e.ts)


def estimate_skew(live: list[Event], backend: list[Event]) -> int:
    """Backward clock skew in ms. Backend events can't precede the caller message that
    triggered them, so a negative gap means the clocks disagree. Forward gaps are real
    latency and are never subtracted."""
    sends = [e.ts for e in live if e.type == "caller_msg"]
    if not sends or not backend:
        return 0
    gaps = [b.ts - max((s for s in sends if s <= b.ts), default=sends[0]) for b in backend]
    return -min(0, int(statistics.median(gaps)))


def merge(live: list[Event], backend: list[Event], *, backend_ok: bool = True) -> Trace:
    """Assign each backend event to the turn of the latest caller_msg at or before its
    skew-corrected time, then append with ids numbered after the live ones (D3)."""
    skew = estimate_skew(live, backend)
    sends = sorted((e.ts, e.turn) for e in live if e.type == "caller_msg")
    merged = list(live)
    n = len(live)
    for b in backend:
        corrected = b.ts + skew
        turn = max((t for ts, t in sends if ts <= corrected), default=0)
        n += 1
        merged.append(
            b.model_copy(
                update={"id": f"e{n}", "turn": turn, "ts": corrected, "raw": _with_orig(b)}
            )
        )
    merged.sort(key=lambda e: (e.ts, int(e.id[1:])))
    return Trace(events=merged, backend_ok=backend_ok)


def _with_orig(e: Event) -> dict[str, Any]:
    return {**(e.raw or {}), "ts_backend": e.ts}
