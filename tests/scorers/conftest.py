from typing import Any

from callsim.trace import Event, Trace


class B:
    """Tiny trace builder so each golden case reads as the conversation it models."""

    def __init__(self, backend_ok: bool = True) -> None:
        self.events: list[Event] = []
        self.turn = 0
        self.backend_ok = backend_ok

    def _add(self, type_: str, **kw: Any) -> "B":
        n = len(self.events) + 1
        self.events.append(
            Event(id=f"e{n}", type=type_, turn=self.turn, ts=n * 100, **kw)  # type: ignore[arg-type]
        )
        return self

    def caller(self, text: str) -> "B":
        self.turn += 1
        return self._add("caller_msg", text=text)

    def agent(self, text: str, latency_ms: int | None = None) -> "B":
        return self._add("agent_msg", text=text, latency_ms=latency_ms)

    def call(self, name: str, **args: Any) -> "B":
        return self._add("tool_call", name=name, args=args, source="backend")

    def result(self, name: str, result: Any) -> "B":
        return self._add("tool_result", name=name, result=result, source="backend")

    def transfer(self, queue: str = "BillingQueue", **attrs: str) -> "B":
        return self._add("transfer", queue=queue, attributes=attrs, source="backend")

    def build(self) -> Trace:
        return Trace(events=self.events, backend_ok=self.backend_ok)
