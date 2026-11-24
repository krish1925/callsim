from callsim.caller import invented_facts, role_break

FACTS: dict[str, str | int | float] = {"account_id": "ACCT-10442", "amount": 240.0}


def test_known_facts_pass() -> None:
    assert invented_facts("My account is acct-10442 and I was charged $240.00", FACTS) == []


def test_invented_id_and_amount_are_caught() -> None:
    bad = invented_facts("account ACCT-99999, charged $19.99", FACTS)
    assert "ACCT-99999" in bad and "$19.99" in bad


def test_invented_digit_run_is_caught() -> None:
    assert invented_facts("my pin is 482913", FACTS) == ["482913"]


def test_real_model_role_break_is_detected() -> None:
    """Verbatim from MiMo when asked to play the caller (2026-11-23)."""
    msg = "Hi! I'm sorry you've been double charged $49.99. I'll help you investigate this right away."
    assert role_break(msg)


def test_normal_caller_text_is_not_a_role_break() -> None:
    assert not role_break("Hi, I was charged twice and I want it fixed.")
    assert not role_break("Can you tell me how I can pay by card?")
