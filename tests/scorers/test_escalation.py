from callsim.schema import EscalationExpect
from callsim.scorers.escalation import score_escalation
from tests.scorers.conftest import B


def test_clean_escalation_passes() -> None:
    t = (
        B()
        .caller("I want a human")
        .agent("Transferring")
        .transfer(reason="billing dispute")
        .build()
    )
    r = score_escalation(t, EscalationExpect(required=True, reason_contains=["billing"]))
    assert r.status == "pass"


def test_missed_escalation_is_critical() -> None:
    t = B().caller("human please").agent("I can help").caller("a human").agent("Sorry").build()
    r = score_escalation(t, EscalationExpect(required=True))
    assert (r.status, r.severity, r.outcome) == ("fail", "critical", "missed_escalation")


def test_late_escalation_is_missed() -> None:
    b = B().caller("human").agent("no").caller("human").agent("no").caller("human")
    t = b.transfer(reason="x").build()
    r = score_escalation(t, EscalationExpect(required=True, by_turn=2))
    assert r.outcome == "missed_escalation"


def test_unnecessary_escalation_is_major() -> None:
    t = B().caller("what's my balance").transfer(reason="x").build()
    r = score_escalation(t, EscalationExpect(required=False))
    assert (r.severity, r.outcome) == ("major", "unnecessary_escalation")


def test_transfer_without_context_is_major() -> None:
    t = B().caller("human").transfer(reason="").build()
    r = score_escalation(t, EscalationExpect(required=True, reason_contains=["refund"]))
    assert (r.severity, r.outcome) == ("major", "transfer_without_context")


def test_missing_backend_is_unknown_not_fail() -> None:
    t = B(backend_ok=False).caller("human").build()
    assert score_escalation(t, EscalationExpect(required=True)).status == "unknown"
