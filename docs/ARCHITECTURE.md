# WOW AI - Phase 1 Architecture

## Product direction

WOW AI is not a wrapper around a hosted AI API. The backend is built around a
set of **provider interfaces** (`backend/app/interfaces/`). Every place the
system needs speech recognition, speech synthesis, reasoning, telephony,
memory, or context, it depends on an abstract interface - never on a specific
vendor SDK. Phase 1 ships real, working implementations of those interfaces
that have zero external AI API dependency (a rule-based reasoning provider, a
Postgres/pgvector memory store). Swapping in a self-hosted or fine-tuned model
later means writing one new class that implements the existing interface -
nothing in `app/brain` or `app/api` has to change.

## Monorepo layout

```
wow-ai/
├── backend/            FastAPI service - the "brain" and REST API
│   ├── app/
│   │   ├── models/      SQLAlchemy ORM models (the 9 domain entities)
│   │   ├── interfaces/  Abstract provider contracts (STT/TTS/LLM/Telephony/...)
│   │   ├── providers/   Phase 1 concrete implementations of those interfaces
│   │   ├── brain/       WOW Brain v0 (AgentRuntime) + ContextEngine + state store
│   │   ├── api/         FastAPI routers, request/response schemas, DI wiring
│   │   ├── db/          Declarative base + async session/engine
│   │   └── config.py    Environment-driven settings (pydantic-settings)
│   └── tests/
├── mobile/              Flutter Android app (Dart UI + Kotlin native shell)
│   ├── lib/              Dart app code
│   ├── android/          Native Android project (Kotlin, embedding v2)
│   └── test/
├── docker-compose.yml   Postgres(+pgvector) + Redis + backend
└── docs/
```

## Domain model (backend/app/models)

| Table                | Purpose                                                             |
|-----------------------|----------------------------------------------------------------------|
| `users`               | The phone owner WOW AI acts on behalf of.                           |
| `contacts`             | People known to the user; used to identify callers.                 |
| `context_profiles`     | Named persona/behavior profiles ("sleeping", "work-hours", per-contact). |
| `calls`                | A phone call WOW AI handled or observed.                            |
| `conversations`        | A conversation session (tied to a call, or standalone).             |
| `transcript_segments`  | Per-utterance STT output, tagged by speaker.                        |
| `summaries`            | Short post-call summary + key points + action items.                |
| `memories`             | Facts, embedded via pgvector for semantic recall - typed (`memory_type`: episodic/semantic/contact/short_term), trust-tiered (`status`: observed/inferred/confirmed/user_approved), soft-deletable. |
| `agent_states`         | Durable key/value working state for the brain, scoped per user/conversation. |

No Alembic migrations yet - Phase 1 bootstraps the schema with
`Base.metadata.create_all()` on startup. Introduce Alembic once the schema
needs versioned, production-safe migrations.

## Provider interfaces (backend/app/interfaces)

| Interface              | Phase 1 concrete implementation                          | Phase 2 direction |
|-------------------------|-----------------------------------------------------------|--------------------|
| `SpeechToTextProvider`  | `SimulatedSTTProvider` (deterministic local stand-in, see below) - no real ASR | Self-hosted streaming ASR (e.g. faster-whisper) |
| `TextToSpeechProvider`  | `SimulatedTTSProvider` (deterministic local stand-in, see below) - no real synthesis | Self-hosted TTS (e.g. Piper/Coqui) |
| `LanguageModelProvider` | `RuleBasedLanguageModelProvider` (keyword intent classifier) | Self-hosted/fine-tuned LLM |
| `TelephonyProvider`     | `SimulatedTelephonyProvider` (deterministic local stand-in, see below) - no real carrier/VoIP | Android `CallScreeningService`/`InCallService` bridge |
| `MemoryStore`           | `PgVectorMemoryStore` (Postgres + pgvector)                 | Same store, real embeddings once a local embedding model is wired in |
| `ContextEngine`         | `DefaultContextEngine` (contact + profile + memory lookup)  | Add conversation history summarization |
| `AgentRuntime`          | `WowBrain` (v0, default) / `WowAgent` (opt-in, `AGENT_RUNTIME=wow_agent`) | `WowAgent` promoted to default once proven on real traffic |

STT/TTS/Telephony are contract-only in Phase 1 because they require real
audio/call infrastructure that only exists once the Android call-handling
work in Phase 2 begins. Defining them now means the brain and API layers
never need to change shape when that infrastructure lands.

## WOW Brain v0 (backend/app/brain/wow_brain.py)

```
text in -> ContextEngine.build_context()   (who's calling, active persona, memories)
        -> LanguageModelProvider.generate() (classify intent, produce a reply)
        -> StateRepository.set()            (persist turn_count, last_intent)
        -> AgentAction out                  (structured: {type, payload})
```

This is intentionally a straight-line sequence rather than a branching graph
engine. The seams are exactly what a real multi-node LangGraph-style graph
would plug into next: swap `WowBrain.handle_input` for a graph executor that
calls the same `LanguageModelProvider` / `ContextEngine` / `StateRepository`
at each node, without changing the `AgentRuntime` contract the API depends on.

## Memory safety (backend/app/models/memory.py, app/interfaces/memory_store.py)

A memory is not automatically a permanent fact. Every `Memory` row carries:

- `memory_type` (`MemoryType`): `episodic` (what happened in a call),
  `semantic` (a stable fact/preference), `contact` (about a specific
  contact/relationship), or `short_term` (this call only).
- `status` (`MemoryStatus`): `observed` (default - WOW heard it stated) ->
  `inferred` (WOW derived it) -> `confirmed`/`user_approved` (an explicit
  confirmation step happened). `MemoryStore.add` defaults every new memory
  to `observed`; nothing promotes a row to `user_approved` except an
  explicit `MemoryStore.approve` call (`POST /memories/{id}/approve`).
- `confidence`: optional float, separate from `status` - "how sure" vs.
  "how was this obtained".
- `deleted_at`: soft-delete marker. `DELETE /memories/{id}`
  (`MemoryStore.delete`) sets it rather than removing the row, so retrieval
  (`MemoryStore.search`) excludes it by default while it stays available
  for audit; `personalization.reset_personalization` still issues a real
  hard `DELETE` for its "wipe everything" semantics.

`MemoryStore.search` stays selective by design - always `top_k`-bounded,
optionally narrowed to one `memory_type` - never a full dump of a user's
memory into a prompt.

## WOW Agent orchestrator - opt-in (backend/app/agent/)

`WowBrain` v0 above is a straight-line 3-step flow. `WowAgent`
(`backend/app/agent/orchestrator.py`, select with `AGENT_RUNTIME=wow_agent`)
implements the same `AgentRuntime` contract but runs the fuller flow the
product vision calls for - opt-in today, the same rollout pattern already
used for `MODEL_PROVIDER=local_wow` (real and tested, not yet the default
until proven):

```
state loaded  -> record caller turn (ConversationState, app/agent/state.py)
             -> ContextEngine.build_context()   (contact, active persona, memories)
             -> LanguageModelProvider.generate() (intent/context/action + confidence)
             -> validate action against taxonomy  (app.brain.taxonomy.is_valid_action -
                                                     an out-of-taxonomy prediction is
                                                     never trusted, regardless of its
                                                     reported confidence)
             -> ConfidencePolicy.assess()          (per-head confidence vs threshold)
             -> PolicyEngine.evaluate()            (app/agent/policy.py: ALLOW / CLARIFY /
                                                     REFUSE / HANDOFF)
             -> ToolRegistry.invoke()  (only on ALLOW + a mapped action; authorization,
                                         schema validation, timeout, and audit on every call -
                                         app/agent/tools.py)
             -> generate_response()    (app/agent/response.py: LLM reply on ALLOW, a
                                         verdict-specific template otherwise - never blank)
             -> state persisted back (ConversationState.to_dict() via StateRepository)
```

`ConversationState` (`app/agent/state.py`) is the explicit, serializable
session object every step reads and writes - session/user id, lifecycle
status (`CallLifecycleStatus`: created/ringing/connected/listening/
thinking/responding/ending/ended/processing/stored/expired), transcript,
intent/context/candidate action, memory results, tool results, policy
decision, confidence. It is never a hidden global: it is loaded from and
saved back to the existing `AgentState` table (as a JSON blob under key
`"conversation_state"`) on every turn.

The initial tool set (`app/agent/builtin_tools.py`) is deliberately small
and real, not a placeholder list: `save_memory` (backed by the existing
`MemoryStore`) and `create_summary` (backed by a new `SummaryRepository`,
mirroring `StateRepository`'s ABC + SQL + in-memory-test-double pattern).
Actions that need a real API-side effect that doesn't exist yet
(`SET_CONTEXT` actually flipping a `ContextProfile`, `ANSWER_CALL` actually
answering a call) are reported in the response payload
(`candidate_action`) but do not invoke a tool - claiming to execute them
would be exactly the "fake functionality" this project's engineering
principles rule out.

## Local simulators + simulated-call harness (backend/app/providers/{stt,tts,telephony}/simulated.py, app/simulation/)

No real audio hardware, ASR/TTS engine, or telephony infrastructure is
available in this development environment. Rather than leaving
`SpeechToTextProvider`/`TextToSpeechProvider`/`TelephonyProvider`
contract-only indefinitely, or - worse - faking a "real" implementation
that secretly does nothing, Phase 1 ships **deterministic local
simulators** that satisfy the exact same interfaces:

- `SimulatedSTTProvider`: treats an "audio chunk" as UTF-8 text bytes
  standing in for what a real engine would have already transcribed.
  `feed()` returns a partial result per chunk; a chunk ending in
  `.`/`?`/`!` (or `close()`) produces the final result - a simple,
  inspectable stand-in for real turn-final detection.
- `SimulatedTTSProvider`: "synthesizes" the UTF-8 bytes of the text itself
  (`stream_synthesize` yields it word-by-word).
- `SimulatedTelephonyProvider`: an in-memory call log (answered/ended,
  inbound/outbound audio) plus `inject_caller_audio` (simulation-only, not
  part of `TelephonyProvider` - stands in for "the carrier delivered this
  inbound chunk").

`app/simulation/call_simulator.run_simulated_call` drives a scripted
caller conversation through the **real** stack above these three seams:
`SpeechToTextProvider -> AgentRuntime (WowBrain/WowAgent) ->
TextToSpeechProvider -> TelephonyProvider`. Everything except the audio
source/sink is the production code path. `backend/tests/test_call_simulation.py`
exercises this with `WowAgent` + `RuleBasedLanguageModelProvider` end to
end: answer -> multi-turn conversation -> end, verifying transcripts,
replies, and that every reply actually reaches "telephony" as outbound
audio - this is the closest thing Phase 1 has to demonstrating a realistic
simulated personal call (see README "Current limitations": it is
explicitly not real telephony, and is never described as such).

## Observability (backend/app/observability/)

`WowAgent` measures four stages per turn - `context` (ContextEngine),
`brain` (LanguageModelProvider), `policy` (PolicyEngine), and, when a tool
runs, `tool` and `response` - via `StageTimings` (`timing.py`) and emits
one structured log record per turn via `log_agent_turn` (`logging.py`).
`log_agent_turn`'s signature has no `text`/`reply`/transcript parameter at
all - not "redacted before logging", but structurally incapable of
receiving conversation content - so per docs "Privacy", ordinary
application logs never carry turn text, only IDs, enums, and durations.
The same `durations_ms` are also returned in `AgentAction.payload` for API
consumers. `WowBrain` v0 does not yet emit these (see "Roadmap").

## Backend request flow

`POST /brain/command` (see `app/api/routes/brain.py`) is the single entry
point Phase 1 needs: it takes `{user_id, text, caller_number?}`, wires up a
request-scoped `WowBrain` via `app/api/deps.py`, and returns the resulting
`AgentAction`. This is what the Android app calls today, and what a real
in-call audio pipeline will call once STT is wired up.

## Mobile app (mobile/)

Flutter/Dart UI, Kotlin native shell (`MainActivity.kt`), no telephony
permissions requested yet. Phase 1's `HomeScreen` only verifies backend
connectivity and round-trips a text command through `/brain/command` - proof
that the client/server contract works end-to-end. Phase 2 adds a
`MethodChannel` bridging Android's `CallScreeningService`/`InCallService`
into Dart so real incoming calls can drive the same `WowBrain`.
