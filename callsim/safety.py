"""Scenario linting: synthetic data only, and expected values must be traceable."""

import re

from callsim.schema import Equals, Scenario

_EMAIL = re.compile(r"[\w.+-]+@([\w-]+\.[\w.]+)")
_PHONE = re.compile(r"\(?\b\d{3}\)?[-. ]?\d{3}[-. ]?\d{4}\b")
_CARD = re.compile(r"\b\d(?:[ -]?\d){12,18}\b")
_SAFE_DOMAINS = {"example.test", "example.com"}


def _luhn(digits: str) -> bool:
    total = 0
    for i, ch in enumerate(reversed(digits)):
        d = int(ch)
        if i % 2:
            d = d * 2 - 9 if d * 2 > 9 else d * 2
        total += d
    return total % 10 == 0


def lint_scenario(sc: Scenario) -> list[str]:
    """Problems found; empty means clean."""
    problems: list[str] = []
    texts = [sc.goal, *sc.behaviors, *sc.persona.never, *map(str, sc.known_facts.values())]
    for t in texts:
        for m in _EMAIL.finditer(t):
            if m.group(1).lower() not in _SAFE_DOMAINS:
                problems.append(f"real-looking email domain: {m.group(0)}")
        for m in _PHONE.finditer(t):
            digits = re.sub(r"\D", "", m.group(0))
            if digits[3:6] != "555" or digits[6:8] != "01":
                problems.append(f"phone is not 555-01xx: {m.group(0)}")
        for m in _CARD.finditer(t):
            digits = re.sub(r"\D", "", m.group(0))
            if _luhn(digits):
                problems.append(f"Luhn-valid card-like number: {m.group(0)}")
    facts = " ".join(str(v).lower() for v in sc.known_facts.values())
    for call in sc.expected.tools.calls:
        for arg, matcher in call.args.items():
            if isinstance(matcher, Equals) and str(matcher.equals).lower() not in facts:
                problems.append(
                    f"expected {call.name}.{arg}={matcher.equals!r} is not in known_facts"
                )
    return problems
