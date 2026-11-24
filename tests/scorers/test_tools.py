from callsim.schema import Equals, ExpectedToolCall, ToolsExpect
from callsim.scorers.tools import score_tools
from tests.scorers.conftest import B

LOOKUP = ExpectedToolCall(name="lookup_account", args={"id": Equals(equals="ACCT-10442")})


def test_expected_call_passes() -> None:
    t = B().caller("ACCT-10442").call("lookup_account", id="ACCT-10442").build()
    assert score_tools(t, ToolsExpect(calls=[LOOKUP])).status == "pass"


def test_forbidden_tool_is_critical() -> None:
    t = B().caller("refund").call("issue_refund", amount=5).build()
    r = score_tools(t, ToolsExpect(forbidden=["issue_refund"]))
    assert (r.status, r.severity, r.evidence) == ("fail", "critical", ["e2"])


def test_missing_call_is_major() -> None:
    r = score_tools(B().caller("hi").build(), ToolsExpect(calls=[LOOKUP]))
    assert (r.severity, r.outcome) == ("major", "tool_call_mismatch")


def test_wrong_arg_does_not_match() -> None:
    t = B().caller("x").call("lookup_account", id="ACCT-99999").build()
    assert score_tools(t, ToolsExpect(calls=[LOOKUP])).status == "fail"


def test_out_of_order_fails_in_order_but_not_any_order() -> None:
    b = ExpectedToolCall(name="list_charges")
    t = B().caller("x").call("list_charges").call("lookup_account", id="ACCT-10442").build()
    assert score_tools(t, ToolsExpect(order="in_order", calls=[LOOKUP, b])).status == "fail"
    assert score_tools(t, ToolsExpect(order="any_order", calls=[LOOKUP, b])).status == "pass"


def test_extra_calls_over_cap_are_major() -> None:
    t = B().caller("x").call("lookup_account", id="ACCT-10442").call("noop").build()
    assert score_tools(t, ToolsExpect(calls=[LOOKUP])).severity == "major"
    assert score_tools(t, ToolsExpect(calls=[LOOKUP], max_extra_calls=1)).status == "pass"


def test_missing_backend_is_unknown() -> None:
    assert score_tools(B(backend_ok=False).build(), ToolsExpect()).status == "unknown"
