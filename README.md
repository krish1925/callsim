# callsim

Rule-based checks for contact-center agents, built around **what the contact flow actually did**, not just what the agent said.

Generic voice-agent evals (EVA, Pipecat Evals, LangWatch) score the conversation. In Amazon Connect the interesting failures happen behind it: a Lambda called with an ID the caller never gave, a transfer to a queue with no context for the human, a Lex intent that disagrees with the reply. callsim pulls the flow logs, Lambda logs and Lex intent for a contact, merges them into one trace, and runs deterministic checks on it.

**Status: pre-v0.1, work in progress.** The scoring core and the log extractor are done and tested. The Connect chat driver, scenarios and the write-up are not yet.

## What works today

| Piece | State |
|---|---|
| Trace model (`callsim/trace.py`) | Done. One ordered event list per call: caller/agent messages, tool calls and results, transfers, intents. |
| Scenario expectations (`callsim/schema.py`) | Done. Tool-call matchers (`equals`, `regex`, `subset`, `any`), forbidden tools, escalation and latency expectations. |
| Checks (`callsim/scorers/`) | Done, no network and no LLM. See below. |
| Connect log extractor (`callsim/adapters/connect_logs.py`) | Done as pure functions over CloudWatch records, tested on fixtures. Flow-log field names are **not yet verified against a real instance**. |
| Known-bad test | Done. A trace with four planted faults fails exactly four checks. |
| LLM client (`callsim/llm.py`) | Done. Stdlib client for any OpenAI-compatible server; defaults to a local MiMo on `127.0.0.1:8000`. Override with `CALLSIM_LLM_BASE_URL` / `CALLSIM_LLM_MODEL`. |
| Simulated caller (`callsim/caller.py`) | Done, with fact and role-break guards. |
| Scenarios | 18 in `scenarios/`, linted and coverage-checked. Design in [docs/TEST_STRATEGY.md](docs/TEST_STRATEGY.md). |
| Connect chat driver | Not started (needs a test instance). |

## The checks

| Check | Fails when | Severity |
|---|---|---|
| `escalation` | a required transfer never happens or comes after `by_turn` | critical |
| | the transfer carries none of the expected reason context | major |
| | a transfer happens when none was needed | major |
| `tool_calls` | a forbidden tool is called | critical |
| | an expected call is missing, out of order, or has the wrong args; extra calls exceed the cap | major |
| `arg_grounding` | a tool argument was never said by the caller or returned by an earlier tool | critical |
| `text_turn_latency` | p95 of text-mode turn latency exceeds the budget | warning |

If backend logs never arrive, the backend-dependent checks return `unknown`, never `fail`, and `unknown` never counts as a pass.
Latency is text-mode turn latency only. It says nothing about voice latency.

## Why standalone

EVA can drive an outside agent only through Twilio-framed audio, its simulated callers are audio, and its text-only mode is internal. A Connect chat adapter doesn't fit it. Details in [docs/EVA_CHECK.md](docs/EVA_CHECK.md). The escalation and grounding checks are domain-neutral and are candidates to propose upstream.

## Safety

Connect runs only against a test instance. The driver will refuse any target whose environment isn't `test`/`staging` or whose instance ARN and flow ID aren't on an exact allowlist. Contacts are tagged `callsim=true`, personas are synthetic (`example.test` emails, 555 numbers, `ACCT-` IDs), and traces are redacted before they are written.

## Development

Python 3.12, [uv](https://docs.astral.sh/uv/).

```bash
uv sync
make check   # ruff, mypy --strict, pytest
```

## License

Apache-2.0, see [LICENSE](LICENSE).
