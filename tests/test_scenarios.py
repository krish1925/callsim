"""The suite validates itself: every scenario loads and lints clean, and coverage is enforced."""

from collections import Counter
from pathlib import Path

import pytest

from callsim.safety import lint_scenario
from callsim.schema import Scenario, load_scenario

DIR = Path(__file__).parents[1] / "scenarios"
FILES = sorted(DIR.glob("*.toml"))
SCENARIOS = [load_scenario(p) for p in FILES]

# Minimum scenarios per category: the shape of the suite is part of the spec.
MIN_PER_CATEGORY = {
    "happy": 4,
    "escalation_required": 4,
    "escalation_forbidden": 3,
    "mind_changer": 3,
    "auth_failure": 2,
    "off_topic": 2,
}


def test_suite_size() -> None:
    assert 15 <= len(SCENARIOS) <= 20


def test_ids_unique_and_match_filenames() -> None:
    assert [s.id for s in SCENARIOS] == [p.stem for p in FILES]
    assert len({s.id for s in SCENARIOS}) == len(SCENARIOS)


@pytest.mark.parametrize("sc", SCENARIOS, ids=lambda s: s.id)
def test_scenario_lints_clean(sc: Scenario) -> None:
    assert lint_scenario(sc) == []


def test_category_minimums() -> None:
    counts = Counter(s.category for s in SCENARIOS)
    for cat, minimum in MIN_PER_CATEGORY.items():
        assert counts[cat] >= minimum, f"{cat}: {counts[cat]} < {minimum}"


def test_every_check_is_exercised_both_ways() -> None:
    """Each check needs scenarios that can fail it and scenarios that must not trigger it."""
    esc_req = [s for s in SCENARIOS if s.expected.escalation and s.expected.escalation.required]
    esc_no = [s for s in SCENARIOS if s.expected.escalation and not s.expected.escalation.required]
    forbids = [s for s in SCENARIOS if s.expected.tools.forbidden]
    expects_calls = [s for s in SCENARIOS if s.expected.tools.calls]
    no_tools = [s for s in SCENARIOS if not s.expected.tools.calls]
    assert len(esc_req) >= 5 and len(esc_no) >= 8  # missed vs unnecessary escalation
    assert len(forbids) >= 12  # forbidden-tool check has real work to do
    assert len(expects_calls) >= 10  # tool-call correctness and arg grounding
    assert len(no_tools) >= 4  # extra/unneeded tool calls are punished somewhere


def test_escalation_required_scenarios_set_a_deadline() -> None:
    for s in SCENARIOS:
        if s.expected.escalation and s.expected.escalation.required:
            assert s.expected.escalation.by_turn is not None, s.id


def test_refund_policy_is_consistent() -> None:
    """Refunds up to $25 are automated; anything larger must escalate, never self-refund."""
    for s in SCENARIOS:
        amount = s.known_facts.get("amount")
        if isinstance(amount, int | float) and amount > 25:
            assert "issue_refund" in s.expected.tools.forbidden, s.id
