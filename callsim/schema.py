"""Scenario expectations. Matchers are a discriminated union on their key."""

import re
from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Equals(_Strict):
    equals: Any

    def matches(self, value: Any) -> bool:
        return bool(str(value).strip().lower() == str(self.equals).strip().lower())


class Regex(_Strict):
    regex: str

    def matches(self, value: Any) -> bool:
        return re.search(self.regex, str(value)) is not None


class Subset(_Strict):
    subset: dict[str, Any]

    def matches(self, value: Any) -> bool:
        return isinstance(value, dict) and all(value.get(k) == v for k, v in self.subset.items())


class Any_(_Strict):
    any: Literal[True]

    def matches(self, value: Any) -> bool:
        return True


Matcher = Annotated[Equals | Regex | Subset | Any_, Field(union_mode="left_to_right")]


class ExpectedToolCall(_Strict):
    name: str
    args: dict[str, Matcher] = Field(default_factory=dict)


class ToolsExpect(_Strict):
    order: Literal["in_order", "any_order"] = "in_order"
    calls: list[ExpectedToolCall] = Field(default_factory=list)
    forbidden: list[str] = Field(default_factory=list)
    max_extra_calls: int = 0
    grounding_exempt: list[str] = Field(default_factory=list)


class EscalationExpect(_Strict):
    required: bool
    reason_contains: list[str] = Field(default_factory=list)
    by_turn: int | None = None


class LatencyExpect(_Strict):
    p95_ms: int


class Expected(_Strict):
    tools: ToolsExpect = Field(default_factory=ToolsExpect)
    escalation: EscalationExpect | None = None
    latency: LatencyExpect | None = None
