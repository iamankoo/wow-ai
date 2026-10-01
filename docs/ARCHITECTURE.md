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

Schema migrations: Alembic (`backend/migrations`, Phase 1 stabilization) -
the baseline adopts a `create_all`-built database; `create_all` still runs at
startup for fresh/dev databases but never alters an existing table. (Original
Phase 1 note, kept for history: "Introduce Alembic once the schema
needs versioned, production-safe migrations.")

## Provider interfaces (backend/app/interfaces)

| Interface              | Phase 1 concrete implementation                          | Phase 2 direction |
|-------------------------|-----------------------------------------------------------|--------------------|
| `SpeechToTextProvider`  | **Real:** `LocalWhisperSTTProvider` (faster-whisper, `STT_PROVIDER=local_whisper`); default `SimulatedSTTProvider` (deterministic stand-in) | Streaming/GPU ASR only if latency requires |
| `TextToSpeechProvider`  | **Real:** `LocalPiperTTSProvider` (Piper, male/female English + Hindi voices, `TTS_PROVIDER=local_piper`); default `SimulatedTTSProvider` | - |
| `LanguageModelProvider` | `RuleBasedLanguageModelProvider` (keyword intent classifier) | Self-hosted/fine-tuned LLM |
| `TelephonyProvider`     | **Real:** `PlivoTelephonyProvider` (selected, locked provider - see "Real telephony"); `SimulatedTelephonyProvider` for tests/the simulated-call harness | Carrier no-answer forwarding to the Plivo number |
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

`WowAgent` also closes a real gap between the existing active-learning
review queue (`docs/SELF_LEARNING.md`, `FeedbackStatus.NEEDS_REVIEW`) and
live predictions: previously nothing in the running system ever populated
that queue - it was only exercised by `test_active_learning.py`'s manual
`FeedbackSubmission`s. `WowAgent` now takes an optional
`feedback_repository`; whenever `ConfidencePolicy.assess` reports
`needs_review=True` for a turn, it logs a `NEEDS_REVIEW` `FeedbackSubmission`
with the predicted intent/context/action and per-head confidence (so it
surfaces in `GET /feedback/review-queue` for a human to resolve via
`POST /feedback/{id}/respond`). This is best-effort and never on the
critical path: a repository failure is swallowed, not raised - a missed
review-queue entry is far cheaper than a failed call.

`ConversationState` (`app/agent/state.py`) is the explicit, serializable
session object every step reads and writes - session/user id, lifecycle
status (`CallLifecycleStatus`: created/ringing/connected/listening/
thinking/responding/ending/ended/processing/stored/expired), transcript,
intent/context/candidate action, memory results, tool results, policy
decision, confidence. It is never a hidden global: it is loaded from and
saved back to the existing `AgentState` table (as a JSON blob under key
`"conversation_state"`) on every turn.

The tool set (`app/agent/builtin_tools.py`) is deliberately small and real,
not a placeholder list: `save_memory` (backed by the existing `MemoryStore`),
`create_summary` (backed by `SummaryRepository`), and `set_context` (backed
by `ContextProfileRepository`, `app/agent/context_profile_repository.py` -
mirroring `StateRepository`'s ABC + SQL + in-memory-test-double pattern; a
predicted `SET_CONTEXT` action now really deactivates the previous active
`ContextProfile` row and activates/creates the new one, read back correctly
by the pre-existing `DefaultContextEngine`, proven end-to-end against a real
Postgres instance by `test_set_context_tool_writes_a_profile_default_context_engine_can_read`
in `backend/tests/test_integration_db.py`). Actions that still need a real
API-side effect that doesn't exist yet (`ANSWER_CALL`/`TRANSFER_CALL`/
`END_CALL` needing real telephony) are reported in the response payload
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

## Call recording (backend/app/agent/call_recorder.py)

`ConversationState` (above) is the agent's in-process working state, not
call history - it is not queryable as "show me last week's calls".
`CallRecorder` is the bridge: given a DB session, `start_call` creates the
`Call` + `Conversation` rows, `record_turn` appends a `TranscriptSegment`
per utterance, and `end_call` marks both `COMPLETED` and writes a
`Summary`. It is optional and orchestration-agnostic - `WowAgent`/`WowBrain`
never depend on it directly. `run_simulated_call` (see below) accepts an
optional `recorder`: when given, it mints the real `call_id`/
`conversation_id` from the database instead of a random one, so a
simulated call produces genuine, queryable call history end to end - the
same code path a real telephony integration would drive.

## Call retention (backend/app/learning/call_retention.py)

`CallRetentionPolicy` (default `CALL_RETENTION_DAYS=15`) and
`cleanup_expired_calls` delete a COMPLETED call's full history - its
`Conversation`(s), `TranscriptSegment`s, `Summary`, and working
`AgentState` - once `ended_at` is older than the retention window.
ACTIVE/RINGING/MISSED/VOICEMAIL calls are never touched regardless of age.
There is no `ON DELETE CASCADE` at the DB level (Phase 1 has no Alembic
migrations - see README "Current limitations"), so child rows are deleted
explicitly, in dependency order, before their parent `Call`. No scheduler
is wired into the app itself (no Celery/APScheduler dependency was
introduced, per docs "Do not overengineer prematurely") - run
`python -m app.learning.run_call_retention_cleanup` via an external
cron/task scheduler, the same human/externally-triggered pattern
`docs/KAGGLE_TRAINING.md`'s training commands already use.

## Backend request flow

`POST /brain/command` (see `app/api/routes/brain.py`) is the single entry
point Phase 1 needs: it takes `{user_id, text, caller_number?}`, wires up a
request-scoped `WowBrain` via `app/api/deps.py`, and returns the resulting
`AgentAction`. This is what the Android app calls today, and what a real
in-call audio pipeline will call once STT is wired up.

## Mobile app (mobile/)

Flutter/Dart UI, Kotlin native shell (`MainActivity.kt`). Phase 6-8 (see
`docs/implementation-status.md` for the last round this file was kept in
sync with) added real telephony permissions, a real `CallScreeningService`
(`WowCallScreeningService.kt`)/`TelecomManager` auto-answer path
(`WowAutoAnswer.kt`), real activation durations
(`POST /users/{id}/activation`), real call history, and a real voice
round trip (`POST /brain/voice-command`, `app/media/pipeline.py`) - this
section is stale about what Phase 1 originally planned; see those files
directly for current behavior. **Note (2026-09-17): this doc and
`implementation-status.md`/README's status badge were not updated during
Phases 3-8 despite substantial real work landing in git history over that
span - read the code/tests, not the "Phase 1" framing above, as the
source of truth for what's actually built.**

## Real telephony (investigated 2026-09-17, implemented 2026-09-17)

Everything upstream of `TelephonyProvider` is real and tested end to end:
`WebRtcVoiceActivityDetector` -> `LocalWhisperSTTProvider` -> `WowAgent`
(WOW Brain v3) -> `LocalPiperTTSProvider`, wired together by
`MediaPipeline` (`app/media/pipeline.py`) and proven against real audio
fixtures (`test_media_pipeline.py`).

**`TelephonyProvider` now has a second, real implementation**:
`PlivoTelephonyProvider` (`app/providers/telephony/plivo.py`), bridging
Plivo's Audio Streaming product (verified against Plivo's official docs,
not assumed - see "Provider research" below for the exact findings) onto
this project's existing PCM16/16kHz convention. Two new routes
(`app/api/routes/telephony_plivo.py`) implement Plivo's own two-step
model: `POST /telephony/plivo/answer` (Plivo's Answer URL webhook -
returns PLIVOXML starting a bidirectional `<Stream>`) and
`WS /telephony/plivo/stream` (the actual bidirectional media bridge:
inbound mu-law/8kHz -> `app/media/audio_codec.py` -> PCM16/16kHz ->
`MediaPipeline.stream_call_audio()` -> real STT/Brain v3/Agent Core/Piper
-> `audio_codec.py` -> mu-law/8kHz -> Plivo -> caller). `CallRecorder`
writes real `Call`/`Conversation`/`TranscriptSegment`/`Summary` rows
around the bridge, and `app/observability/notifications.py` logs a real
"WOW handled a call" line at call end - see docs/PLIVO_TESTING.md for the
full real-device test procedure and exactly what remains unverified
(Plivo's exact inbound JSON nesting, `end_call`'s effect on the
underlying PSTN call) until a real call proves it.

`SimulatedTelephonyProvider` is untouched and remains the deterministic
test double `app/simulation/call_simulator.py` uses.

**Why Android can't be that real implementation.** `WowCallScreeningService`
(the real `CallScreeningService`) and `WowAutoAnswer`
(`TelecomManager.acceptRingingCall()`) already detect and auto-answer a
real GSM call on a physical device - confirmed live, not simulated. But
`MediaRecorder.AudioSource.VOICE_CALL` (the only way to read/inject a live
cellular call's audio) is OS-restricted to privileged/carrier apps; no
normal third-party app, including this one, can be granted it. This is a
platform ceiling, not a missing feature - see `WowCallScreeningService.kt`'s
own class doc.

**Real architecture, as implemented** (for the first PC-hosted test - see
docs/PLIVO_TESTING.md; production hosting is a separate, not-yet-made
decision - see docs/DEPLOYMENT.md):

```
Caller dials the real Plivo India number directly (see "Provider
research" below for why this is a separate number, not carrier
forwarding of the physical SIM, for this first milestone)
   -> Plivo POSTs to POST /telephony/plivo/answer
   -> PLIVOXML response opens a bidirectional Stream WebSocket
   -> WS /telephony/plivo/stream -> PlivoTelephonyProvider
      (mu-law/8kHz <-> PCM16/16kHz, app/media/audio_codec.py)
   -> MediaPipeline.stream_call_audio() (added 2026-09-17: yields each
      reply the moment VAD confirms a turn ended, not only once the whole
      call ends - process_call_audio's batch shape, used by
      /brain/voice-command today, cannot serve a live, open-ended call)
   -> real STT (faster-whisper) -> WowAgent (WOW Brain v3, Agent Core)
   -> real TTS (Piper, female voice) -> PlivoTelephonyProvider -> Plivo
   -> caller hears it
```

**Phase 1 hardening of this path (2026-10-01; code-tested, not live-tested):**
`POST /telephony/plivo/answer` verifies `X-Plivo-Signature-V3` (fails closed
without `PLIVO_AUTH_TOKEN`; the signed URL is rebuilt from `PUBLIC_BASE_URL`
behind a tunnel), applies the activation gate, and mints a short-lived
single-use token bound to the `CallUUID` that it places in the Stream URL;
`WS /telephony/plivo/stream` is refused before `accept()` unless it presents
that token, then cross-checks the `start` event's call id, caps concurrent
streams and call duration, survives a failed turn (STT/Brain/TTS error) and
always runs cleanup. Full detail and the explicit list of what is deferred:
`docs/SECURITY.md`. Plivo's public docs do not publish verbatim JSON for the
inbound `start`/`media` events; the parser is tolerant and the first real call
is what confirms the shape (`docs/PLIVO_TESTING.md`).

`CallRecorder` wraps the whole call (real `Call`/`Conversation`/
`TranscriptSegment`/`Summary` rows); `app/observability/notifications.py`
logs a real notification at the end. Carrier no-answer call-forwarding of
the user's actual physical SIM number to this Plivo number (so a caller
dialing the real number gets bridged in when unanswered) is real future
work, not needed for this first milestone, which calls the Plivo number
directly - Android's own role (`WowCallScreeningService`/`WowAutoAnswer`)
is unaffected either way; it never becomes the audio path.

**Provider research - HISTORICAL** (kept only to record why Plivo was
chosen over Twilio/Exotel; the decision is final: **Plivo is the selected,
locked telephony provider** and no custom telephony bridge - Asterisk,
FreeSWITCH, Kamailio, OpenSIPS, RTPengine, a custom SIP server or a
GSM/SIM gateway - is planned or to be introduced):

- **Twilio** was ruled out for this specific use: its own live India
  voice-pricing page (checked directly, not from memory) marks inbound
  ("to receive calls") as unsupported for both Local and Mobile Indian
  number types - only browser/SIP-app numbers can receive there. A Twilio
  number cannot be the forwarding target this architecture needs.
- **Exotel** is India-licensed, explicitly supports inbound PSTN + a
  real-time bidirectional Voicebot Applet (WebSocket), but publishes no
  self-serve pricing - it's a "book a demo" enterprise product.
- **Plivo** (chosen): real self-serve India numbers (₹200/mo, verified on
  `plivo.com/voice/pricing/in/`), real inbound PSTN support, a dedicated
  Audio Streaming product with documented true bidirectional WebSocket
  audio (mu-law 8kHz), a ₹1,000 no-card-required trial credit, and no
  minimum monthly commitment - see docs/PLIVO_TESTING.md for the full
  verified quotes/URLs. India KYC (Udyam MSME registration, or GST/COI)
  is required before renting any Indian number from any legitimate
  provider - this is Indian telecom law (DoT), not Plivo- or
  Exotel-specific gatekeeping, and Udyam registration itself is free and
  self-serve.
- Render's free web-service plan (what production runs on today) spins
  down after 15 minutes of no inbound traffic (confirmed in Render's own
  docs) - a real always-on call assistant cannot tolerate that cold start
  in addition to the already-documented RAM ceiling (see
  `docs/DEPLOYMENT.md`). Render's own pricing page (checked live) puts the
  realistic minimum paid tier for Brain v3 + Whisper + Piper together at
  the $25/mo "Standard" plan (2GB RAM); $7/mo "Starter" (512MB) repeats
  the same OOM ceiling already hit once in production. This is why the
  first real test runs on a local PC (behind a Cloudflare Tunnel/ngrok)
  instead - no Render upgrade has been made.

## Multilingual conversation (2026-09-17)

Real per-turn Hindi/Hinglish/English detection and response, layered
entirely around Brain v3/`RuleBasedLanguageModelProvider` without
modifying either: `app/agent/language_detection.py` (script detection +
faster-whisper's own real acoustic signal, newly surfaced via
`TranscriptionResult.language`/`.language_probability` + a bounded
Hindi-in-Latin-script lexicon) runs on the already-transcribed text
inside `MediaPipeline._finalize_turn`, and the result flows into
`AgentRuntime.handle_input(language=...)` (new optional parameter) and
`app/agent/response.py`'s `generate_response(language=...)` for reply
selection, and `app/media/voice_selection.resolve_voice_for_language`
for per-turn female-voice selection. Detection is per-turn, not
call-wide, so a caller switching languages mid-call is genuinely
followed. Full detail, the real Urdu-script edge case found and fixed
during testing, measured latency, and honest limitations (this is a
curated multilingual phrase bank, not free generation) are in
`docs/implementation-status.md`'s "Context-instruction execution +
multilingual conversation" entry.

Same round: `app/agent/user_instructions.py` closes a real gap the prior
round's own review flagged - the caller's literal context instructions
now actually change `WowAgent`'s conversational replies (see
`app/agent/response.py`'s `_compose_contextual_reply`), not just sit
stored in `ContextProfile.user_instructions` unused.
