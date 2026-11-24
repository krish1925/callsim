"""Text-mode turn latency only. This is not voice latency."""

import math

from callsim.schema import LatencyExpect
from callsim.scorers.base import ScoreResult
from callsim.trace import Trace

METRIC = "text_turn_latency"


def _pct(values: list[int], p: float) -> int:
    ordered = sorted(values)
    return ordered[max(0, math.ceil(p / 100 * len(ordered)) - 1)]


def score_latency(trace: Trace, expect: LatencyExpect) -> ScoreResult:
    turns = [e for e in trace.events if e.type == "agent_msg" and e.latency_ms is not None]
    values = [e.latency_ms for e in turns if e.latency_ms is not None]
    if not values:
        return ScoreResult(metric=METRIC, status="unknown", detail="no latency samples")
    p95 = _pct(values, 95)
    if p95 <= expect.p95_ms:
        return ScoreResult(metric=METRIC, status="pass", detail=f"p95={p95}ms")
    slow = [e.id for e in turns if (e.latency_ms or 0) > expect.p95_ms]
    return ScoreResult(
        metric=METRIC,
        status="fail",
        severity="warning",
        outcome="slow_turn",
        evidence=slow,
        detail=f"p95={p95}ms > {expect.p95_ms}ms",
    )
