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
| `memories`             | Long-term facts, embedded via pgvector for semantic recall.         |
| `agent_states`         | Durable key/value working state for the brain, scoped per user/conversation. |

No Alembic migrations yet - Phase 1 bootstraps the schema with
`Base.metadata.create_all()` on startup. Introduce Alembic once the schema
needs versioned, production-safe migrations.

## Provider interfaces (backend/app/interfaces)

| Interface              | Phase 1 concrete implementation                          | Phase 2 direction |
|-------------------------|-----------------------------------------------------------|--------------------|
| `SpeechToTextProvider`  | *(contract only)*                                          | Self-hosted streaming ASR (e.g. faster-whisper) |
| `TextToSpeechProvider`  | *(contract only)*                                          | Self-hosted TTS (e.g. Piper/Coqui) |
| `LanguageModelProvider` | `RuleBasedLanguageModelProvider` (keyword intent classifier) | Self-hosted/fine-tuned LLM |
| `TelephonyProvider`     | *(contract only)*                                          | Android `CallScreeningService`/`InCallService` bridge |
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
