from pathlib import Path

from callsim.safety import lint_scenario
from callsim.schema import Scenario, load_scenario

BASE = load_scenario(Path(__file__).parents[1] / "scenarios" / "happy_balance.toml")


def _with(**changes: object) -> Scenario:
    return BASE.model_copy(update=changes)


def test_clean_scenario_has_no_problems() -> None:
    assert lint_scenario(BASE) == []


def test_real_email_domain_is_flagged() -> None:
    sc = _with(known_facts={"account_id": "ACCT-10442", "email": "a@gmail.com"})
    assert any("email" in p for p in lint_scenario(sc))


def test_safe_email_and_555_phone_are_allowed() -> None:
    sc = _with(known_facts={"account_id": "ACCT-10442", "e": "a@example.test", "p": "415-555-0142"})
    assert lint_scenario(sc) == []


def test_real_looking_phone_is_flagged() -> None:
    sc = _with(known_facts={"account_id": "ACCT-10442", "p": "415-867-5309"})
    assert any("phone" in p for p in lint_scenario(sc))


def test_luhn_valid_card_is_flagged_and_invalid_is_not() -> None:
    bad = _with(known_facts={"account_id": "ACCT-10442", "c": "4111 1111 1111 1111"})
    ok = _with(known_facts={"account_id": "ACCT-10442", "c": "4111 1111 1111 1112"})
    assert any("card" in p for p in lint_scenario(bad))
    assert lint_scenario(ok) == []


def test_expected_arg_not_in_known_facts_is_flagged() -> None:
    sc = _with(known_facts={"account_id": "ACCT-00000"})
    assert any("not in known_facts" in p for p in lint_scenario(sc))
