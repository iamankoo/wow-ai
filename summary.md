# WOW AI — Complete Project Summary

> **Purpose of this file.** A continuity document: a new developer or coding
> agent given only the Git repository (plus `Phases.md`, see the warning
> below) should be able to understand what WOW AI is, what exists, what has
> been *proven* versus only *tested in simulation*, and exactly where to
> continue. It is historical + technical + operational. It is generated from
> the repository, its documentation, its git history and its tests — nothing
> here is invented. Where the repository has no record, this file says
> **NOT VERIFIED**, **NOT IMPLEMENTED** or **BLOCKED**.
>
> **Status vocabulary:** IMPLEMENTED (code exists + automated tests) ·
> PROVEN LIVE (exercised for real on real hardware/network) · NOT VERIFIED ·
> NOT IMPLEMENTED · BLOCKED.
>
> 📍 **Where we stopped (2026-10-02):** see **"End-of-Day Checkpoint — 2026-10-02"** and
> **"NEXT SESSION — CONTINUE FROM HERE"** near the end of this file (before §29).
> **CONTINUE FROM PLIVO KYC / PHONE NUMBER SETUP.**
>
> ⚠️ **`Phases.md` is NOT in this repository.** The instructions that asked for
> this file refer to a `Phases.md`, but no such file exists in `wow-ai`
> (`git ls-files` has none; searching the machine found copies only in
> *other* projects, which were deliberately not read). Everything this file
> says about the "master roadmap" (Phases 1–5) comes from the project owner's
> written instructions, not from a file. **Obtain the real `Phases.md` from the
> project owner and reconcile it with §24 before starting any new phase.**

---

## 1. Project Identity

| | |
|---|---|
| Name | WOW AI |
| Repository | https://github.com/iamankoo/wow-ai (branch `main`) |
| Owner / Git identity | `iamankoo <aniketraj00384@gmail.com>` |
| Product purpose | A self-hosted personal AI call assistant: answers phone calls on the owner's behalf when unavailable, identifies the caller, loads the owner's current context, converses with the caller in English / Hindi / Hinglish, and gives the owner a transcript and summary afterwards (README §1–2). |
| Core vision | A phone owner delegates "answer this call for me". The assistant knows who is calling, what context the owner is in (busy, sleeping, travelling, meeting, custom), converses in the caller's language, takes the right action (take a message, mark urgent, …) and reports back. |
| Hard architectural stance | **No hosted third-party AI API** (no OpenAI/Claude/Gemini/etc.). Every capability sits behind an abstract provider interface (`backend/app/interfaces/`) with self-hosted implementations (faster-whisper, Piper, a self-trained classifier, pgvector). Telephony is the one external service: **Plivo** (§12). |
| Target users | A single owner (personal use, single-tenant) today. |
| **Individual WOW** | The personal-assistant mode. Partly implemented (§4). |
| **Business WOW** | An AI voice agent for businesses. **NOT IMPLEMENTED.** No code, no schema, no spec exists in the repository (grep for "business" finds only the `BUSINESS_CONTACT` caller-relationship enum and a roadmap line). Its requirements below come only from the owner's instructions. |

## 2. Original Product Vision

What WOW was *intended* to do (sources: README §2, commit messages that quote
the product requirements, owner instructions). Implementation status of each is
in §4 — do not read this section as a list of features that exist.

- **Personal AI call representative** — answers calls for the owner.
- **Business AI voice agent** — separate, later mode (Phase 4 in the roadmap).
- **Manual WOW activation** — WOW must **never** activate itself; the owner
  turns it on, with a duration.
- **Activation durations** — exactly: 15 minutes, 1 hour, 5 hours, "Until I stop".
- **Current user context** — a named profile (BUSY, SLEEPING, MEETING,
  TRAVELLING, UNAVAILABLE, CUSTOM, NORMAL) that shapes how calls are handled.
- **Incoming-call behaviour** — identify the caller, apply context, converse,
  take a message / mark urgent / escalate.
- **Human-first behaviour** — give the human a short window to answer
  themselves before WOW takes the call (originally "~10 seconds" in Phase 2
  Block 7; later changed to "~5 seconds" to match the written spec — see §9).
- **Natural conversation** — the owner's requirement is genuinely natural,
  free-form conversation. **The current system does not satisfy this** (§6, §25).
- **Hindi / Hinglish / English** — including switching languages mid-call.
- **Female / male voice** — user-selectable, female the default.
- **Memory / context** — remembered facts with trust levels (§14).
- **Call summaries and notifications** — a summary per call; a notification when
  WOW handles a call.
- **Self-learning** — improves from real usage, but only through a gated,
  human-approved, offline pipeline (§7); never live weight updates.

## 3. Locked Product Requirements

Recorded as stated by the project owner / found as hard rules in the code. Do not
reinterpret.

1. **Telephony is locked to Plivo.** Never introduce Asterisk, FreeSWITCH,
   Kamailio, OpenSIPS, RTPengine, a custom SIP server, a custom PSTN gateway, a
   GSM/SIM gateway or any other telephony provider unless the owner explicitly
   changes this.
2. **WOW is OFF by default** and must never activate itself
   (`User.call_assistant_enabled` defaults to `False`).
3. **Activation durations are exactly 15m / 1h / 5h / until_stop** (plus "off").
4. **Human-first window of ~5 seconds** where the architecture supports it
   (Android auto-answer path only — §9).
5. **18+ only**, enforced server-side.
6. **Languages:** English, Hindi, Hinglish; **voices:** female (default) and male.
7. **No hosted AI API** for STT/TTS/reasoning.
8. **Brain v3 is frozen** — do not modify it unless explicitly authorized.
9. **Self-learning is offline and human-gated**; no live weight updates; training
   consent is opt-in and defaults to off.
10. **Do not fake functionality.** A feature that cannot genuinely work is
    documented as a limitation, not simulated (this principle appears throughout
    the commit history).
11. **Roadmap order is locked** (Phases 1→5, §24); do not skip phases.
12. **Git rules:** commits/pushes only as `iamankoo <aniketraj00384@gmail.com>`;
    **no** Claude/Anthropic attribution, **no** `Co-Authored-By`, **no**
    session trailers; do **not** create GitHub Releases or tags unless asked.
13. **Never expose credentials** in code, commits, logs, screenshots or reports.

## 4. Product Modes

### Individual mode — intended vs implemented

| Capability | Status |
|---|---|
| Onboarding (name, mobile, email, DOB, language/voice) | IMPLEMENTED, device-tested (Phase 6) |
| Mobile + email verification (OTP) | IMPLEMENTED; **production exposes the OTP to the client** (`OTP_EXPOSE_DEV_CODE=true`, no real SMS/email provider) |
| 18+ check | IMPLEMENTED server-side |
| WOW activation with the four durations + lazy expiry | IMPLEMENTED, tested |
| Floating WOW button (Android overlay) | IMPLEMENTED (Phase 6) |
| Text command / voice command to the backend | IMPLEMENTED; real speech needs real STT (not on Render) |
| Call history, summaries, "today" summary | IMPLEMENTED |
| Notification when WOW auto-answers | IMPLEMENTED (Phase 8) |
| Privacy / permissions / consent screen | IMPLEMENTED; no widget test, not device-tested after Phase 1 |
| In-app updater (GitHub Releases) | IMPLEMENTED (v1.0.0 → v1.2.0 released) |
| Auto-answer a real GSM call (human-first window) | PROVEN LIVE on emulator and a physical device (answers + window), but **WOW cannot hear or speak on a cellular call** (§9) |
| Real two-way caller conversation | IMPLEMENTED for **Plivo calls only**; **NOT VERIFIED on a real call** (§12, §23) |
| Carrier no-answer forwarding to the Plivo number | **NOT IMPLEMENTED** (carrier/phone configuration; nothing in the repo) |
| Free-form natural conversation | **NOT IMPLEMENTED** (§6) |

### Business mode — NOT IMPLEMENTED

Intended (owner's roadmap, Phase 4 "Business WOW + Scale"): multi-tenant
business voice agent, concurrent calls at scale. **The concurrency target is not
recorded anywhere in the repository — NOT VERIFIED / unknown.** Today's code is
single-tenant by construction: one Plivo number → one hard-coded user
(`Settings.demo_user_id = 00000000-0000-0000-0000-000000000001`), a process-wide
in-memory stream-token store, `PLIVO_MAX_CONCURRENT_STREAMS=2`, no accounts, no
tenant isolation, one backend process. Business mode needs per-tenant numbers
and routing, accounts/authorization, a shared token store, scale-out and a
capacity plan.

## 5. Complete Architecture

### 5.1 Monorepo layout
```
backend/    FastAPI app (app/), Alembic (migrations/), tests/, Dockerfile
mobile/     Flutter app + Android native Kotlin (android/app/src/main/kotlin/com/wowai/app)
training/   datasets, training pipeline, evaluation, model configs (models/ is git-ignored)
docs/       ARCHITECTURE, DEPLOYMENT, RUNNING, SECURITY, PLIVO_TESTING, TRAINING, DATASET, SELF_LEARNING, KAGGLE_TRAINING, MODEL_ARCHITECTURE, implementation-status
render.yaml docker-compose.yml .env.example summary.md README.md
```

### 5.2 Request/call flows
- **App → backend (REST):** Flutter `WowApiClient` → FastAPI routes. `X-WOW-API-Key`
  is required when `API_ACCESS_KEY` is configured (§15).
- **Voice command from the phone:** raw PCM16 → `POST /brain/voice-command` →
  `MediaPipeline` (VAD → STT → agent → TTS) → transcript + reply + base64 audio.
- **Real GSM call (Android):** `WowCallScreeningService` (Telecom binds it per
  call) reports metadata to `/brain/command`, starts the human-first timer;
  `WowAutoAnswer` calls `TelecomManager.acceptRingingCall()` if the backend says
  WOW is on. **No audio** is available to the app (§9).
- **Plivo call:** caller → Plivo number → `POST /telephony/plivo/answer`
  (signature + activation gate + token) → bidirectional `WS /telephony/plivo/stream`
  → mu-law/8 kHz ⇄ PCM16/16 kHz → `MediaPipeline.stream_call_audio` → Whisper →
  language detection → WowAgent (Brain) → Piper → Plivo → caller; `CallRecorder`
  persists everything (§12).

### 5.3 Components and responsibilities

| Area | Where | Notes |
|---|---|---|
| Provider interfaces | `backend/app/interfaces/` | `LanguageModelProvider`, `SpeechToTextProvider`, `TextToSpeechProvider`, `VoiceActivityDetector`, `TelephonyProvider`, `MemoryStore`, `ContextEngine`, `AgentRuntime`, `OtpDeliveryProvider`, `PrivacyFilter`/feedback |
| LLM/Brain providers | `app/providers/llm/` | `RuleBasedLanguageModelProvider` (default), `LocalWOWModelProvider` (`MODEL_PROVIDER=local_wow`, Brain v3) |
| Agent runtimes | `app/brain/wow_brain.py` (v0 straight-line, default), `app/agent/orchestrator.py` `WowAgent` (opt-in `AGENT_RUNTIME=wow_agent`) | WowAgent = explicit state, confidence-gated policy, tool registry, multi-turn clarification |
| STT | `providers/stt/local_whisper.py` (faster-whisper), `simulated.py` | `WHISPER_MODEL_SIZE` default `base` |
| TTS | `providers/tts/local_piper.py` (Piper), `simulated.py` | voices in §13 |
| VAD | `providers/vad/webrtc_vad.py` (WebRTC VAD via `webrtcvad-wheels`) | events SPEECH_START/END, SILENCE, BARGE_IN |
| Media pipeline | `app/media/pipeline.py` | `process_call_audio`, `stream_call_audio`, `synthesize_reply`, per-turn failure tolerance |
| Audio codec | `app/media/audio_codec.py` | pure-Python G.711 mu-law + linear resampler |
| Telephony | `providers/telephony/plivo.py`, `plivo_signature.py`, `stream_tokens.py`; `api/routes/telephony_plivo.py` | §12 |
| Memory | `providers/memory/pgvector_store.py` | typed memories + trust tiers (OBSERVED/INFERRED/CONFIRMED/USER_APPROVED); embeddings are **not real** (see limits) |
| Context | `brain/context_engine.py`, `agent/context_profile_repository.py`, `models/context.py` | §14 |
| Call recording | `agent/call_recorder.py` | Call, Conversation, TranscriptSegment, Summary |
| Observability | `app/observability/` | per-stage latency, PII-safe logging, call-handled notification (a **log line**, not a push) |
| Learning | `app/learning/` | §7 |
| Security | `app/security.py` | §15 |
| Android native | `WowCallScreeningService`, `WowAutoAnswer`, `CallStateObserver`, `NotificationHelper`, `WowFloatingButtonService`, `VoiceRecorder`/`VoicePlayer`, `MainActivity` (MethodChannels: permissions, overlay, update, notifications) | §9 |
| Flutter | `mobile/lib/` (core, features: onboarding, home, history, profile, settings, privacy, splash) | §10 |
| Redis | configured (`REDIS_URL`), **not used by any application code** | NOT IMPLEMENTED |
| Deployment | `render.yaml`, `backend/Dockerfile` | §11, §18 |

### 5.4 REST API (all behind the API key except `/health` and the Plivo routes)
`/users` (create, get, patch profile, `/activation`, `/verify/{channel}/request|confirm`),
`/users/{id}/calls`, `/users/{id}/calls/today-summary`, `/calls/{id}`,
`/brain/command`, `/brain/voice-command`, `/contacts`, `/memories`,
`/feedback/*` (submit, review-queue, respond, approve, export, used-for-training,
consent, delete, reset-personalization), `/health`;
Plivo: `POST /telephony/plivo/answer`, `WS /telephony/plivo/stream`.

### 5.5 Taxonomy (`backend/app/brain/taxonomy.py`)
17 intents, 7 context modes (SLEEPING, BUSY, MEETING, TRAVELLING, UNAVAILABLE,
CUSTOM, NORMAL), 13 actions (ENABLE/DISABLE_CALL_ASSISTANT, SET/CLEAR_CONTEXT,
ANSWER_CALL, ASK_CALLER_REASON, COLLECT_MESSAGE, MARK_URGENT, TRANSFER_CALL,
END_CALL, SAVE_MEMORY, CREATE_SUMMARY, NO_ACTION).

## 6. WOW Brain History

**What the Brain is — stated plainly.** The WOW Brain is a **structured-decision
classifier**: three independent fine-tuned text-classification heads (intent,
context mode, action) over a multilingual encoder. It outputs *labels with
confidences*. It does **not** generate free-form text. `LocalWOWModelProvider.generate()`
returns `content=""` and the structured prediction. **Every reply the caller hears
comes from deterministic, bounded templates** (`backend/app/agent/response.py`) —
a richer template layer than before (per-language phrase banks, active-context
composer, parsed owner instructions) but still templates. **Free-form generative
conversation is NOT IMPLEMENTED.** (Verified in code this phase; repeated in §25.)

| Version | Base model | Data | Result / note |
|---|---|---|---|
| v0 | `prajjwal1/bert-tiny` (~4.4M) | 117-example seed (99/18) | Smoke test. Intent 16.7%, action 16.7%; worse than the rule baseline; mode collapse (100% → SET_CONTEXT). English-only vocabulary. |
| v1 | `distilbert-base-multilingual-cased` (~135M) | 724-record unified set (dataset v2.0.0; 615 train intent/action, 94 context) | Intent 71.6%, context 50.0% (n=20), action 70.6% on a 109-example val set; no collapse; Hinglish strongest (88.9%). UNKNOWN accuracy weak (20%, n=5). |
| v1.1 | same | dataset v2.1.0 (866 examples) prepared & validated | **Never trained** (no `v1.1` artifact directory). |
| v2 | same | 33,000 hand-annotated (`v3.2.0-train-ready`: 26,140/3,378/3,482) | Trained; exposed a real gap: **zero `ANSWER_CALL` examples**. (Per-metric results are in `docs/TRAINING.md`; not restated here — NOT VERIFIED in this document.) |
| **v3** | same | **`v3.3.0-answer-call`, 66,000 examples** (train 52,514 / val 6,701 / test 6,785); +30,000 ANSWER_CALL (10,000 each English/Hindi/Hinglish), +3,000 hard negatives, 33,000 carried from v2 | Trained on Kaggle (2× Tesla T4), `epochs≤20`, early stopping patience 4, class-weighted. **Frozen.** |

**v3 held-out test (frozen `test.jsonl`, 6,785; checksum-verified unmodified;
`training/evaluation/v3_test_report.json`):** intent **94.15%**, context
**90.86%** (n=6,466), action **95.30%**, structured-output validity 100%,
ambiguous/unknown 96.00% (n=125). Per-language intent: Hindi 94.56%, Hinglish
93.76%, English 94.13%. Rule-based baseline on the same split: intent 5.13%.
Early-stopping validation: intent 94.54% best / 94.27% deployed (the saved intent
weights are the *last* epoch, 16 — see implementation-status §4), context 91.62%,
action 95.61%.

**Kaggle training and recovery.** A first Kaggle pass (reported ~93.66/89.62/95.49)
was **lost** — session persistence was off and nothing was saved. The owner had the
repo **retrain** (notebook `iamankoo/notebook914fc30194`, persistence "Variables and
Files"). A real bug appeared on resume (`RNG state must be a torch.ByteTensor`,
torch/numpy mismatch) and was fixed by making RNG restoration best-effort
(commit `6771af5`); one container restart mid-run was survived thanks to per-epoch
checkpoints. The recovered artifacts were verified (byte-for-byte transfer, each
head loads and forwards, `LocalWOWModelProvider` classifies English and Hinglish
locally).

**Artifacts.** `training/models/wow-brain/{v0,v1,v2,v3,v3_pre_kaggle_backup}` —
**git-ignored** (v3 ≈ 1.56 GB: 3 heads × ~520 MB). They exist only on the
developer's PC. Datasets (`training/datasets/versions/`), raw corpora and
`kaggle-upload/` are also git-ignored.

**Integration today.** `MODEL_PROVIDER=local_wow` + `WOW_MODEL_DIR=training/models/wow-brain/v3`
+ `AGENT_RUNTIME=wow_agent` runs Brain v3 inside the real pipeline (proven by
tests and the Phase 1 rehearsal, §19). **Default remains `rule_based`**; promoting
v3 to default is a pending product decision. **Production (Render) cannot run it**
(§11).

**Limitations.** Classifier only; three forward passes per request (≈0.2–2 s on
the developer CPU); mixed precision and a shared-trunk redesign not built;
UNKNOWN/ambiguous handling modest; held-out numbers are on the project's own
(partly synthetic, template-generated) dataset, **not** on real recorded calls.

## 7. Self-Learning Architecture

```
real call → transcript → privacy filter → [consent gate] → CANDIDATE
 → human approval (named reviewer) → dataset batch (INCLUDED)
 → human-run dataset version build → train.py → evaluate.py
 → PromotionManager (regression-blocking gate) → ModelRegistry CANARY → PRODUCTION / REJECTED
```
**IMPLEMENTED and unit/integration-tested (offline):** per-user training consent
(opt-in, default off; stored in `User.training_data_consent`), retention check,
regex PII redaction (`RegexPrivacyFilter`: email, phone, card-like, OTP/PIN —
defense-in-depth, no NER), active-learning review queue fed by low-confidence agent
predictions, human approval, `TrainingCandidateBuilder`, dataset versioning with
SHA-256 manifests, model registry, promotion gate (any intent regression or mode
collapse blocks), failure mining, data-subject endpoints (export, delete,
disable-consent, reset personalization), call retention cleanup
(`python -m app.learning.run_call_retention_cleanup`, **run externally — no
scheduler**).
**NOT IMPLEMENTED / future:** live canary traffic routing between model versions;
automatic chaining of build→train→evaluate→promote (deliberately human-run);
**no real call has ever flowed into this pipeline** — it has been exercised only
with test data; live weight updates (deliberately never).

## 8. Phase History

**Naming warning.** The git history uses *historical* labels — "Agent Core Block
1–4", "Phase 2 Blocks 1–7", "Phase 5", "Phase 6 Parts A–U", "Phase 7", "Phase 8" —
that predate and are **not the same as** the locked *master roadmap* "Phase 1–5"
(§24). Historical labels are used in §8–§13; roadmap phases in §22–§24. The
historical label "Phase 5" (one commit) and the roadmap "Phase 5" (Final
Production & Launch Gate) are unrelated.

| # | Date | Work | Commits | Status |
|---|---|---|---|---|
| 0 | 2026-09-01 | Initial baseline: FastAPI + SQLAlchemy + Postgres/pgvector + Redis config, 9 domain models, provider interfaces, rule-based provider, `LocalWOWModelProvider`, `PgVectorMemoryStore`, `WowBrain` v0, self-learning scaffolding, v3 dataset, Android app shell | `5e8e75b` | complete |
| 0b | 09-03 | Opt-in `WowAgent` (state/policy/tools), memory safety tiers + `/memories`, deterministic simulators + simulated-call harness, observability, `CallRecorder`, active-learning queue, retention cleanup | `01cfb0d`…`bcb7de5` | complete |
| 0c | 09-03 | v3 artifact-loss recovery attempt, Kaggle retrain, RNG fix, held-out evaluation | `47fa6ce`,`6771af5`,`b770328`,`277d912` | complete |
| AC | 09-03 | **Agent Core Blocks 1–4**: `ContextProfile` write path + real `SET_CONTEXT`; remaining tools; genuine multi-turn clarification loop; full integration test with Brain v3 | `8ba57f8`…`c9e977b` | complete |
| 2 | 09-03 | **Phase 2 Blocks 1–7** (§9): Android build blocker, real STT, TTS, VAD, media pipeline, CallScreeningService, ANSWER_CALL | `7c123e9`…`1cee0a7` | complete |
| 5 | 09-03 | "Phase 5": live-verify `WowAutoAnswer` end to end (§9) | `d75044c` | complete |
| 6 | 09-03/04 | **Phase 6 Parts C–U** (§10): onboarding, verification, activation, profile/settings, call history, floating button, voice selection, updater (v1.0.0), voice commands | `3a3bec7`…`a6a7178` | complete |
| 7 | 09-04 | Render + Neon deployment (§11), version 1.1.0+2 | `4a659dc`…`2a2f471` | complete (limited) |
| 8 | 09-04 | Notification on auto-answer, malformed-ID 500 fix, physical-device fixes, real STT/TTS on Render attempted and **reverted after OOM**, version 1.2.0+3 | `c4b9dee`…`d9bcb08` | complete |
| P | 09-17 (in working tree, committed 10-01) | **Real telephony investigation → Plivo bridge**, safety review, signature validation, multilingual + context-instruction execution (§12–14) | in `3a0aa84` | implemented, **not live-validated** |
| **R1** | 10-01 | **Roadmap Phase 1 implementation** (§22): tree reconciliation, stream auth, API key, fail-closed webhook, Alembic, redaction, docs | `3a0aa84` | implementation COMPLETE |
| R1b | 10-01 | Live-validation **rehearsal** found/fixed 2 bugs (cross-session FK, token in logs) | `2e2e5dd` | complete |

Important discoveries are in each section. Note: `docs/implementation-status.md`
admits it was not kept in sync for Phases 3–8 of the historical numbering; the git
log is the authority for those.

## 9. Phase 2 Blocks / "Phase 5" — Voice Stack and Android Call Handling

(The owner's summary template calls this "Phase 5"; git calls it Phase 2 Blocks 1–7
plus the one-commit "Phase 5".)

- **Block 1:** AndroidManifest referenced a launcher icon that did not exist → build
  failed; fixed; debug APK built, installed and launched on the emulator
  (`Medium_Phone_API_36.1`).
- **Block 2 — `LocalWhisperSTTProvider` (faster-whisper):** lazy-imported; raw PCM16 mono;
  language auto-detect per utterance (no "Hinglish" mode in Whisper); `feed()` does not
  fabricate partials. Verified against real SAPI-synthesized fixtures (`hello.wav`,
  `meeting_context.wav`): transcribed exactly / punctuation-only difference. **Hindi
  and Hinglish accuracy NOT VERIFIED** (only English voices available then).
- **Block 3 — `LocalPiperTTSProvider`:** real ONNX synthesis, voices auto-downloaded to
  `~/.cache/wow-ai/piper-voices`, real streaming, Hindi voice verified audibly different.
- **Block 4 — VAD:** new interface + `WebRtcVoiceActivityDetector` (debounced; barge-in
  event). Found/fixed a real bug where one `feed()` dropped earlier events. Verified on
  real speech (start 0.12 s, end 3.15 s of 3.535 s).
- **Block 5 — `MediaPipeline`:** audio → VAD → STT → WowAgent(Brain v3) → TTS; proven with
  real fixtures end to end (SET_CONTEXT/MEETING reached from audio).
- **Block 6 — Android:** `WowCallScreeningService` (the OS binds it for every call once the
  app holds the CALL_SCREENING role; it allows the call and reports metadata to the
  backend), `CallStateObserver`, role/permission requests. Verified with `adb emu gsm call`.
  Found/fixed malformed-user-id crashes; made the demo user a real UUID.
- **Block 7 — ANSWER_CALL:** `WowAutoAnswer` uses `TelecomManager.acceptRingingCall()`
  (permitted for a normal app with `ANSWER_PHONE_CALLS`). A timer starts at RINGING and is
  cancelled if the human handles the call; on expiry it asks the backend whether WOW is
  enabled and answers only if so. **END_CALL** needs `MODIFY_PHONE_STATE` (privileged) and
  **TRANSFER_CALL** needs an `InCallService` Call object — both documented as platform
  limitations, **not faked**.
- **"Phase 5" (`d75044c`):** both branches live-verified on the emulator: left ringing →
  auto-answered after ~10.2 s and `dumpsys telecom` showed RINGING→ACTIVE; declined inside
  the window → WOW did nothing.
- **Phase 8 physical-device findings (Vivo, Android 13):** `onScreenCall` fired 3/3 but the
  `CallStateObserver` listener (in the app process) was killed in the background, so the
  timer never started → the timer is now also started from the screening service
  (`7d29ac9`). Emulator RINGING callbacks are unreliable.
- **Window length:** 10 s while verifying → set to **5 s** in the Plivo prep round to match
  the written spec. **The 5 s value has NOT been re-verified on a device.**
- **Core Android limitation (platform, not a bug):** a third-party app **cannot read or
  inject cellular call audio** (`AudioSource.VOICE_CALL` is privileged/carrier-only). So
  WOW can auto-answer a GSM call but **cannot converse on it**. This is *why* real
  conversation uses a separate Plivo number (§12).
- **Proven:** screening, answer, human-first window, notification, backend round trip.
  **Not possible:** audio on the cellular call, ending it, transferring it.

## 10. Historical Phase 6 — Onboarding … Updater

- **User model:** DOB, mobile/email verified flags, `personalization_completed`,
  `preferred_language`, `voice_gender`, computed `age`/`is_adult`/`profile_complete`.
- **Verification:** `OtpDeliveryProvider` interface + `VerificationService` (secrets-based
  code, SHA-256-hashed storage, expiry, attempt limits). Only a logging provider exists;
  the dev code is returned to the client (labelled dev). **No real SMS/email delivery.**
- **Onboarding (5 steps)** driven by the real backend row, never a local flag; permissions
  via a MethodChannel with real per-permission status.
- **Activation:** `POST /users/{id}/activation` with `15m|1h|5h|until_stop|off`,
  `User.active_until`, **lazy** expiry (no scheduler): any read after expiry flips it off.
- **Profile / Settings screens:** only rows backed by real capability (no fake plan/
  password/devices rows).
- **Call history:** `GET /users/{id}/calls`, `/calls/{id}`, `/today-summary`; the
  `/brain/command` route records a real Call (no fabricated transcript).
- **Floating WOW:** real `TYPE_APPLICATION_OVERLAY` service, draggable; tap returns to the
  app (in-overlay voice capture not built).
- **Voice selection:** `app/media/voice_selection.py` maps language+gender to Piper voices.
- **Voice command:** `POST /brain/voice-command` + `chunk_pcm16` (needed so VAD surfaces
  every event).
- **Updater:** reads GitHub Releases for this repo, downloads the APK, installs via
  FileProvider; releases `v1.0.0`, `v1.1.0`, `v1.2.0` exist. Release signing uses the debug
  keystore (must not change — upgrade-in-place requirement, DEPLOYMENT.md).
- **Tests:** backend DB tests against real Postgres; Flutter widget tests (splash routing,
  onboarding, text command sheet, update checker).

## 11. Phase 7 / Render

- **Backend** on Render free plan from `render.yaml` (Docker), service
  `wow-ai-backend` at `https://wow-ai-backend-4h49.onrender.com`; `/health` check.
- **Database:** Neon free Postgres (Render allows one free DB per account and it was in use);
  `DATABASE_URL` set only in the Render dashboard (`sync: false`); startup enables the
  `vector` extension; `pool_pre_ping=True` because Neon closes idle connections (real
  `InterfaceError` seen live). The demo user row was seeded once by hand.
- **Mobile:** release builds → Render URL; debug builds → `http://10.0.2.2:8000`
  (override with `--dart-define=WOW_BACKEND_URL`); native Kotlin uses
  `BuildConfig.BACKEND_BASE_URL` per build type. Permissive CORS (`*`).
- **Production providers: zero-ML defaults** — `MODEL_PROVIDER=rule_based`,
  `STT_PROVIDER=simulated`, `TTS_PROVIDER=simulated`, `AGENT_RUNTIME=wow_brain`,
  `OTP_EXPOSE_DEV_CODE=true`, `CALL_RETENTION_DAYS=15`.
- **Why local Brain/Whisper/Piper do not run there (measured, not guessed):** free plan =
  512 MB RAM, no persistent disk, spins down after 15 min idle. Brain v3 weights alone are
  1.56 GB. Real STT (even `tiny`) **loaded at boot then OOM-crashed on the first real
  inference** (`d9bcb08`, `/health` itself died) → reverted. Realistic minimum for the full
  stack ≈ the $25/mo 2 GB tier (Render pricing as read at the time).
- **What remains for production hosting:** a plan with ≥2 GB RAM + persistent disk or model
  download step, always-on instance, model packaging (tar.gz on a GitHub release — described,
  not built), `API_ACCESS_KEY` + a mobile build that sends it, real OTP provider, scheduler for
  retention cleanup, secrets management.
- **State after Phase 1 push (observed 2026-10-01):** production is running the new code
  (unsigned Plivo webhook → 503); call-detail read returned 200, which indirectly shows the
  `transcript_segments.language` column exists, i.e. the Alembic migration applied on Neon.
  **Direct Neon inspection was not possible (no credentials here) — migration on Neon is
  inferred, NOT directly verified.** Production REST routes are still **unauthenticated**.

## 12. Plivo Architecture (historical "Phase 8" + roadmap Phase 1)

**Why Plivo.** Investigation (2026-09-17, docs read live): Twilio's India pricing page marks
inbound unsupported for Local/Mobile Indian numbers; Exotel supports inbound + bidirectional
streaming but is a "book a demo" enterprise product with no self-serve pricing; Plivo has
self-serve India numbers (₹200/mo as read), inbound PSTN, a documented bidirectional Audio
Streaming product (mu-law 8 kHz), a ₹1,000 no-card trial and no monthly commitment. India
needs KYC (Udyam/GST/COI) for any Indian number. A custom SIP/Asterisk/GSM bridge was
**rejected/locked out** by the owner. Plivo is final.

**Pieces (all in the repo; no credentials):**
- **Answer webhook** `POST /telephony/plivo/answer`: verifies `X-Plivo-Signature-V3`
  (HMAC-SHA256, constant time; fails closed); the signed URL is rebuilt from
  `PUBLIC_BASE_URL`; activation gate (`call_assistant_enabled`/`active_until`, lazy expiry) →
  `<Hangup/>` when off; no `CallUUID`, DB error, stream cap or full token store → `<Hangup/>`;
  otherwise returns PLIVOXML `<Stream bidirectional="true" contentType="audio/x-mulaw;rate=8000" keepCallAlive="true">wss://…/telephony/plivo/stream?token=…</Stream>`.
- **WebSocket** `WS /telephony/plivo/stream`: token validated and consumed **before accept**;
  start-event call id must equal the token's `CallUUID`; bounded audio queue (2000 frames);
  oversized/non-object/invalid frames dropped; `track: outbound` ignored; max concurrent
  streams and max call seconds; greeting "Hello." synthesized by Piper; per-turn recording;
  cleanup always runs (each step independently guarded).
- **Codec** `audio_codec.py`: G.711 mu-law (decode bit-exact vs `audioop`, encode within one
  quantization step) + linear resampler 8k⇄16k; pure Python (no `audioop`, removed in 3.13).
- **Pipeline:** mu-law/8k → PCM16/16k → VAD → faster-whisper → `detect_language` → WowAgent
  (Brain) → Piper → PCM → mu-law/8k → `playAudio`.
- **CallRecorder:** `Call`, `Conversation`, `TranscriptSegment`(+language), `Summary`; commits
  right after `start_call`, after each turn and after `end_call` (needed because the agent uses
  a different DB session — see below). Summary is a generic template line.
- **Public URL:** a Cloudflare quick tunnel (`cloudflared tunnel --url http://localhost:8000`);
  its hostname changes each run; `PUBLIC_BASE_URL` must match; Plivo's Answer URL must point at
  `<PUBLIC_BASE_URL>/telephony/plivo/answer` (POST).
- **Documented provider unknowns (NOT VERIFIED until a real call):** exact JSON of inbound
  `start`/`media` events (Plivo docs name fields but publish no sample; `extraHeaders` arrive
  in the start event, not the handshake); whether the `?token=` query string survives; whether
  closing the WebSocket hangs up the PSTN call (`end_call` only closes the socket).
- **Failure handling:** a failed STT/Brain/TTS turn is logged (type only) and skipped; 3
  consecutive failures end the call; receive-loop errors, `start_call` failure and history
  failures never skip socket cleanup.
- **Real bug found by the rehearsal (fixed `2e2e5dd`):** conversation row was committed only
  at call end while WowAgent writes `agent_states`/`feedback_events` (FK → conversations)
  through a separate session → ForeignKeyViolation on turn 1 on Postgres; SQLite tests could
  not see it. Regression test needs Postgres.

## 13. Multilingual System

- **Languages:** English (`en`), Hindi (`hi`), Hinglish (`hi-Latn`, Hindi in Latin script).
- **Per-turn detection** (`app/agent/language_detection.py`, ~0 ms): (1) real script detection
  (Devanagari; Perso-Arabic/Urdu script also resolves to Hindi — found live when Whisper
  rendered synthesized Hindi that way), (2) faster-whisper's own acoustic language id +
  probability (`TranscriptionResult.language`), (3) a bounded Hindi function-word lexicon for
  Latin-script text. Detection is per turn, so switching mid-call is followed.
- **Response:** `generate_response(language=…)` selects per-language/per-context phrase banks
  (templates, not generation); `None` language is byte-identical to before (regression-tested).
- **Voices:** English F/M `en_US-hfc_female-medium` / `en_US-hfc_male-medium`; Hindi F/M
  `hi_IN-priyamvada-medium` / `hi_IN-pratham-medium` (gender inferred from Hindi given names —
  Piper has no gender field); **Hinglish reuses the Hindi voices** (no distinct Hinglish voice;
  Piper's Hindi voice on Latin-script text is expected to be poor — not evaluated). Per-turn voice
  follows the detected language and the user's gender (`resolve_voice_for_language`).
- **Tests actually performed:** unit tests of detection; full-bridge test with a Piper-synthesized
  Hindi utterance then English fixture (real Whisper/Piper through the bridge, fake WebSocket);
  Phase 1 rehearsal: English, Hindi (synthesized), English again through a real server/socket.
  **Not performed:** any real human Hindi or Hinglish speech; any Hinglish audio at all; any real
  phone call.
- **Latency (rehearsal, developer PC CPU):** STT 1.8–2.8 s, language detection ≈0, agent
  0.2–2.0 s, TTS 0.3–0.8 s (3.1 s first Hindi voice load) → English turn 2.4–3.9 s, first Hindi
  turn 7.9 s. Conversationally slow; no optimisation done (not Phase 1 scope).

## 14. Context and User Instructions

- **`ContextProfile`** (`models/context.py`): per-user, optional per-contact; `name`, `instructions`
  (the fixed per-mode description that drives policy/templates), `is_active`, and
  **`user_instructions`** (nullable `Text`) = the owner's literal words (e.g. "ask why they called,
  take a message, only mark it urgent if necessary").
- **Tools:** `SET_CONTEXT` writes a profile (and captures the literal instructions; blank = none);
  `CLEAR_CONTEXT` deactivates; `ENABLE/DISABLE_CALL_ASSISTANT`, `SAVE_MEMORY`, `COLLECT_MESSAGE`,
  `MARK_URGENT`, `CREATE_SUMMARY` are real tools. `pending_action` stores the original turn text so
  a confirmed action ("yes") keeps the real words.
- **How instructions influence behaviour today:** `parse_user_instructions()` extracts four booleans by
  regex (`ask_caller_reason`, `take_message`, `mark_urgent_only_if_necessary`, `do_not_disturb`);
  `generate_response` composes a context-aware **template** reply. Proven: the same caller turn yields
  a different reply depending on the instructions. **Limit:** it does not understand arbitrary
  instructions or restate the caller's actual reason; free generation is out of scope today.
- **Memory:** typed (episodic/semantic/contact/short-term) with trust tiers OBSERVED/INFERRED →
  CONFIRMED/USER_APPROVED; soft delete via `/memories`. Embeddings are placeholders ("real
  embeddings once a local embedding model is wired in") — **semantic recall quality NOT VERIFIED**.
- **Clarification loop:** low-confidence but actionable predictions are remembered and resolved
  (confirm/cancel/abandon) on the next reply via a deterministic yes/no matcher.
- **Policy:** confidence-gated (`POLICY_MIN_SENSITIVE_CONFIDENCE`, default 0.75); `ANSWER_CALL`,
  `TRANSFER_CALL`, `END_CALL` are *reported, not executed* by the agent.

## 15. Security

**Phase 1 (done, code-tested; not live-tested):**
- `X-WOW-API-Key` (`API_ACCESS_KEY`) on every REST route except `/health` and Plivo routes;
  constant-time compare; OpenAPI/docs hidden when protected; the backend **refuses to start** if
  `PUBLIC_BASE_URL` is set without `API_ACCESS_KEY` and `PLIVO_AUTH_TOKEN`.
- Plivo webhook signature (V3) — fail-closed; unsigned mode only via `PLIVO_ALLOW_UNSIGNED_WEBHOOKS`
  and ignored when `PUBLIC_BASE_URL` is set.
- WebSocket: single-use token (`secrets.token_urlsafe(32)`, SHA-256 digest stored, TTL
  `PLIVO_STREAM_TOKEN_TTL_SECONDS`=120, in-memory), minted by the signed webhook, **bound to
  `CallUUID`**, validated before accept, consumed on first use (replay → rejected), expiry enforced,
  start-event call-id cross-check.
- Caps: `PLIVO_MAX_CONCURRENT_STREAMS`=2, `PLIVO_MAX_CALL_SECONDS`=1800, bounded queue, oversized frame limit.
- Secrets: environment-only; `.env` git-ignored; repo scan found no committed credentials; tokens/API
  key never logged or returned; **uvicorn access-log token redaction** added (`RedactStreamTokenFilter`).
- Mobile sends the key via `--dart-define=WOW_API_KEY` (Dart) and the `WOW_API_KEY` build env var
  (Kotlin `BuildConfig`). A key embedded in an APK is extractable.
- CORS `allow_origins=["*"]` (no cookies; header-key auth).
- Transcripts: card-like numbers and OTP/PIN codes redacted before storage; phone numbers/emails kept
  deliberately.

**Known limitations / Phase 3:** single shared key (no per-user auth/ownership); production Render not
key-enforced and the installed app v1.2.0 sends no key; production OTP exposed; token store is in-process
(one worker); full transcript PII handling; agent state/memory may hold raw utterances; no caller-facing
recording disclosure; no rate limiting; permissive CORS; `SECRET_KEY` is unused by app code.

## 16. Privacy

- **Consent:** `training_data_consent` (default False, opt-in); a feedback record without it can never become
  a training candidate. UI: privacy/permissions screen (permission status via real Android state, consent
  toggle writes the real column, "turn WOW off", disclosure text). No silent permissions.
- **Retention:** `CALL_RETENTION_DAYS`=15 via an externally-run cleanup job (**not scheduled**).
- **Redaction:** feedback → full regex filter; stored call transcripts → card/OTP/PIN only (Phase 1).
- **Data rights:** feedback export/delete/disable-consent/reset-personalization endpoints exist.
  **No in-app delete button and no per-call delete endpoint** — the privacy screen says so plainly.
- **Caller disclosure:** NOT IMPLEMENTED (the greeting is a bare "Hello."). Legal/product decision pending.
- **Phase 3 privacy work:** full PII redaction of stored transcripts and agent memory, per-call/user delete,
  scheduled retention, caller recording/AI disclosure, per-user access control.

## 17. Database

- **Tech:** PostgreSQL + pgvector (production Neon; local `pgvector/pgvector`), SQLAlchemy 2.0 async +
  asyncpg; SQLite+aiosqlite used by unit tests only (pgvector tables skipped there).
- **Tables (9+):** `users`, `contacts`, `context_profiles`, `calls`, `conversations`, `transcript_segments`,
  `summaries`, `memories` (vector column), `agent_states`, plus `feedback_events`, `verification_codes`.
  Key FKs: conversations→calls/users, transcript_segments/summaries/agent_states/feedback_events→conversations.
- **Migrations (Phase 1):** Alembic (`backend/alembic.ini`, `backend/migrations/`; the directory is named
  `migrations` to avoid shadowing the `alembic` package; helpers in `app/db/migration_helpers.py`).
  `0001_baseline` = adopt-or-create via `create_all(checkfirst)` (+ `CREATE EXTENSION vector` on Postgres;
  vector tables skipped on other dialects) — **never edit it**; `0002_phase1_cols` adds nullable
  `context_profiles.user_instructions` and `transcript_segments.language` idempotently. Future revisions must
  use the idempotent helpers. The Dockerfile runs `alembic upgrade head` before uvicorn; a failed migration
  stops the container (Render keeps the previous deploy).
- **Why:** `create_all` never alters existing tables, so the new columns would have broken production.
- **Validation status:** SQLite (fresh, adoption with data preserved, idempotent, downgrade) and real
  Postgres+pgvector (fresh + legacy-shaped adoption) PASS. **Neon: inferred (§11), not directly verified.**
- **Other:** `create_all` still runs at startup (fresh/dev); no `ON DELETE CASCADE` (child rows deleted
  explicitly by retention); Redis unused.

## 18. Deployment

- **Local dev:** `docker compose up db redis backend` (Postgres 5433, Redis 6380, API 8000) or a venv
  (`docs/RUNNING.md`); `alembic upgrade head` from `backend/`.
- **Real local voice stack:** `pip install -r backend/requirements-local-{stt,tts,model}.txt`; env
  `STT_PROVIDER=local_whisper TTS_PROVIDER=local_piper MODEL_PROVIDER=local_wow
  WOW_MODEL_DIR=training/models/wow-brain/v3 AGENT_RUNTIME=wow_agent`.
- **Public tunnel for Plivo:** `cloudflared tunnel --url http://localhost:8000` (random hostname each run).
- **Render/Neon:** §11. Release APK points at Render; debug at the emulator alias.
- **Environment variable NAMES** (values never in git): `APP_ENV API_HOST API_PORT DATABASE_URL REDIS_URL
  MEMORY_EMBEDDING_DIM SECRET_KEY MODEL_PROVIDER WOW_MODEL_DIR INFERENCE_DEVICE
  INTENT_CONFIDENCE_THRESHOLD CONTEXT_CONFIDENCE_THRESHOLD ACTION_CONFIDENCE_THRESHOLD AGENT_RUNTIME
  POLICY_MIN_SENSITIVE_CONFIDENCE CALL_RETENTION_DAYS OTP_EXPOSE_DEV_CODE OTP_CODE_TTL_SECONDS
  OTP_MAX_ATTEMPTS STT_PROVIDER TTS_PROVIDER WHISPER_MODEL_SIZE DEMO_USER_ID PUBLIC_BASE_URL
  PLIVO_AUTH_ID PLIVO_AUTH_TOKEN PLIVO_ALLOW_UNSIGNED_WEBHOOKS PLIVO_STREAM_TOKEN_TTL_SECONDS
  PLIVO_MAX_CONCURRENT_STREAMS PLIVO_MAX_CALL_SECONDS API_ACCESS_KEY`; build-time: `WOW_API_KEY`
  (env for Gradle + `--dart-define`), `WOW_BACKEND_URL` (dart-define). Test-only: `TEST_DATABASE_URL`.
- **Local secrets file:** `backend/.env` (git-ignored, loaded by Settings; env vars outrank it; tests pin a
  baseline in `tests/conftest.py` so they never depend on it).
- **Production limitations:** §11 and §15.

## 19. Testing History (what was proven vs simulated)

| When | Result | Notes |
|---|---|---|
| Phase 2 blocks | backend 214/10 skipped → 225/10 → 232/10 → 241/10 → 243/10 | real Whisper/Piper/VAD on real fixtures |
| Phase 5 | backend 243 passed / 3 skipped; `flutter analyze` clean; 2 Flutter tests | emulator + `adb emu gsm call` |
| Physical device (Phase 8) | Vivo/Android 13: screening 3/3, auto-answer trigger bug found/fixed | **owner-observed via logcat; not re-run after the 5 s change** |
| Plivo prep | 259/29 → 262/29 → 297/29 → 313/29 → 355/29 | all with fake WebSockets/fixtures — **not a real call** |
| Brain v3 held-out | 94.15 / 90.86 / 95.30 (§6) | on project dataset |
| Phase 1 (2026-10-01) | no DB: **497 passed, 30 skipped** (all `TEST_DATABASE_URL`-gated); Postgres+pgvector: **527 passed, 0 skipped**; after rehearsal fixes **532 passed, 0 skipped** | throwaway Postgres container |
| Flutter (Phase 1) | `flutter analyze`: no issues; **10 tests pass**; debug APK built (Kotlin/Gradle edits compile) | 10 includes 2 API-key client tests |
| `training/tests` | 254 test functions present; **last full run not recorded here — NOT VERIFIED in this file** | |
| Phase 1 rehearsal | 27/27 checks (see below) | real server/Postgres/Whisper/Brain v3/Piper, **simulated caller** |

**Rehearsal (not the live gate):** auth boundary; signed webhook with URL rebuilt from `PUBLIC_BASE_URL`;
token missing/invalid/mismatch/replay rejected; junk/outbound/oversized frames ignored; English ×3 +
Hindi turn answered with audio; transcript, per-turn language (`en`,`hi`), summary, COMPLETED call
persisted; OFF hangs up.
**Mocked/simulated, therefore NOT proof of real-world success:** every Plivo test (fake socket / synthetic
mu-law), Hindi audio (Piper-synthesized), Hinglish (never tested), production STT/TTS (simulated).

## 20. Current Git State

- Repository `https://github.com/iamankoo/wow-ai`, branch `main`, tags `v1.0.0 v1.1.0 v1.2.0` (plus an old
  `preserved-pre-attribution-fix-2026-09-03`). No new tags/releases are to be created without the owner asking.
- `3a0aa841ec41675bdb98cfd211e45e0e6d1bd16c` — Phase 1 implementation commit.
- `2e2e5dd` — Phase 1 live-rehearsal fixes (the latest code commit when this file was written; this file is
  committed after it).
- Author and committer of every recent commit: `iamankoo <aniketraj00384@gmail.com>`.
- **Rules:** verify `git config user.name`/`user.email` before every commit; **no** Claude/Anthropic
  attribution, **no** `Co-Authored-By`, **no** session trailers (any tooling that suggests them must be
  overridden); push to `main`; verify `origin/main == HEAD` and a clean tree.
- Git ignores: `.env`, `training/models/`, datasets, `kaggle-upload/`, build output.

## 21. Current Known Limitations

### Implemented but limited
Rule-based default provider; Brain v3 opt-in and PC-only; template replies; context instructions = 4
booleans; embeddings placeholder; latency 2.4–7.9 s/turn on CPU; Hinglish uses the Hindi voice; barge-in
event exists but is **not** wired to stop playback; notification on Plivo calls is a log line, not a push;
activation expiry is lazy; single shared API key; one hard-coded user.
### Not implemented
Free-form generation; Business mode; carrier forwarding; per-user auth; Redis usage; real OTP delivery;
agent-executed `ANSWER_CALL`/`TRANSFER_CALL`/`END_CALL`; caller disclosure; in-app/per-call data deletion;
scheduler for retention; live canary routing; automated retrain/promote chaining; mixed precision; shared-trunk Brain.
### Not verified
Everything on a real Plivo call (§12); inbound JSON shape; `?token=` query survival; hangup on socket close;
Hindi/Hinglish accuracy with real speakers; 5 s window on a device; privacy screen on a device; Neon migration
(directly); Whisper `base` quality on 8 kHz phone audio; production behaviour under load.
### Provider / platform limitations
Android cannot access cellular call audio; cannot end or transfer a call without privileged APIs; Whisper has no
Hinglish mode; Piper has no gender field/Hinglish voice; Render free plan (512 MB, spin-down); Plivo docs lack
verbatim inbound event JSON; Plivo handshake has no signature.
### Phase 3 work
Per-user accounts/authorization; production key enforcement + mobile release; real OTP; full PII/transcript
handling, delete, scheduled retention, caller disclosure; shared token store; rate limiting.
### Phase 4 work
Business WOW (multi-tenant, routing, concurrency target to be defined), scale-out hosting.
### Phase 5 work
Launch gate: free-form natural conversation decision, production hosting, load/security/privacy sign-off.

## 22. Current Phase Status

| | Status |
|---|---|
| **Phase 1 implementation** | **COMPLETE** (commit `3a0aa84`, fixes `2e2e5dd`) |
| **Phase 1 live validation** | **NOT CLOSED** — no real Plivo call has been made; credentials are now present locally and the Default application's Answer URL is set, but **business KYC / an Indian phone number is still required** (see the 2026-10-02 checkpoint) |
| Phase 2 | **NOT STARTED** |

Phase 1 must **not** be called CLOSED until a real external phone call proves the bridge end to end.

## 23. Immediate Next Step — Phase 1 Live Validation Gate

Prepared already: backend `.env` (git-ignored) with `API_ACCESS_KEY` generated and non-secret provider
settings; local Postgres container for the test database; a Cloudflare quick tunnel; rehearsal passed.
Still required, in order:
1. ~~Owner enters `PLIVO_AUTH_ID` and `PLIVO_AUTH_TOKEN` in `backend/.env`~~ — **DONE (2026-10-02, present locally; never in chat/git).** **New blocker: Plivo business KYC / Indian number — see the 2026-10-02 checkpoint.**
2. Plivo console: an XML Application whose **Answer URL** = `<PUBLIC_BASE_URL>/telephony/plivo/answer`
   (POST), the Plivo number attached to it, Audio Streaming enabled — owner performs/confirm labels.
3. Start the backend with real providers and `PUBLIC_BASE_URL` = tunnel; activate WOW (1 h).
4. First real inbound call; verify webhook, signature, token, WebSocket, media parsing, audio path
   (timings), English, Hindi, Hinglish, a language switch, persistence (call/conversation/transcript/
   language/summary), cleanup, OFF behaviour, expiry, a spoken OTP being redacted.
5. A short-duration call to learn whether closing the stream hangs up the phone call (END_CALL result;
   the agent action itself is not executable).
6. Induced single-turn failure → call survives; repeated → ends; cleanup.
7. Neon migration validation (needs Neon access; otherwise report BLOCKED) and the owner's mobile client
   authenticating with the key (needs a build with `WOW_API_KEY`).
8. Full automated tests (Postgres), `flutter analyze`, `flutter test`, Android build.
Closure rule: only a passing real call closes Phase 1. Failures → fix only Phase 1 issues; a proven
provider limitation is documented, not bypassed, and the report states whether it blocks Phase 2.

## 24. Remaining Master Roadmap (locked order; names from the owner's instructions)

> Exit criteria below beyond Phase 1 are **derived from the owner's instructions and this repo's gaps**;
> the authoritative text is in `Phases.md`, which is **not in the repo** — reconcile before use.

- **Phase 1 — Stabilization & Plivo Production Foundation.** Implementation complete; live gate pending.
  Exit: real Plivo end-to-end call passes + exit checklist (§22/§23).
- **Phase 2 — Real Plivo Voice + Individual WOW.** Make the real call experience good: latency, voice
  quality, Hindi/Hinglish quality, end-of-call handling, notifications, carrier forwarding story. Exit: a
  repeatable real-call experience for the owner.
- **Phase 3 — Production Individual WOW.** Per-user auth, production hardening, privacy/PII/deletion,
  real OTP, hosting, observability, scheduled retention. Exit: safe for real users' data.
- **Phase 4 — Business WOW + Scale.** Multi-tenant business agent, concurrency target, scale-out.
- **Phase 5 — Final Production & Launch Gate.** Everything in §25 true and signed off.

## 25. Launch Requirements

All must be true before WOW is honestly "launch-ready": real Plivo calls proven on real numbers and
networks; Hindi/Hinglish/English quality validated with real speakers; acceptable latency; **genuinely
natural, free-form conversation** — the current bounded classifier + template system does **not** satisfy
this and must not be described as if it does (needs a fine-tuned generator or an equivalent approved
approach, with safety review); per-user auth; production hosting with enough RAM/disk and always-on;
real OTP; PII/privacy/deletion/disclosure completed; caller recording notice; migrations validated on
production; monitoring and rate limits; Business-mode tenant isolation and a load test at the agreed
concurrency; installed-app update path with the API key; legal/telecom compliance (KYC, call-recording laws).

## 26. Decision Log (supported by repo history)

| Date | Decision | Why |
|---|---|---|
| 09-01 | Self-hosted/local AI, provider interfaces, no hosted AI API | privacy, control, README §1 |
| 09-03 | Classifier Brain (3 heads), human-gated offline learning, no live updates | avoid forgetting/poisoning |
| 09-03 | Retrain v3 on Kaggle after artifact loss; persistence on; best-effort RNG restore | recovery lessons |
| 09-03 | END_CALL/TRANSFER_CALL documented as platform limits, not faked | `MODIFY_PHONE_STATE`/`InCallService` |
| 09-04 | Neon instead of Render-managed DB | one free DB per account |
| 09-04 | Revert real STT/TTS on Render | measured OOM crash |
| 09-04 | Timer also started from the screening service | process killed in background |
| 09-17 | Plivo over Twilio/Exotel; separate Plivo number, not SIM tapping | India inbound, pricing, Android audio limit |
| 09-17 | Pure-Python mu-law codec | `audioop` removed in Python 3.13 |
| 09-17 | Multilingual via detection + phrase banks, not generation; Brain untouched | scope; Brain v3 frozen |
| 09-17 | Explicit `PUBLIC_BASE_URL` | proxy headers unreliable |
| 10-01 | Stream token + signature fail-closed + API key + startup refusal | public tunnel exposure |
| 10-01 | Redact only card/OTP/PIN in stored transcripts | keep callback details for the owner |
| 10-01 | Alembic baseline adopts `create_all` DBs; idempotent revisions | protect existing Neon data |
| 10-01 | Production not key-enforced yet | installed app sends no key |
| 10-01 | Roadmap Phase 2 not started until live gate passes | owner's rule |

## 27. How to Continue This Project

1. Read this file, then **obtain and read `Phases.md`** (absent from the repo) and reconcile §24.
2. Read `docs/SECURITY.md`, `docs/PLIVO_TESTING.md`, `docs/ARCHITECTURE.md`, `docs/DEPLOYMENT.md`,
   `docs/implementation-status.md` (note its sync gap) and the git log.
3. `git status`, `git log -5`, verify identity (`iamankoo` / `aniketraj00384@gmail.com`).
4. Never skip the roadmap order. Never claim functionality without verification — mocked/simulated tests
   are not proof of a real call.
5. Never modify Brain v3 unless explicitly authorized. Plivo is locked.
6. Preserve Git rules (§20). No releases/tags unless asked.
7. Before starting any phase, cross-check the implementation prompt against `Phases.md` and report mismatches.
8. Run the full backend suite against Postgres (`TEST_DATABASE_URL`, a **throwaway** database — fixtures
   `drop_all`), `flutter analyze`, `flutter test`, and an Android build before committing.
9. Tests must not depend on `backend/.env`; override with `monkeypatch.setenv`, never `delenv`.
10. Update this file after every major phase.

## 28. Handoff Checklist

- ✅ Complete: Phase 1 implementation; historical phases up to Render/Phase 8; Brain v3; Plivo bridge code.
- 🟡 Being validated: Phase 1 live gate (real Plivo call).
- ➡️ Next: credentials in `backend/.env`, Plivo console Answer URL, first real call.
- ⛔ Do NOT: start Phase 2; create releases/tags; add AI attribution; change Brain v3; replace Plivo; weaken security.
- 🔑 Needed: `PLIVO_AUTH_ID`, `PLIVO_AUTH_TOKEN`, `API_ACCESS_KEY`, `PUBLIC_BASE_URL`, Postgres, tunnel, Plivo number +
  XML Application, (for Neon check) Neon access, (for the app) a build with `WOW_API_KEY`.
- 📚 Docs: `summary.md`, `README.md`, `docs/*`, `docs/SECURITY.md`, `docs/PLIVO_TESTING.md`, `render.yaml`.

## End-of-Day Checkpoint — 2026-10-02

**Source of facts:** repository state and local checks on 2026-10-02, plus what the project owner reported
from the Plivo dashboard (the dashboard itself was not visible to the coding agent — those items are
owner-reported, not independently observed). No secret values appear in this file.

### Status
| Item | Status |
|---|---|
| Phase 1 implementation | **COMPLETE** |
| Phase 1 live validation gate | **NOT CLOSED** |
| Real Plivo call | **NOT MADE** |
| Plivo Answer webhook | **NOT LIVE-VERIFIED** (only exercised locally with a simulated, correctly-signed request) |
| WebSocket stream | **NOT LIVE-VERIFIED** |
| Real caller audio through Plivo | **NOT VERIFIED** |
| English / Hindi / Hinglish through real Plivo | **NOT VERIFIED** |
| Real-device privacy validation | **NOT COMPLETE** |
| Neon production migration | **NOT DIRECTLY VERIFIED** (inferred from production behaviour only, §11/§17) |
| Phase 2 | **NOT STARTED** |

### Latest commits (all authored/committed as `iamankoo <aniketraj00384@gmail.com>`, no attribution trailers)
- `3a0aa841ec41675bdb98cfd211e45e0e6d1bd16c` — Phase 1 implementation
- `2e2e5dd` — Phase 1 live-rehearsal fixes (conversation commit mid-call; stream-token log redaction)
- `3b8a4ec` — `summary.md` created
- (this checkpoint is committed on top of `3b8a4ec`; `git log -3` shows the exact hash)

### Local credential configuration (verified 2026-10-02; values never read into this file)
- `backend/.env` is **git-ignored and untracked** (verified).
- `PLIVO_AUTH_ID` = **PRESENT**; `PLIVO_AUTH_TOKEN` = **PRESENT**; `API_ACCESS_KEY` = present (generated locally).
- Secrets exposed anywhere (git, logs, this file, reports): **NO**.

### Plivo dashboard state (owner-reported)
- **Plivo account:** exists; credentials were obtained and entered locally.
- **Application:** the existing **Default** Plivo application.
- **Answer URL configured:** `https://project-reflect-inspections-subscribers.trycloudflare.com/telephony/plivo/answer`
- **Answer method:** **POST**
- **Indian phone number linked:** **NO** — no Plivo number is attached to the application.
- **KYC:** **REQUIRED.** Today's work reached the Plivo requirement that **business KYC must be completed
  before an Indian phone number can be obtained**. KYC is **not approved / not completed** (no number could be
  obtained); no further status detail was recorded.
- **Audio Streaming enabled on a number:** NOT VERIFIED (no number exists yet).

### Current tunnel
- Recorded Cloudflare quick-tunnel URL: `https://project-reflect-inspections-subscribers.trycloudflare.com`
  (a `cloudflared` process was still running at the checkpoint). **Quick-tunnel hostnames change whenever the
  tunnel restarts**, and the backend was **not running** at the checkpoint, so the tunnel currently forwards to
  nothing (HTTP 502). If the tunnel URL changes, the Default application's Answer URL **and** `PUBLIC_BASE_URL`
  must both be updated.

### What has been successfully verified (all local / code-level)
Backend suite **532 passed, 0 skipped** against Postgres+pgvector (497 passed / 30 skipped without a database,
measured before the last fixes); Flutter analyze clean + 10 tests; debug APK builds; a 27/27 local rehearsal of
the real server (real Postgres, Whisper, Brain v3, Piper) with a **simulated** caller covering auth, signed
webhook with URL reconstruction, token rejection cases, junk-frame tolerance, English/Hindi/English turns,
persistence and OFF-behaviour; migrations on SQLite and real Postgres.

### What has NOT been verified
Everything in the "Status" table marked NOT VERIFIED / NOT LIVE-VERIFIED; Plivo's inbound `start`/`media` JSON
shape; whether Plivo preserves `?token=` on the WebSocket URL; whether closing the stream hangs up the phone call
(END_CALL); Hinglish at all; real human Hindi speech; failure recovery on a live call; the 5-second human-first
window on a device; the mobile client authenticating with the API key (needs a build with `WOW_API_KEY`); the
privacy screen on a physical device.

### Exact blockers
1. **Plivo business KYC not completed → no Indian phone number can be rented** → there is no number to call.
2. The backend is not currently running (it must be started with real providers before any call).
3. The tunnel URL may change on restart (requires updating the Default application's Answer URL).
4. Neon access is not available to the coding agent, so the production migration cannot be directly verified.

### Exact next action
**Complete / check Plivo business KYC; once approved, rent the Indian number and link it to the Default application.**

### Where we stopped today
Plivo credentials entered locally; the Default application's Answer URL set to the tunnel URL with POST; the
dashboard then required business KYC before a number can be obtained; development stopped there. No call was made,
no implementation was changed after `2e2e5dd`, and Phase 2 was not started.

## NEXT SESSION — CONTINUE FROM HERE

**CONTINUE FROM PLIVO KYC / PHONE NUMBER SETUP.**

1. **Read this file first.**
2. **Read `Phases.md` if/when it is available in the repository** (it was absent on 2026-10-02; reconcile §24).
3. **Verify the Git state:** `git status`, `git log -5`; `git config user.name` / `user.email` must be
   `iamankoo` / `aniketraj00384@gmail.com`; `origin/main` must equal `HEAD`; the working tree must be clean.
4. **Verify the current Cloudflare tunnel URL** — it may have changed after any restart. If it differs from the
   URL above, update the Plivo Default application's Answer URL and the `PUBLIC_BASE_URL` used at launch.
5. **Check Plivo KYC status.**
6. **If KYC is approved, obtain/rent the Indian Plivo phone number.**
7. **Link the number to the existing Default application** (and confirm Audio Streaming is enabled).
8. **Verify the Answer URL remains `<tunnel URL>/telephony/plivo/answer`, method POST.**
9. **Start the WOW backend with real providers** (`backend/.env` already holds the credentials, the generated
   `API_ACCESS_KEY` and the real-provider settings; pass `PUBLIC_BASE_URL` at launch; the local Postgres container
   `wow-ai-phase1-rehearsal-pg` may need restarting; the backend takes ~1–2 minutes to load models).
10. **Run the pre-call checks** (health, signed-webhook self-test with the real token, activation state — see
    `docs/PLIVO_TESTING.md`; WOW is OFF by default and must be activated deliberately).
11. **Only after the coding agent explicitly reports readiness, make the first real Plivo call.**
12. **Complete the Phase 1 Live Validation Gate** (§23): English, Hindi, Hinglish, a language switch, persistence,
    cleanup, activation, OTP redaction, END_CALL behaviour, failure recovery, then the full automated tests.
13. **Do NOT start Phase 2 until Phase 1 is formally CLOSED.**

## 29. Last Updated

- **Date:** 2026-10-02 (end-of-day checkpoint; originally written 2026-10-01)
- **Latest code commit:** `2e2e5dd` (Phase 1 implementation: `3a0aa841ec41675bdb98cfd211e45e0e6d1bd16c`); documentation commits follow it
- **Current phase:** Phase 1 — implementation complete, live gate NOT CLOSED (blocked on Plivo KYC / phone number)
- **Source:** generated from the repository, its docs, git history, tests and the project owner's written instructions;
  no secrets included. Update after every major phase.
