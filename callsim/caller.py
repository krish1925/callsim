"""Simulated caller. The LLM writes the words; deterministic guards check them.

A small local model drifts: it invents identifiers and, as seen in testing, sometimes
answers as the support agent instead of the caller. Both are caught here so a bad caller
turn is thrown away and counted, never blamed on the agent under test.
"""

import math
import re

from pydantic import BaseModel

from callsim.llm import LLM
from callsim.schema import Scenario


class CallerTurn(BaseModel):
    message: str
    end_call: bool = False
    goal_met: bool = False


_ID = re.compile(r"\b(?:ACCT|CH)-\d+\b", re.IGNORECASE)
_MONEY = re.compile(r"\$\s?\d[\d,]*(?:\.\d+)?")
_DIGITS = re.compile(r"\b\d{4,}\b")
_EMAIL = re.compile(r"[\w.+-]+@[\w-]+\.[\w.]+")

# Phrases a caller doesn't say. Seen from the real model: "I'll help you investigate this".
_AGENT_SPEAK = [
    re.compile(p, re.IGNORECASE)
    for p in (
        r"\bhow (can|may) i (help|assist)\b",
        r"\bi('| wi)ll (help|assist|look into|investigate|process|check)\b",
        r"\bi('m| am) sorry (you|that you)'?ve? been\b",
        r"\bthank you for (calling|contacting)\b",
        r"\bis there anything else i can\b",
    )
]


def _norm(s: str) -> str:
    return re.sub(r"[\s$,]", "", s.lower())


def invented_facts(message: str, known_facts: dict[str, str | int | float]) -> list[str]:
    """Identifier-like tokens in the message that are not in the scenario's known facts."""
    allowed = " ".join(_norm(str(v)) for v in known_facts.values())
    amounts = [float(v) for v in known_facts.values() if isinstance(v, int | float)]
    bad = [
        m.group(0)
        for rx in (_ID, _DIGITS, _EMAIL)
        for m in rx.finditer(message)
        if _norm(m.group(0)) not in allowed
    ]
    for m in _MONEY.finditer(message):  # compare money numerically: $240.00 == 240.0
        value = float(re.sub(r"[$,\s]", "", m.group(0)))
        if not any(math.isclose(value, a) for a in amounts):
            bad.append(m.group(0))
    return bad


def role_break(message: str) -> bool:
    return any(rx.search(message) for rx in _AGENT_SPEAK)


def system_prompt(sc: Scenario, seed: int) -> str:
    facts = "\n".join(f"- {k}: {v}" for k, v in sc.known_facts.items())
    behaviors = "\n".join(f"- {b}" for b in sc.behaviors) or "- none"
    never = "\n".join(f"- {n}" for n in sc.persona.never) or "- none"
    return (
        "You are a CUSTOMER contacting a company's support chat. You are NOT the support agent: "
        "never offer help, never apologise on the company's behalf, never say you will look into "
        "anything. Write one short chat message per turn, like a real customer.\n"
        f"Style: {sc.persona.style}. Patience: {sc.persona.patience}. Variation seed: {seed}.\n"
        f"Your goal: {sc.goal}\n"
        f"Facts you know (use ONLY these; if asked for something else, say you don't have it):\n"
        f"{facts}\nBehaviors:\n{behaviors}\nYou never:\n{never}\n"
        "Set end_call true only when your goal is met or you give up. "
        "Set goal_met true only if the agent actually did what you wanted."
    )


class Caller:
    def __init__(self, scenario: Scenario, llm: LLM, seed: int = 0) -> None:
        self.sc, self.llm, self.seed = scenario, llm, seed
        self.history: list[dict[str, str]] = []
        self.persona_breaks = 0
        self.broken = False  # True if a turn still failed the guards after regeneration

    def next_turn(self, agent_said: str | None) -> CallerTurn:
        """Produce the caller's next message. A guard failure gets one regeneration."""
        if agent_said is not None:
            self.history.append({"role": "user", "content": f"Support agent: {agent_said}"})
        else:
            self.history.append({"role": "user", "content": "The chat just opened. Write first."})
        turn = self.llm.parse(system_prompt(self.sc, self.seed), self.history, CallerTurn)
        for _ in range(2):
            if not invented_facts(turn.message, self.sc.known_facts) and not role_break(
                turn.message
            ):
                break
            self.persona_breaks += 1
            self.history.append(
                {
                    "role": "user",
                    "content": "That was wrong: use only your facts and speak as the customer.",
                }
            )
            turn = self.llm.parse(system_prompt(self.sc, self.seed), self.history, CallerTurn)
        self.broken = self.broken or bool(
            invented_facts(turn.message, self.sc.known_facts) or role_break(turn.message)
        )
        self.history.append({"role": "assistant", "content": turn.message})
        return turn
