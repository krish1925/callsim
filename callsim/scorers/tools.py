from callsim.schema import ExpectedToolCall, ToolsExpect
from callsim.scorers.base import ScoreResult, Severity, unknown, worst
from callsim.trace import Event, Trace

METRIC = "tool_calls"


def score_tools(trace: Trace, expect: ToolsExpect) -> ScoreResult:
    if not trace.backend_ok:
        return unknown(METRIC, "backend logs missing")
    calls = [e for e in trace.events if e.type == "tool_call"]
    sev: Severity | None = None
    problems: list[str] = []
    evidence: list[str] = []

    for c in calls:
        if c.name in expect.forbidden:
            sev = worst(sev, "critical")
            problems.append(f"forbidden tool {c.name}")
            evidence.append(c.id)

    used: set[int] = set()
    last = -1
    for want in expect.calls:
        hit = _find(calls, want, used, last if expect.order == "in_order" else -1)
        if hit is None:
            sev = worst(sev, "major")
            problems.append(f"missing or out-of-order call {want.name}")
            continue
        used.add(hit)
        last = hit

    extras = [c for i, c in enumerate(calls) if i not in used and c.name not in expect.forbidden]
    if len(extras) > expect.max_extra_calls:
        sev = worst(sev, "major")
        problems.append(f"{len(extras)} extra calls (max {expect.max_extra_calls})")
        evidence += [c.id for c in extras]

    if sev is None:
        return ScoreResult(metric=METRIC, status="pass")
    return ScoreResult(
        metric=METRIC,
        status="fail",
        severity=sev,
        outcome="tool_call_mismatch",
        evidence=evidence,
        detail="; ".join(problems),
    )


def _find(calls: list[Event], want: ExpectedToolCall, used: set[int], after: int) -> int | None:
    for i, c in enumerate(calls):
        if i <= after or i in used or c.name != want.name:
            continue
        if all(k in c.args and m.matches(c.args[k]) for k, m in want.args.items()):
            return i
    return None
