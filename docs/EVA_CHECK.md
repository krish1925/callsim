# EVA check (2026-11-23)

Repo: https://github.com/ServiceNow/eva (MIT, active; last push 2026-11-24). Read from a shallow clone of `main`.

## Findings

1. **Not airline-only any more.** `data/` has `airline`, `itsm` and `medical_hr` datasets (213 scenarios, 3 domains). None is a contact-center billing/refund domain, and nothing mentions Amazon Connect.
2. **External agents are supported, but over audio.** `docs/assistant_server_contract.md`: a new agent is a subclass of `AbstractAssistantServer` that exposes `ws://localhost:{port}/ws` speaking **Twilio Media Streams audio frames**, and writes an audit log. EVA's simulated callers (ElevenLabs Agents, OpenAI Realtime) are audio callers.
3. **Text mode exists, but only for EVA's own agent.** `scripts/run_text_only.py` drives EVA's in-process `AgenticSystem` with an LLM caller. It is not an interface for an outside agent.
4. **Tool calls come from EVA's own `ToolExecutor`** against a scenario database (`execute_tool()` is required; direct handler calls are forbidden). A Connect flow's Lambda tool calls don't pass through it, so the Connect-side tool/transfer events can't be fed in without changing core code.
5. **No escalation or arg-grounding metric** (grep for transfer/escalat only hits domain tool code and the user-behaviour metric). This confirms the gap.
6. **Contributing:** large features need an issue or discussion first; review bandwidth is limited.

## Decision

An EVA adapter PR doesn't fit the Connect chat target:
- It would mean a Connect **voice** path (telephony to Twilio-framed audio), not the chat API in this plan.
- The text-only path is internal to EVA.

So: **ship `callsim` as a small standalone package**, text mode, Connect chat only.
Still worth doing for upstream credit:
- Run EVA (audio, Pipecat) against the Pipecat/LiveKit example agents for the write-up's first half.
- Open a GitHub Discussion on EVA proposing contact-center escalation and arg-grounding metrics. The checks are rule-based and domain-neutral, so they are the likelier PR than a Connect adapter.

Caller side for Connect: EVA's callers are audio, so use a minimal text LLM caller in `callsim`. (Confirm with you: this reopens "no own caller LLM" from the plan, and `CLAUDE.md` says no new deps without asking, so the `anthropic` SDK is a dependency to approve.)
