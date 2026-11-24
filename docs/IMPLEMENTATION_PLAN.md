# callsim v0.1 — Implementation Plan

Source: "Contact-Center Agent Test Harness — 2-Weekend Build Plan" (2026-11-23).
This file turns that design into file-by-file tasks, interfaces, tests and acceptance
checks for each 4h block. The design doc is the spec; this is the build order.

Name check (2026-11-23): `callsim` is free on PyPI (404 on `/pypi/callsim/json`).
GitHub repo `krish1925/callsim` exists.

---

## 0. Decisions made up front

These fill gaps the design doc leaves open. Change them here first, not in code.

| # | Decision | Why |
|---|----------|-----|
| D1 | **Turns.** `turn` is an int that goes up by one on every `caller_msg`. Agent events between two caller messages belong to the earlier turn. Backend events get their turn assigned during the merge (§3.3). | Gives every scorer one shared clock. |
| D2 | **When the agent's turn ends (text mode).** Adapter signal if the platform has one (Pipecat: end of LLM response frame). Otherwise quiescence: no `agent_msg` for `turn_idle_ms` (default 1500 ms) after the last one, with a hard cap of `limits.max_seconds`. Connect always uses quiescence plus typing events. | Connect chat has no end-of-turn marker. Latency is taken from the *first* agent_msg, so the quiescence window doesn't skew it. |
| D3 | **Event IDs** are `e{n}`, numbered per call in append order. Backend events get IDs when they're merged and are written in a second pass (§3.3). | Evidence lists stay stable when you rescore. |
| D4 | **LLM client.** One wrapper `callsim/llm.py` over the official `anthropic` SDK. Caller default `claude-sonnet-5-5`, judge default `claude-opus-5-5`; both set in `callsim.toml`. Structured output through `client.messages.parse()` with pydantic models. | Different models for caller and judge, as the doc asks. |
| D5 | **"Judge at temperature 0" can't be done literally**: current Claude models reject `temperature`. Instead: fixed prompt, effort `low` or `medium`, structured output, and the prompt hash plus model ID in every trace. Measure judge variance by running it 3× on the 20 hand-labelled traces and reporting how often it agrees with itself. | The API removed sampling parameters. Put this in the write-up's limits. |
| D6 | **Refusals.** The LLM wrapper checks `stop_reason == "refusal"` and raises `LLMRefusal`. The caller treats that as a harness error (exit 2) for that call, never as an agent failure. Turn server-side fallbacks on (`fallbacks: "default"`) and log which model actually answered. | The off-topic/abuse scenarios could trip the safety classifiers. |
| D7 | **Run layout.** `runs/<run_id>/<scenario_id>/r<repeat>_s<seed>.jsonl` plus `runs/<run_id>/manifest.json`. A call counts as done when its trace has a `call_end` and at least one `score` line. Resume skips calls that are done. | Results keyed by (scenario, repeat, seed), as the doc asks. |
| D8 | **Unknown is its own score outcome.** `ScoreResult.status` is one of `pass | fail | unknown`. It's `unknown` when the backend logs didn't arrive before the timeout. `unknown` never counts as a pass toward pass^k, and is reported separately. | The risk table says to mark missing logs unknown, not failed. |
| D9 | **Severity order:** `critical > major > warning`. The baseline gate fails when pass^k drops for any scenario or a new `critical` appears (§5.3). | |
| D10 | **Seeds.** The seed goes into the caller's system prompt ("variation seed N") and picks persona phrasing variants. The LLM itself isn't deterministic, so the header says reproduction is best-effort. | Be honest in the viewer's "reproduce" line. |

---

## 1. Repo layout (final v0.1)

```
callsim/
  __init__.py          # __version__, public re-exports
  cli.py               # typer: run, rescore, view, validate
  config.py            # callsim.toml loader (targets, models, caps)
  schema.py            # Scenario, Persona, Expected, matchers, Limits
  trace.py             # TraceEvent union, TraceHeader, ScoreLine, JSONL reader/writer
  llm.py               # thin anthropic wrapper, token + cost accounting
  caller.py            # persona LLM; CallerTurn output model; fact guard
  runner.py            # orchestration: k repeats, semaphore, budgets, resume
  safety.py            # allowlist, redaction, PII lint, cost caps
  adapters/
    base.py            # AgentAdapter Protocol, Session, EndReason
    fake.py            # in-proc scripted agent (good + known-bad modes)
    pipecat.py
    connect.py
    connect_logs.py    # CloudWatch query + parse + merge
  scorers/
    base.py            # ScoreResult, Severity, registry
    latency.py intent.py escalation.py tools.py grounding.py judge.py
  report/
    jsonl.py html.py junit.py markdown.py baseline.py
    templates/viewer.html.j2
scenarios/ personas/ fixtures/{golden,agents}/ tests/ examples/github-action.yml
```

Note: the design doc's scorer table lists **Arg grounding** as its own metric. It gets
its own module, `scorers/grounding.py`, instead of living inside `tools.py`.

---

## 2. Weekend 1 — core + Pipecat

### Block 1 · Sat AM (4h) — skeleton + end-to-end against fake agent

Files, in order:

1. **Tooling:** `pyproject.toml` (uv, hatchling, Python 3.12; extras `connect = [boto3, websockets]`,
   `pipecat = [pipecat-ai]`; dev deps `pytest, pytest-asyncio, ruff, mypy`), `Makefile`
   (`check: ruff check, ruff format --check, mypy --strict callsim/, pytest -q`), `LICENSE`
   (Apache-2.0), `.github/workflows/ci.yml` running `make check`.
2. **`schema.py`:**
   - `Persona(name, style, patience: Literal[low,medium,high], literacy, language, never: list[str])`
   - `Limits(max_turns: int = 14, max_seconds: int = 180)`
   - Arg matchers as a discriminated union: `Equals(equals)`, `Regex(regex)`, `Subset(subset: dict)`, `Any_(any: Literal[True])`
   - `ExpectedToolCall(name, args: dict[str, Matcher] = {})`
   - `ToolsExpect(order: Literal[in_order, any_order], calls, forbidden: list[str] = [], max_extra_calls: int = 0)`
   - `EscalationExpect(required: bool, reason_contains: list[str] = [], by_turn: int | None)`
   - `LatencyExpect(p95_ms: int)`
   - `IntentExpect`: a bare string, or a list of `{intent, from_turn}` for mind-changer scenarios
   - `Expected(intent, tools, escalation, latency, judge_rubric: list[str])`
   - `Scenario(id, persona: Path | Persona, goal, known_facts: dict[str, str|int|float], behaviors, limits, expected, repeats = 5, tags)`. `model_config = extra="forbid"` everywhere.
   - `load_scenario(path)` resolves the persona path relative to the repo root.
3. **`trace.py`:** a base `TraceEvent(id, type, turn, ts: int, source: Literal[live,backend], raw: dict | None, ts_backend: int | None)`
   with one subclass for each of the 8 types, a discriminated union on `type`, plus `TraceHeader` and `ScoreLine`.
   `TraceWriter` (append-only, flush per line, redacts before writing: it calls `safety.redact` and is stubbed to identity until Block 7)
   and `read_trace(path) -> Trace(header, events, scores)`.
4. **`safety.py` (part 1):** `lint_known_facts(scenario)` rejects emails not on `example.test`/`example.com`,
   phone numbers that aren't 555-01xx, and digit runs that look like cards (Luhn check). `validate` calls it.
5. **`cli.py validate`:** schema + PII lint + "every `equals` arg in expected traces back to a known_facts value
   (or is marked `from_tool: true`)". Exit 0 or 2.
6. **`llm.py`:** `LLM(model, effort).parse(system, messages, output_model) -> (obj, Usage)`; records
   input/output tokens; `estimate_usd(usage, model)` from a price table in `config.py`; raises `LLMRefusal`.
7. **`caller.py`:** output model `CallerTurn(message: str, end_call: bool, caller_state: CallerState(goal_met, frustrated, asked_for_human))`.
   The system prompt is built from persona + goal + known_facts + behaviors + limits.
   **Fact guard:** after each turn, pull identifier-like tokens out of `message` (ACCT-…, emails, digit runs ≥ 4, money)
   and check that each one is in known_facts. A miss gets one regeneration; a second miss sets `persona_break=True` on the call.
   The runner throws those calls away, re-runs them, and counts how often it happened.
8. **`adapters/base.py` + `adapters/fake.py`:** the Protocol exactly as in the design doc. `FakeAgent` is a
   small rule-based state machine (regex on caller text → canned replies + tool calls against a
   `MockToolRegistry`). Modes: `good` and `bad` (Block 4).
9. **`runner.py` (minimal):** one scenario, one repeat: start → loop(caller → send → collect events until turn end) →
   end → backend_events → write the trace.
10. **`cli.py run`** with `--target fake --scenario PATH`.

Tests first: `tests/test_schema.py` (the example scenario YAML from the doc loads; extra keys are rejected; matcher
parsing), `tests/test_safety_lint.py` (real-looking emails/cards are rejected), `tests/test_trace_roundtrip.py`.

**Acceptance:** `callsim run --target fake --scenario scenarios/billing/double_charge_wants_human.yaml`
writes a trace with a header, caller and agent messages, tool calls and `call_end`. `make check` is green. Commit.

### Block 2 · Sat PM (4h) — Pipecat adapter

1. Pick an upstream Pipecat example that already works with text input, put it under `examples/agents/pipecat_billing/`
   with an LLM-backed bot and 4 tools (`lookup_account`, `list_charges`, `issue_refund`, `transfer_to_human`).
   **Timebox to 45 min.** If text-mode wiring fights back, drive the pipeline with a custom
   input processor that pushes text frames and an output processor that collects them, and skip the transport.
2. **`adapters/pipecat.py`:** builds the pipeline in-process and runs it in a background task. `send()` pushes the caller's text
   into the pipeline. `events()` yields `agent_msg` when a full LLM response arrives (D2) and stamps
   `ts=time.monotonic_ns()`.
3. **Mock tool registry** (`adapters/tools_mock.py`, shared with fake): `register(name, fn)`, and wraps each call to
   emit `tool_call` and then `tool_result` with timing. `transfer_to_human` also emits a `transfer` event. Real tools only
   with `--live-tools`, and that is refused unless the target is `env in {test, staging}` (enforced in `safety.py`).
4. Session metadata: `callsim_run_id`, `callsim=true` go into the pipeline's context / metadata.
5. Latency: the adapter sets `latency_ms` on the first `agent_msg` of each turn (first agent ts minus caller send ts).

Tests: `tests/adapters/test_pipecat_smoke.py` (marked `@pytest.mark.pipecat`, skipped when the extra is missing) runs one
scripted 3-turn conversation using a stub LLM service, so no network is needed.

**Acceptance:** one scenario runs against the Pipecat example, and the trace has tool events and per-turn latency.

### Block 3 · Sun AM (4h) — deterministic scorers (golden traces first)

Write `fixtures/golden/*.jsonl` + `fixtures/golden/expected_scores.yaml` **before** the scorers.
You need at least these golden traces:

| Golden trace | Exercises |
|---|---|
| `g01_clean_escalation` | correct transfer, all tools in order, latency passes |
| `g02_missed_escalation` | caller asked for a human twice, no transfer → critical |
| `g03_unneeded_escalation` | transfer when `required: false` → major |
| `g04_forbidden_tool` | `issue_refund` called → critical |
| `g05_ungrounded_arg` | `lookup_account(ACCT-99999)` never said → critical |
| `g06_out_of_order_and_extra` | order violation + extra calls > max |
| `g07_latency_spike` | p95 passes but one turn > 3× p50 → warning |
| `g08_backend_missing` | backend events absent → tools/escalation `unknown` |

Scorer contract (`scorers/base.py`):
```python
class ScoreResult(BaseModel):
    metric: str; status: Literal["pass","fail","unknown"]; value: float | str | None
    severity: Severity | None; outcome: str | None; evidence: list[str]; detail: str = ""
Scorer = Callable[[Trace, Expected], ScoreResult]   # pure, no I/O
```

- **`tools.py`:** match each expected call to the earliest observed `tool_call` with the same name whose args satisfy the matchers.
  For `in_order`, the matched indices must go up. `forbidden` → critical; any missing → major; extras (observed calls left unmatched)
  > `max_extra_calls` → major. Evidence = event IDs of the offending or missing-context calls.
- **`grounding.py`:** for each `tool_call` arg value (flattened to strings, normalised by case and whitespace, numbers in canonical form),
  it must appear as a substring in an earlier `caller_msg.text` or an earlier `tool_result` payload. Anything that doesn't is critical, and the
  evidence is the `tool_call` ID. Allowlist booleans/enums by declaring `grounding_exempt: [arg names]` on the scenario.
- **`escalation.py`:** a 4-outcome table. `by_turn` is violated → missed (critical). `reason_contains` is checked against the transfer
  event's reason/context text, and failing it gives major `transfer_without_context` (this feeds failure mode 7).
- **`latency.py`:** per-turn `latency_ms`, split into tool turns and non-tool turns; p50/p95 using the nearest-rank method;
  warning severity. Metric name is `text_turn_latency`.
- **`intent.py` (deterministic part):** compares the `intent_detected` events with expected (including `from_turn` switches). If the
  trace has no `intent_detected`, it returns `unknown` and the judge fills it in (Block 4).

Tests: `tests/scorers/test_golden.py` is parametrised over `expected_scores.yaml`, plus unit tests for matchers.

**Acceptance:** all goldens score as expected; `make check` green.

### Block 4 · Sun PM (4h) — judge, runner, markdown, known-bad agent

1. **`scorers/judge.py`:** this is the one scorer that's allowed to call an LLM, so it lives behind `JudgeScorer(llm)`, and the
   pure scorers never import it. Output model:
   `JudgeVerdict(intent_label: Literal[<closed list from suite>], intent_evidence: list[str], rubric: list[RubricItem(line, pass_, evidence: list[str], rationale)])`.
   Reject any item whose `evidence` is empty or cites IDs not in the trace; retry once, then mark it `unknown`.
   Write `judge_model` and `judge_prompt_sha256` into the score line.
2. **`runner.py` (full):** expands (scenario × repeat) into jobs with `seed = base_seed + repeat`;
   `asyncio.Semaphore(max_concurrency)`; a per-call `asyncio.timeout(limits.max_seconds)`; a running cost meter that refuses
   to start new jobs once `max_usd` would be passed; resume per D7; re-runs persona breaks (cap 2).
3. **pass^k:** per scenario `pass_rate = passes/k` and `pass_k = all(passes)`. A call passes when every scorer is `pass`
   (warnings count as passes, `unknown` doesn't count as a pass and is reported separately).
4. **`report/markdown.py`:** a scenario × metric grid, pass^k, the top failures with evidence IDs, cost, and how many persona breaks there were.
5. **Known-bad agent** (`FakeAgent(mode="bad")` *and* a Pipecat variant with a bad system prompt + tool wrapper):
   it must (a) miss an escalation, (b) call `issue_refund`, (c) call `lookup_account` with a made-up ID, (d) sleep 3× p50 on one turn.
   Everything else passes.
6. `tests/test_known_bad.py`: run the fake bad agent through a scripted (non-LLM) caller and assert **exactly** those
   four failures. CI runs this on every push.

**Gate 1:** 5 scenarios × 5 repeats on the good Pipecat agent pass; the known-bad agent fails all 4 checks; `make check` green.
Run a fresh review session over `safety.py` and `scorers/` against the design doc before moving on.

---

## 3. Weeknights — Connect prep (4–6h, mostly the console)

- [ ] Test Connect instance, a chat-enabled contact flow → Lex V2 bot (intents `billing_dispute`, `order_status`, `cancel_service`)
      → Lambda `lookup_account` → transfer-to-queue block (`BillingQueue`).
- [ ] Turn on flow logs for the flow; confirm a log group `/aws/connect/<instance-alias>` with entries per `ContactId`.
- [ ] Lambda guard (5 lines, put it in the README): `if event["Details"]["ContactData"]["Attributes"].get("callsim") == "true": use mock backend`.
- [ ] Have the Lambda set a contact attribute `callsim_last_tool=<name>` as a fallback signal (risk-table mitigation).
- [ ] Write the remaining 15 scenarios (the suite totals 6 happy / 4 esc-required / 3 esc-forbidden / 3 mind-changers / 2 wrong-info / 2 off-topic).
- [ ] `callsim.toml` target entry: `env="test"`, `instance_arn`, `contact_flow_id`, `region`, `log_group`, `aws_profile`.

---

## 4. Weekend 2 — Connect + outputs + ship

### Block 5 · Sat AM (4h) — Connect live path (`adapters/connect.py`)

**Before writing code**, list the operations and check them against botocore (CLAUDE.md rule):

| Service | Operation | Use |
|---|---|---|
| `connect` | `StartChatContact` | start; `Attributes={callsim, callsim_run_id}`; `ParticipantDetails.DisplayName="callsim"` |
| `connectparticipant` | `CreateParticipantConnection` | `Type=["WEBSOCKET","CONNECTION_CREDENTIALS"]` with the participant token |
| `connectparticipant` | `SendMessage` | caller text, `ContentType="text/plain"` |
| `connectparticipant` | `GetTranscript` | after-call reconciliation for messages the websocket missed |
| `connectparticipant` | `DisconnectParticipant` | end |
| `logs` | `StartQuery` / `GetQueryResults` | Block 6 |

- Websocket: connect to the URL in the connection response; subscribe (`{"topic":"aws/subscribe","content":{"topics":["aws/chat"]}}`);
  parse `content` JSON; map `MESSAGE` from `AGENT`/`SYSTEM`/bot → `agent_msg`, typing events → turn-end hints (D2),
  `participant.left` / `chat.ended` → `call_end`. Keep the full frame in `raw`.
- Backoff: one `retry_aws(fn)` helper with exponential backoff and full jitter on `ThrottlingException` / `TooManyRequestsException`,
  max 5 attempts. **No retries on agent responses.**
- `safety.check_target(target)` runs before `StartChatContact`: env is test or staging, and the instance ARN and contact flow ID match the allowlist exactly.

Tests: `tests/adapters/test_connect_unit.py` uses `botocore.stub.Stubber` for the API calls and a local `websockets` server
that replays recorded frames from `fixtures/connect/ws_frames.jsonl` (redacted).

**Acceptance:** a real chat against the test flow produces a trace with agent messages and `call_end`.

### Block 6 · Sat PM (4h) — Connect backend events (`adapters/connect_logs.py`)

1. **Query:** a Logs Insights query over the flow log group plus the Lambda log group, filtered by `ContactId`, time window
   [start−5s, end+120s]. Poll `GetQueryResults` until it's `Complete`; poll again with backoff until the record count stops changing
   or `backend_timeout_s` (default 90 s) runs out → then emit `error{kind:"backend_timeout"}` (scorers return `unknown`).
2. **Parse** (keep everything in `raw`):
   - Lex / GetCustomerInput block results → `intent_detected{intent, confidence}`
   - InvokeExternalResource / Lambda block + Lambda log lines → `tool_call` / `tool_result`
   - TransferContactToQueue / SetQueue → `transfer{queue, attributes}` (attributes = context passed)
   - Fallback: contact attributes from `DescribeContact` (`connect`) if flow logs are empty. Verify the op exists first.
3. **Merge:** sort backend events by their timestamp; for each one, find the live `caller_msg` with the largest
   `ts_wall ≤ backend_ts + skew`, where skew is estimated as median(backend first-message ts − live first-message ts). Assign that turn,
   set `ts` = the live-clock estimate, `ts_backend` = the original. Then append to the trace as a second pass (D3).
4. Fixture-driven tests: `fixtures/connect/flowlogs_*.json` (late, out of order, missing transfer) → expected merged events.

**Acceptance:** Connect traces score on all deterministic metrics, and missing logs show up as `unknown`, not `fail`.

### Block 7 · Sun AM (4h) — outputs + safety

1. **`report/html.py`** + Jinja template: one self-contained file (inline CSS/JS, JSON embedded). Summary grid
   sortable by severity → per-call timeline (bubbles, collapsible tool cards, a `backend` badge), an expected-vs-observed panel,
   a latency strip with tool turns shaded, evidence links (`#e14`), a copyable reproduce command.
2. **`report/junit.py`:** one `<testcase>` per scenario; `<failure>` when `pass_k` is false (or `pass_rate < threshold`).
3. **`report/baseline.py`:** writes `baseline.json` `{scenario: {pass_k, pass_rate, criticals: [metric:outcome]}}`.
   `compare(old, new)` → a regression when pass_k goes true→false or a critical appears that wasn't in old.
4. **Exit codes** in `cli.run`: 0 = pass, 1 = regression or failure, 2 = harness error (config, adapter crash, LLM refusal,
   budget exceeded before finishing). Wrap the entry point so any uncaught exception exits 2.
5. **`safety.py` (complete):** `redact(obj)` walks dicts and strings: emails, phones, card-like runs (Luhn), AWS key IDs
   (`AKIA|ASIA[0-9A-Z]{16}`), secret-looking 40-char base64. It keeps `example.test` values so traces stay readable. `--no-raw` drops `raw`.
   Allowlist enforcement, plus a check that no credentials appear in YAML (reject keys like `aws_secret*`, `api_key`).
6. **`--dry-run`:** job count × estimated tokens per turn × max_turns → printed USD estimate, then exit 0.
7. `examples/github-action.yml`: run the fake suite plus the known-bad check, upload `runs/` as an artifact, post `summary.md` as a PR comment.

Tests: `test_redaction.py` (property-style over generated PII strings), `test_baseline.py`, `test_junit.py` (validated
against the schema), `test_exit_codes.py`, `test_html_snapshot.py` (renders a golden run; checks key element IDs).

### Block 8 · Sun PM (4h) — run + ship

1. Full suite: 20 scenarios × 5 repeats on 2–3 Pipecat example agents and the Connect flow. Check the `--dry-run` estimate first.
2. Judge agreement: hand-label 20 traces into `fixtures/labels/*.yaml`; `callsim rescore --judge-only` then
   `scripts/judge_agreement.py` → agreement % and self-consistency (D5). **Under 85%, don't publish judge metrics.**
3. README: one-command quickstart (`uvx callsim run scenarios/ --target fake`), the Lambda guard, the safety section, the latency caveat.
4. `uv build`, publish to TestPyPI, install it in a clean venv, then PyPI. Tag `v0.1.0`.

**Gate 2:** both targets run 20 scenarios; CI fails on an injected regression (flip one scenario's expected tool);
`grep`-based PII scan over `runs/` comes back empty.

---

## 5. Cross-cutting details

### 5.1 `callsim.toml`
```toml
[models]
caller = "claude-sonnet-5-5"
judge  = "claude-opus-5-5"

[caps]
max_usd = 10.0
max_concurrency = 4
turn_idle_ms = 1500

[targets.pipecat_local]
kind = "pipecat"; env = "test"; entry = "examples.agents.pipecat_billing:build"

[targets.connect_test]
kind = "connect"; env = "test"; region = "us-east-1"; aws_profile = "callsim-test"
instance_arn = "arn:aws:connect:us-east-1:<acct>:instance/<id>"
contact_flow_id = "<id>"; log_groups = ["/aws/connect/<alias>", "/aws/lambda/lookup_account"]
```
Credentials only come from env or the AWS profile. A target without `env` is refused.

### 5.2 CLI surface
```
callsim validate PATH...
callsim run PATH... --target NAME [--repeat N] [--seed S] [--scenario ID] [--baseline FILE]
                    [--dry-run] [--no-raw] [--live-tools] [--resume RUN_DIR] [--out runs/]
callsim rescore RUN_DIR [--judge-only | --no-judge]
callsim view RUN_DIR [--open]
```

### 5.3 Definition of pass for CI
- A scenario passes when `pass_k` is true.
- With `--baseline`, exit 1 only on a regression (D9); with no baseline, exit 1 when any scenario fails.

### 5.4 Test pyramid
| Layer | Network | Runs in CI |
|---|---|---|
| schema / trace / safety / scorers on goldens | none | always |
| fake agent end-to-end with a scripted caller | none | always |
| known-bad agent catches exactly 4 | none | always |
| Pipecat smoke with a stub LLM | none | when the extra is installed |
| Connect unit tests (Stubber + local websocket) | none | always |
| live LLM caller / real Connect | yes | manual `make e2e` only |

---

## 6. Risks to watch while building (beyond the design doc)

- **Pipecat API churn:** pin `pipecat-ai` to an exact version in the extra and record it in the trace header.
- **Connect websocket idle timeout:** send the keep-alive / heartbeat the participant service expects; check this in Block 5.
- **Grounding false positives:** normalisation (e.g. `acct-10442` vs `ACCT-10442`, `$49.99` vs `49.99`) needs its own
  unit tests; when unsure, report it as a warning in v0.1 and tighten it once the goldens prove it out.
- **Cost:** 20 × 5 × ~10 turns × 2 targets is about 2k caller calls plus about 200 judge calls. Run `--dry-run` before each full run.

## 7. Cut order (unchanged from the design doc)
HTML viewer → baseline compare → Lex parsing → resume.
**Never cut:** allowlist, redaction, known-bad agent, golden-trace tests.
