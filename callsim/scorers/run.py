from callsim.schema import Expected
from callsim.scorers.base import ScoreResult
from callsim.scorers.escalation import score_escalation
from callsim.scorers.grounding import score_grounding
from callsim.scorers.latency import score_latency
from callsim.scorers.tools import score_tools
from callsim.trace import Trace


def score_all(trace: Trace, expected: Expected) -> list[ScoreResult]:
    results = [score_tools(trace, expected.tools)]
    results.append(score_grounding(trace, expected.tools.grounding_exempt))
    if expected.escalation is not None:
        results.append(score_escalation(trace, expected.escalation))
    if expected.latency is not None:
        results.append(score_latency(trace, expected.latency))
    return results
