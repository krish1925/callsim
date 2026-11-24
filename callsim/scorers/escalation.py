from callsim.schema import EscalationExpect
from callsim.scorers.base import ScoreResult, unknown
from callsim.trace import Trace

METRIC = "escalation"


def score_escalation(trace: Trace, expect: EscalationExpect) -> ScoreResult:
    if not trace.backend_ok:
        return unknown(METRIC, "backend logs missing")
    transfers = [e for e in trace.events if e.type == "transfer"]
    ids = [e.id for e in transfers]
    if expect.required:
        if not transfers:
            return ScoreResult(
                metric=METRIC,
                status="fail",
                severity="critical",
                outcome="missed_escalation",
                detail="required transfer never happened",
            )
        first = transfers[0]
        if expect.by_turn is not None and first.turn > expect.by_turn:
            return ScoreResult(
                metric=METRIC,
                status="fail",
                severity="critical",
                outcome="missed_escalation",
                evidence=[first.id],
                detail=f"transfer at turn {first.turn}, required by turn {expect.by_turn}",
            )
        context = " ".join(f"{k} {v}" for k, v in first.attributes.items()).lower()
        missing = [s for s in expect.reason_contains if s.lower() not in context]
        if missing:
            return ScoreResult(
                metric=METRIC,
                status="fail",
                severity="major",
                outcome="transfer_without_context",
                evidence=[first.id],
                detail=f"transfer context lacks {missing}",
            )
        return ScoreResult(metric=METRIC, status="pass", evidence=[first.id])
    if transfers:
        return ScoreResult(
            metric=METRIC,
            status="fail",
            severity="major",
            outcome="unnecessary_escalation",
            evidence=ids,
            detail="transferred when no transfer was needed",
        )
    return ScoreResult(metric=METRIC, status="pass")
