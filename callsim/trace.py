"""One trace per call. Adapters emit Events; scorers read them (D1, D3, D8)."""

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

EventType = Literal[
    "caller_msg",
    "agent_msg",
    "tool_call",
    "tool_result",
    "transfer",
    "intent_detected",
    "error",
    "call_end",
]


class Event(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str  # e{n}, per call, append order (D3)
    type: EventType
    turn: int  # +1 on every caller_msg (D1)
    ts: int  # ms on the live clock
    source: Literal["live", "backend"] = "live"
    text: str | None = None  # caller_msg / agent_msg
    name: str | None = None  # tool_call / tool_result / intent_detected
    args: dict[str, Any] = Field(default_factory=dict)  # tool_call
    result: Any = None  # tool_result
    queue: str | None = None  # transfer
    attributes: dict[str, str] = Field(default_factory=dict)  # transfer context
    latency_ms: int | None = None  # first agent_msg of a turn
    raw: dict[str, Any] | None = None


class Trace(BaseModel):
    model_config = ConfigDict(extra="forbid")

    events: list[Event]
    # False when backend logs never arrived: backend-dependent checks return unknown (D8).
    backend_ok: bool = True
