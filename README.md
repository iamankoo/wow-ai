# WOW AI

**A self-hosted personal AI call assistant.** WOW AI answers phone calls on
your behalf when you're unavailable, identifies the caller, loads the right
context (busy, travelling, in a meeting, asleep, ...), converses naturally
in English, Hindi, or Hinglish, and hands you back a transcript and summary
afterward.

This README is written to be accurate, not aspirational: every claim below
is marked as **Implemented** or **Planned**, and the current v3 model
status is reported exactly as measured, not rounded up.

> **Status: Phase 1 (personal use, single-tenant).** WOW AI is a working
> backend + reasoning core + training pipeline today. It is **not yet** a
> fully autonomous phone agent handling real live calls, and its
> self-learning loop is a real, tested, offline pipeline - not a model that
> updates itself from live traffic. See "Current limitations" below before
> assuming otherwise.

---

## 1. What WOW AI is

WOW AI is architected as a **self-hosted AI system**, not a wrapper around
a hosted third-party AI API (OpenAI, Claude, Gemini, etc.). Every place the
system needs speech recognition, speech synthesis, reasoning, telephony,
or memory, it depends on an abstract provider interface
(`backend/app/interfaces/`) - never a specific vendor SDK. Phase 1 ships
real, working, zero-external-API implementations of those interfaces (a
rule-based reasoning provider today, a Postgres/pgvector memory store, and
an optional self-trained classifier model), so swapping in a fully
self-hosted/fine-tuned model later means writing one new class - nothing
in the API or brain layers has to change.

## 2. Product vision

Let a phone owner delegate "answer this call for me" to an assistant that:

1. Knows who's calling (contacts) and what context the owner is currently
   in (a named profile: busy, sleeping, travelling, in a meeting, custom).
2. Converses with the caller naturally, in the caller's language.
3. Takes the right action for that context - answer normally, ask the
   caller to leave a message, mark a call urgent, offer to transfer, etc.
4. Leaves the owner a transcript, a summary, and any action items - and
   gets better over time from the owner's own corrections, under an
   explicit consent-and-approval pipeline, never silently.

## 3. Current capabilities (Implemented vs. Planned)

| Capability | Status |
|---|---|
| FastAPI backend, domain models, REST API (`/brain/command`, `/feedback/*`, `/contacts`, `/users`) | **Implemented** |
| Rule-based reasoning provider (keyword intent classifier, zero ML deps) | **Implemented** |
| WOW Brain v0 agent runtime (context -> reasoning -> state -> action) | **Implemented**, default |
| WOW Agent orchestrator: explicit conversation state, confidence-gated policy engine, controlled tool registry (`backend/app/agent/`) | **Implemented**, opt-in (`AGENT_RUNTIME=wow_agent`; not yet the default) |
| Self-trained classifier model (intent/context/action, 3 heads) - v0 through v3 | **Implemented** (v3 training in progress, see §8) |
| Postgres + pgvector memory store, per-user personalization | **Implemented** |
| Memory safety: typed memories (episodic/semantic/contact/short-term), trust tiers (observed -> confirmed/user-approved), soft-delete (`/memories` API) | **Implemented** |
| Self-learning feedback pipeline (consent -> privacy filter -> human approval -> retrain -> evaluate -> promote) | **Implemented**, fully offline/batched |
| Data-subject rights (export, delete, disable training, reset personalization) | **Implemented** |
| Android app shell (Flutter/Dart + Kotlin), backend round-trip proof-of-concept | **Implemented** |
| Real telephony integration (`CallScreeningService`/`InCallService`) | **Planned** (only a deterministic local simulator, `SimulatedTelephonyProvider`, exists today) |
| Self-hosted speech-to-text / text-to-speech | **Planned** (only deterministic local simulators, `SimulatedSTTProvider`/`SimulatedTTSProvider`, exist today) |
| End-to-end simulated-call harness (`app/simulation/call_simulator.py`): scripted STT -> WowAgent -> TTS -> telephony, real orchestration around simulated audio | **Implemented** |
| `LocalWOWModelProvider` as the default production reasoning provider | **Planned** (works today, opt-in via `MODEL_PROVIDER=local_wow`; `rule_based` is still the default) |
| Live canary traffic routing between model versions | **Planned** (registry supports the status; routing logic does not exist yet) |
| Fully automated dataset-build/retrain/promote pipeline | **Planned** (every step is real and tested; chaining them together end-to-end is currently a human-run sequence, by design - see §9) |

## 4. Architecture

```
wow-ai/
├── backend/        FastAPI service - the "brain" and REST API
├── mobile/         Flutter Android app (Dart UI + Kotlin native shell)
├── training/        Model training pipeline, datasets, evaluation, inference
├── docker-compose.yml   Postgres(+pgvector) + Redis + backend
└── docs/            Design docs (architecture, model, dataset, training, self-learning)
```

Backend request flow (`POST /brain/command`, `backend/app/brain/wow_brain.py`):

```
text in -> ContextEngine.build_context()    (who's calling, active persona, memories)
        -> LanguageModelProvider.generate()  (classify intent, produce a reply)
        -> StateRepository.set()             (persist turn_count, last_intent)
        -> AgentAction out                   (structured: {type, payload})
```

This is intentionally a straight-line sequence today, not a branching graph
engine - the seams are exactly what a multi-node graph executor would plug
into next, without changing the `AgentRuntime` contract the API depends on.

Provider interfaces and their Phase 1 implementations:

| Interface | Phase 1 implementation | Phase 2 direction |
|---|---|---|
| `LanguageModelProvider` | `RuleBasedLanguageModelProvider` (default) / `LocalWOWModelProvider` (opt-in, self-trained model) | Fine-tuned model as the default |
| `MemoryStore` | `PgVectorMemoryStore` (Postgres + pgvector) | Real embeddings once a local embedding model is wired in |
| `ContextEngine` | `DefaultContextEngine` (contact + profile + memory lookup) | Conversation-history summarization |
| `AgentRuntime` | `WowBrain` v0 (default) / `WowAgent` (opt-in, `AGENT_RUNTIME=wow_agent` - state + memory + policy + tools, see `docs/ARCHITECTURE.md`) | `WowAgent` promoted to default once proven; STT/VAD-driven turn detection |
| `SpeechToTextProvider` / `TextToSpeechProvider` / `TelephonyProvider` | Contract only | Self-hosted ASR/TTS (e.g. faster-whisper, Piper/Coqui) + Android call-handling bridge |

Full design: [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md).

## 5. Model architecture

A WOW Brain model version is **three independent text-classification
heads** (not one multi-task model), each a full fine-tuned copy of the same
base encoder with its own classification layer:

```
training/models/wow-brain/<version>/
├── intent/    predicts Intent      (17 classes)
├── context/   predicts ContextMode (7 classes)
├── action/    predicts Action      (13 classes)
```

| Version | Base model | Why |
|---|---|---|
| v0 | `prajjwal1/bert-tiny` (~4.4M params) | Proved the training pipeline end-to-end on CPU in minutes. Never claimed production-quality - its English-only vocabulary had no meaningful Hindi representation. |
| v1 | `distilbert-base-multilingual-cased` (~135M params, 119,547-token vocab) | Fixes the Hindi/Hinglish tokenization gap - verified directly by comparing tokenizer output on the same Hindi sentence (see `docs/MODEL_ARCHITECTURE.md`). Still CPU-practical. |
| v2 | Same base model, trained on a 33K hand-annotated dataset | Revealed a real gap: zero `ANSWER_CALL` examples anywhere in that dataset. |
| v3 | Same base model, trained on the 66K `v3.3.0-answer-call` dataset | Closes the `ANSWER_CALL` gap (30,000 added examples + 3,000 hard negatives). In progress - see §8. |

Base model is a config value, not hardcoded (`training/configs/model_config*.yaml`)
- swapping base models requires a new config file and a training run, no
code changes. Full detail: [`docs/MODEL_ARCHITECTURE.md`](docs/MODEL_ARCHITECTURE.md).

**Known architectural cost, not yet addressed:** three independent model
copies means three forward passes per request (3x the inference compute of
a shared-trunk multi-head model). A shared-trunk redesign is a planned,
not-yet-done, follow-up (see "Roadmap").

## 6. Training pipeline

`training/training/train.py` is a plain PyTorch training loop (no
`transformers.Trainer`/`accelerate` dependency, kept minimal so it runs
identically on CPU or GPU):

- Config-driven (`training/configs/model_config*.yaml`): base model, seed,
  batch size, learning rate, epochs, per-head definitions, dataset/output
  paths, device.
- Class-weighted cross-entropy (optional) and early stopping (configurable
  patience).
- **Checkpoint + resume**: every epoch writes `checkpoint.pt` (model +
  optimizer + RNG + early-stopping + history state) and `checkpoint_best.pt`
  (best-validation-accuracy weights). Rerunning with `--resume` continues
  each head from its own last completed epoch - never restarts at epoch 1
  unless a checkpoint genuinely isn't present.
- **Explicit device selection** (`training/training/device.py`): `"cpu"` /
  `"cuda"` / `"mps"` / `"auto"`. Requesting an accelerator that isn't
  actually available raises immediately - it never silently falls back to
  CPU and reports numbers that look like they came from a GPU run.
- All paths resolve relative to the repository root at runtime
  (`training/training/config.py:REPO_ROOT`) - nothing is hardcoded to any
  specific machine, so the same config works unmodified on a laptop or a
  cloud GPU checkout.

`training/evaluation/evaluate.py` scores every model version (plus the
rule-based baseline) on the same held-out `val.jsonl`: intent/context/action
accuracy, structured-output validity, per-intent accuracy, mode-collapse
detection, a full confusion matrix, and per-language breakdowns.

Full detail: [`docs/TRAINING.md`](docs/TRAINING.md).

## 7. Dataset & versioning approach

Each finalized dataset lives at `training/datasets/versions/<version>/`
with a `MANIFEST.json` recording every file's SHA-256 checksum, byte size,
and line count - so "did this training run actually use the data I think
it did" is independently verifiable, not just trusted by filename.
Versions are never overwritten; each is an independent, checksummed
snapshot. Splits are stratified by intent (`training/pipeline/split.py`),
and **test is held out**: nothing in the pipeline reads `test.jsonl` except
final evaluation reporting.

Reusable dataset-generation/preprocessing code lives under
`training/pipeline/` (dedup, PII detection, language ID, quality gates,
diversity checks, schema validation, stratified splitting, versioning) and
`training/generation/` (seed-dataset construction). Full detail:
[`docs/DATASET.md`](docs/DATASET.md).

## 8. Current v3 training status (verified, not assumed)

**Dataset — `training/datasets/versions/v3.3.0-answer-call/`** (counts
verified against `MANIFEST.json` SHA-256 checksums, not assumed from
filenames):

| Split | Records |
|---|---|
| train | 52,514 |
| val | 6,701 |
| test | 6,785 |
| **Total** | **66,000** |

`ANSWER_CALL` action examples: 30,000 (10,000 each: English / Hindi /
Hinglish). Hard negatives: 3,000. Pre-existing (v2-era) examples: 33,000.

**Intent head checkpoint — `training/models/wow-brain/v3/intent/checkpoint.pt`**
(read directly from the checkpoint's own saved state, not inferred):

| Field | Value |
|---|---|
| Epochs completed | **14** of 20 configured |
| Next epoch on resume | 15 |
| Best validation accuracy | **94.54%** (epoch 10) |
| Last completed epoch's validation accuracy | 93.99% (epoch 14) |
| Early-stopping bad-epoch streak | 4 of 4 (patience) - next non-improving epoch would trigger early stop |
| Model + optimizer state present | Yes (resume-capable) |
| Trained on | CPU (this development machine has no CUDA GPU) |

This checkpoint is the **resume point**, not a finished model - training
continues (`--resume`, not a fresh run) on a cloud GPU. Full cloud-training
procedure: [`docs/KAGGLE_TRAINING.md`](docs/KAGGLE_TRAINING.md).

## 9. Self-learning / continuous-learning architecture

Production conversations **never automatically become training data**.
Every step from "a user gave feedback" to "a new model reaches production"
passes through an explicit gate:

```
Prediction + user feedback
    -> consent check -> retention check -> PII redaction   (automatic)
    -> CANDIDATE                                             (not yet training data)
    -> human approval (named reviewer required)              (APPROVED)
    -> TrainingCandidateBuilder writes a dataset batch        (INCLUDED)
    -> (human-run) dataset version build + train.py + evaluate.py
    -> PromotionManager.decide (regression-blocking evaluation gate)
    -> ModelRegistry: CANARY -> PRODUCTION (or REJECTED)
```

- **Consent is opt-in and per-user**, default `False`. Feedback without
  training consent is stored for product/review purposes only and is
  permanently rejected before it can become a training candidate.
- **PII redaction runs on every record** (`RegexPrivacyFilter`) - phone
  numbers, emails, card-like digit sequences, OTP/PIN codes. This is
  disclosed as defense-in-depth, not a guarantee (it doesn't do named-
  entity recognition on free text).
- **A named human must approve** every candidate before it can be written
  to a dataset file - there is no code path that skips this.
- **Promotion has a hard evaluation gate**: any intent-accuracy regression,
  or mode-collapse, blocks promotion outright, regardless of other gains.
- **Explicitly never implemented, by design**: live weight updates from
  unreviewed traffic. Online updates create catastrophic-forgetting and
  poisoning risk; every gate above exists specifically to prevent that.
  The loop is offline and batched end to end.

Full detail, including the exact API surface and what's still a manual
step today: [`docs/SELF_LEARNING.md`](docs/SELF_LEARNING.md).

## 10. Backend architecture

FastAPI + SQLAlchemy (async) + Postgres/pgvector + Redis. Nine domain
models (`backend/app/models/`): `users`, `contacts`, `context_profiles`,
`calls`, `conversations`, `transcript_segments`, `summaries`, `memories`,
`agent_states`. No Alembic migrations yet - Phase 1 bootstraps the schema
with `Base.metadata.create_all()` on startup; introduce Alembic once the
schema needs versioned, production-safe migrations.

## 11. Mobile application

Flutter (Dart UI) + Kotlin native shell (`mobile/android/`, embedding v2),
under `mobile/`. Phase 1's `HomeScreen` only verifies backend connectivity
and round-trips a text command through `/brain/command` - proof that the
client/server contract works end-to-end. **No telephony permissions are
requested yet.** Phase 2 adds a `MethodChannel` bridging Android's
`CallScreeningService`/`InCallService` into Dart so real incoming calls
drive the same `WowBrain`.

## 12. Memory & personalization

Two structurally separate systems, deliberately kept apart:

- **Personal memory/personalization** (`Memory`, `ContextProfile`): facts
  about *one user's* standing preferences (e.g. "treat family calls as
  high priority"). Retrieved per-request by `ContextEngine`, changes
  behavior for that user immediately, never touches model weights, and is
  user-resettable (`POST /feedback/reset-personalization`).
- **Global model improvement** (the self-learning loop, §9): patterns
  across many users' *authorized* feedback that indicate the classifier
  itself is wrong. Slow, batched, reviewed, evaluated - the opposite of
  personalization's immediate, per-user effect.

## 13. Privacy & security principles

- No hosted third-party AI API is ever called, in training or inference.
- Training data requires explicit, revocable per-user consent
  (`training_data_consent`, default `False`).
- PII is redacted before any text reaches a training candidate or file;
  raw text never leaves the originating feedback record.
- Every dataset inclusion is attributable to a named human reviewer -
  never anonymous, never automatic.
- Data-subject rights are implemented as real endpoints: export, delete
  feedback, delete not-yet-included candidates, disable training consent,
  and see exactly what was used for training (`backend/app/api/routes/feedback.py`).
- Secrets/config live in `.env` (see `.env.example`), never committed;
  `.gitignore` excludes virtualenvs, caches, local databases, model
  checkpoints, and finalized large datasets from version control.

## 14. Testing

```
backend/tests/    139 passed, 5 skipped (skipped tests require a live TEST_DATABASE_URL)
training/tests/   249 passed
```

Run them yourself - see §15.

## 15. Local development

**Prerequisites**: Docker Desktop, Python 3.10+, Flutter SDK (mobile only).

```bash
cp .env.example .env
docker compose up -d db redis backend
curl http://localhost:8000/health
```

Backend without Docker, and running tests:

```bash
cd backend
python -m venv .venv
.venv/Scripts/activate        # Windows; source .venv/bin/activate on macOS/Linux
pip install -r requirements.txt
python -m pytest -v
```

Full walkthrough (mobile setup, `/brain/command` example calls, DB-backed
integration tests): [`docs/RUNNING.md`](docs/RUNNING.md).

## 16. Cloud GPU training workflow

v3's intent-head checkpoint has 14 completed epochs (CPU-trained locally)
and is designed to **resume** on a cloud GPU (Kaggle: 2x NVIDIA Tesla T4)
rather than restart. Device selection is explicit
(`TRAINING_DEVICE=cuda` overrides the config file with zero code changes)
and refuses to silently fall back to CPU.

The complete, step-by-step procedure - getting source/dataset/checkpoint
onto Kaggle, verifying CUDA and the checkpoint with
`training/verify_kaggle_environment.py` (a read-only pre-flight check, no
training performed), the exact resume command, and how to pull trained
checkpoints back down - is documented in
[`docs/KAGGLE_TRAINING.md`](docs/KAGGLE_TRAINING.md).

## 17. Project structure

```
wow-ai/
├── backend/
│   ├── app/
│   │   ├── models/         SQLAlchemy ORM models
│   │   ├── interfaces/     Abstract provider contracts (STT/TTS/LLM/Telephony/Memory/...)
│   │   ├── providers/      Phase 1 concrete implementations
│   │   ├── brain/          WOW Brain v0 (AgentRuntime) + ContextEngine + state store
│   │   ├── learning/       Self-learning pipeline (feedback, privacy, promotion, registry)
│   │   ├── api/            FastAPI routers, schemas, DI wiring
│   │   └── config.py       Environment-driven settings
│   └── tests/
├── mobile/                  Flutter Android app (Dart UI + Kotlin native shell)
├── training/
│   ├── configs/             Per-version training configs (YAML)
│   ├── datasets/             Seed data, schemas; versioned datasets under versions/ (not in Git)
│   ├── pipeline/              Dedup, PII, quality, diversity, splitting, versioning
│   ├── training/                train.py, config.py, device.py
│   ├── evaluation/               evaluate.py
│   ├── inference/                 predict.py
│   ├── models/                     Trained checkpoints, versioned v0-v3 (not in Git)
│   └── verify_kaggle_environment.py
├── docs/                     Architecture, model, dataset, training, self-learning, Kaggle
├── docker-compose.yml
└── .env.example
```

## 18. Current limitations

- No real telephony integration - calls aren't actually being answered yet.
  `TelephonyProvider`/STT/TTS have deterministic local *simulators*
  (`app/providers/{stt,tts,telephony}/simulated.py`) so the orchestration
  stack around them is real and tested (`app/simulation/call_simulator.py`),
  but no real audio, ASR/TTS engine, or carrier/VoIP integration exists.
- The mobile app is a connectivity proof-of-concept, not a shipped call
  handler; no telephony permissions are requested.
- The default production reasoning provider is still the rule-based
  keyword classifier (`MODEL_PROVIDER=rule_based`); the trained neural
  model is available (`local_wow`) but opt-in, not yet the default.
- v3 training is incomplete (14 of 20 epochs) - resume on GPU is required
  before it can be evaluated as a finished model version.
- Three independent classification heads per request (3x inference cost)
  - a shared-trunk architecture is designed but not built.
  - Mixed precision (AMP/fp16) is not implemented in the training loop.
- Dataset-version building, retraining, and promotion are human-run steps,
  not an automated pipeline - by design, not an oversight (see §9).
- No live canary traffic routing between model versions yet.
- No Alembic migrations - schema changes require care in Phase 1.

## 19. Roadmap / next steps

- Finish v3 training on cloud GPU (Kaggle T4x2) and evaluate against v1/v2.
- Promote `LocalWOWModelProvider` to the default production provider once
  v3 clears the evaluation gate.
- Real Android `CallScreeningService`/`InCallService` integration.
- Self-hosted streaming ASR (e.g. faster-whisper) and TTS (e.g.
  Piper/Coqui) implementations of the existing contract-only interfaces.
- Shared-trunk, multi-head model architecture (cut inference compute and
  storage roughly 3x).
- Evaluate `google/muril-base-cased` (or another larger multilingual
  encoder) if Hindi/Hinglish accuracy remains the specific bottleneck.
- Automated dataset-version build tooling (still deliberately manual today).
- Live canary traffic routing in `app/api/deps.py`'s provider selection.
- Alembic migrations once the schema needs versioned, production-safe changes.

## 20. Implemented vs. planned - the short version

If it's described in §3, §5-§14 with a checkpoint file, a passing test, or
a documented, runnable command, it's real today. If it's in §18-§19, it
isn't built yet. This README intentionally does not describe WOW AI as an
already-autonomous, human-level phone agent, or as a model that learns
live from conversations - neither is true yet, and the self-learning
pipeline is explicitly designed to never do the latter without a human
in the loop (see §9).

---

## License / usage

Personal project, Phase 1 (single-tenant, personal use). See individual
`docs/*.md` files for full design rationale on any topic above.
