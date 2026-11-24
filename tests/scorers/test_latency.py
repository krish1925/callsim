from callsim.schema import LatencyExpect
from callsim.scorers.latency import score_latency
from tests.scorers.conftest import B


def _trace(latencies: list[int]) -> B:
    b = B()
    for ms in latencies:
        b.caller("hi").agent("hello", latency_ms=ms)
    return b


def test_within_budget_passes() -> None:
    r = score_latency(_trace([800, 900, 1000]).build(), LatencyExpect(p95_ms=1500))
    assert r.status == "pass"


def test_slow_turn_is_warning() -> None:
    r = score_latency(_trace([800, 900, 4000]).build(), LatencyExpect(p95_ms=1500))
    assert (r.status, r.severity, r.evidence) == ("fail", "warning", ["e6"])


def test_no_samples_is_unknown() -> None:
    assert score_latency(B().build(), LatencyExpect(p95_ms=1)).status == "unknown"
