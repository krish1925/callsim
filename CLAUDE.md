# callsim
- Python 3.12, uv, pydantic v2, asyncio. No new deps without asking.
- Run `make check` (ruff, mypy --strict on callsim/, pytest) before saying a task is done.
- Scorers are pure functions over traces. No network or LLM calls inside scorers/ (the judge lives behind `JudgeScorer(llm)` and is the only exception).
- Every scorer change needs a golden-trace test in tests/scorers/.
- AWS: only call APIs that exist in botocore's service model; check with
  `python -c "import boto3; print(boto3.client('connectparticipant').meta.service_model.operation_names)"`.
- Never write real-looking PII in fixtures. Use example.test, 555 numbers, ACCT- ids.
- Adapters emit TraceEvent only; never import scorers from adapters.
- LLM calls go through `callsim/llm.py` only (official `anthropic` SDK, structured output via `messages.parse`). Don't send `temperature`; current models reject it.
- The build plan lives in docs/IMPLEMENTATION_PLAN.md. Decisions D1–D10 there are binding unless changed in that file first.
