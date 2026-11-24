from callsim.scorers.grounding import score_grounding
from tests.scorers.conftest import B


def test_arg_said_by_caller_is_grounded() -> None:
    t = B().caller("my account is acct-10442").call("lookup_account", id="ACCT-10442").build()
    assert score_grounding(t).status == "pass"


def test_made_up_arg_is_critical() -> None:
    t = B().caller("my account is ACCT-10442").call("lookup_account", id="ACCT-99999").build()
    r = score_grounding(t)
    assert (r.status, r.severity, r.evidence) == ("fail", "critical", ["e2"])


def test_arg_from_earlier_tool_result_is_grounded() -> None:
    t = (
        B()
        .caller("ACCT-10442")
        .call("lookup_account", id="ACCT-10442")
        .result("lookup_account", {"charge_id": "CH-77"})
        .call("issue_refund", charge_id="CH-77")
        .build()
    )
    assert score_grounding(t).status == "pass"


def test_money_formats_normalise() -> None:
    t = B().caller("refund me $49.99").call("issue_refund", amount=49.99).build()
    assert score_grounding(t).status == "pass"


def test_arg_before_it_was_said_is_ungrounded() -> None:
    t = B().call("lookup_account", id="ACCT-10442").caller("ACCT-10442").build()
    assert score_grounding(t).status == "fail"


def test_exempt_arg_is_skipped() -> None:
    t = B().caller("hi").call("lookup_account", mode="full").build()
    assert score_grounding(t, exempt=["mode"]).status == "pass"
