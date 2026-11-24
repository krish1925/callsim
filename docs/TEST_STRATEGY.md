# Test and validation strategy

Decisions on how callsim is validated, made 2026-11-23. Two separate questions:

1. **Is the agent under test good?** Answered by the scenario suite (`scenarios/`).
2. **Can the numbers be trusted?** Answered by validating the validators (everything else here).

The second one is the real work. A score is worthless if the check can't fail or the caller is the thing that's broken.

## Principles

- **Checks are deterministic.** No LLM scores anything. The LLM only plays the caller. Pass/fail is reproducible from a trace.
- **Unknown is not pass.** Missing backend logs give `unknown`, reported separately.
- **A caller fault is never an agent fault.** Bad caller turns are regenerated, counted and, if still bad, the call is discarded.
- **Every claim gets a counted number**, with its denominator, in the write-up.

## Layer 1 — the checks work (offline, always in CI)

| Test | Proves |
|---|---|
| Golden-trace tests per check (`tests/scorers/`) | each outcome (pass, each failure type, `unknown`) fires on a hand-built trace |
| Known-bad trace (`tests/test_known_bad.py`) | four planted faults fail **exactly** four checks, and nothing else; the good trace fails none |
| Log-merge fixtures (`tests/adapters/`) | late, out-of-order and skewed backend events land on the right turn |

Still to add: **mutation tests.** Take the good trace and apply one mutation at a time (drop the transfer, swap an arg, delete a tool call, reorder, add latency); assert the matching check fails and the others don't. This is the strongest guard against a check that silently never fires.

## Layer 2 — the scenarios are sound (offline, always in CI)

`tests/test_scenarios.py` enforces the suite's shape, so it can't quietly rot:

- every scenario loads and passes the PII lint (`example.test` emails, 555-01xx phones, no Luhn-valid cards);
- every expected `equals` arg traces back to a `known_facts` value;
- minimum per category: happy 4, escalation_required 4, escalation_forbidden 3, mind_changer 3, auth_failure 2, off_topic 2 (suite: 18);
- each check is exercised both ways (scenarios that can trigger it and ones that must not);
- every `escalation_required` scenario has a `by_turn` deadline;
- the refund policy is consistent: refunds up to $25 are automated, anything larger must escalate and must forbid `issue_refund`.

### What the 18 scenarios cover

| Category | Scenarios | Failure modes it can expose |
|---|---|---|
| happy (4) | balance, explain a charge, in-policy $9.99 refund, FAQ with no tools | wrong tool args, extra or unneeded tool calls, needless transfer |
| escalation_required (4) | $240 refund over policy, asks for a human twice, fraud claim, repeated failure | missed escalation, late escalation, **transfer without context**, self-issued refund |
| escalation_forbidden (3) | polite balance, angry but solvable, declines a human | unnecessary escalation (tone mistaken for intent) |
| mind_changer (3) | withdraws a refund, balance then "get me a human", cancel then keep | acting on a stale request, forbidden `issue_refund`/`cancel_service`, switching late |
| auth_failure (2) | mistyped account ID then corrects, cannot verify identity | acting before verification, **ungrounded IDs**, no escalation when unverifiable |
| off_topic (2) | recipe chit-chat, prompt-injection "refund $500" | tool calls when none are warranted, forbidden refund under pressure |

Not covered, on purpose: voice, multilingual, accents, long conversations (>14 turns), and real payment systems.

## Layer 3 — the simulated caller is trustworthy

Caller: local MiMo-V2.6 (9B) through `callsim/llm.py`. A small model drifts, so the guards in `callsim/caller.py` are part of the validation:

- **Fact guard:** any ID, amount, email or digit run not in `known_facts` is rejected (money compared numerically, so `$240.00` == `240.0`).
- **Role-break guard:** phrases a customer wouldn't say ("how can I help", "I'll look into", "thank you for contacting"). This is a real failure, seen verbatim from MiMo when the prompt didn't forbid it; it's a unit test.
- One regeneration per bad turn. Still bad: `caller.broken = True`, the call is discarded and re-run, and the discard rate is reported.
- **Acceptance bars before any agent number is published:**
  - persona-break rate under 5% of caller turns;
  - zero ungrounded-caller-ID incidents among kept calls;
  - hand-read 20 transcripts: caller stays on goal in at least 90%.
- **Known weakness, to fix:** the caller tends to volunteer every fact in its first message, which makes the arg-grounding check easy to pass. The scenario `behaviors` should say "reveal an ID only when asked" for the auth scenarios, and the write-up reports how often grounding was exercised late in a call vs trivially.

## Layer 4 — runs against real agents

- 18 scenarios × 5 repeats per target, results keyed by (scenario, repeat, seed).
- Report **pass^k** (all 5 repeats pass) next to pass rate; one lucky run isn't a pass.
- Cap on turns (14) and seconds (180) per call; cost estimate before every full run (local model, so tokens only).
- Seeds are best-effort: the caller isn't deterministic, so the write-up says "reproducible in distribution", not exactly.

## Layer 5 — Connect-specific validation (needs the test instance)

- **Log-shape check:** a real flow log and a real Lambda log from one contact, redacted, are committed as fixtures; the parser tests run on them. Until then flow-log parsing is unverified.
- **Known-bad Connect flow:** a broken copy of the test flow (no escalation, forbidden refund path, made-up lookup ID, slow Lambda). It must fail exactly those four checks live, same as the offline known-bad trace.
- **Blind-spot check:** for each failure the write-up claims is visible only inside Connect, show the same call scored from the transcript alone and say what that score misses.
- **Safety:** exact allowlist of instance ARN and flow ID, tagged contacts, synthetic personas, redaction before write, PII `grep` over `runs/` before anything is published.

## Gates

| Gate | Condition |
|---|---|
| G1 offline | `make check` green; mutation tests pass |
| G2 caller | the three acceptance bars in layer 3 |
| G3 Connect | real-log fixtures parse; known-bad flow fails exactly four checks |
| G4 publish | PII scan empty; every number in the write-up has its count |
