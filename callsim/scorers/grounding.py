"""Every tool arg value must have been said by the caller or returned by a tool earlier."""

import re
from typing import Any

from callsim.scorers.base import ScoreResult, unknown
from callsim.trace import Trace

METRIC = "arg_grounding"


def _norm(s: str) -> str:
    return re.sub(r"[\s$,]", "", s.lower())


def _flat(v: Any) -> list[str]:
    if isinstance(v, dict):
        return [x for item in v.values() for x in _flat(item)]
    if isinstance(v, list):
        return [x for item in v for x in _flat(item)]
    if isinstance(v, float) and v.is_integer():
        v = int(v)
    return [str(v)]


def score_grounding(trace: Trace, exempt: list[str] | None = None) -> ScoreResult:
    if not trace.backend_ok:
        return unknown(METRIC, "backend logs missing")
    exempt = exempt or []
    seen = ""
    bad: list[str] = []
    detail: list[str] = []
    for e in trace.events:
        if e.type == "caller_msg" and e.text:
            seen += " " + _norm(e.text)
        elif e.type == "tool_result":
            seen += " " + _norm(" ".join(_flat(e.result)))
        elif e.type == "tool_call":
            for key, val in e.args.items():
                if key in exempt:
                    continue
                for s in _flat(val):
                    if _norm(s) not in seen:
                        bad.append(e.id)
                        detail.append(f"{e.name}.{key}={s!r} not grounded")
    if not bad:
        return ScoreResult(metric=METRIC, status="pass")
    return ScoreResult(
        metric=METRIC,
        status="fail",
        severity="critical",
        outcome="ungrounded_arg",
        evidence=sorted(set(bad)),
        detail="; ".join(detail),
    )
