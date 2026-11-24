"""Scorers are pure functions over a Trace. No network, no LLM (D8, D9)."""

from typing import Literal

from pydantic import BaseModel, Field

Severity = Literal["warning", "major", "critical"]
_RANK: dict[str, int] = {"warning": 0, "major": 1, "critical": 2}


class ScoreResult(BaseModel):
    metric: str
    status: Literal["pass", "fail", "unknown"]
    severity: Severity | None = None
    outcome: str | None = None
    evidence: list[str] = Field(default_factory=list)
    detail: str = ""


def worst(a: Severity | None, b: Severity) -> Severity:
    return b if a is None or _RANK[b] > _RANK[a] else a


def unknown(metric: str, detail: str) -> ScoreResult:
    return ScoreResult(metric=metric, status="unknown", detail=detail)
