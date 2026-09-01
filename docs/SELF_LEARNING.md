# WOW's self-learning architecture

WOW Brain improves from real, authorized user feedback over time - but
production conversations never automatically become training data. Every
step from "a user said something" to "a new model is running in
production" passes through an explicit gate: consent, privacy filtering,
and a human approval, in that order, before anything is even eligible to
be written to a dataset file - and a further evaluation gate before any
retrained model can replace the one in production.

This document describes that pipeline end to end. The code lives under
`backend/app/learning/` (the pipeline itself), `backend/app/models/feedback.py`
and `backend/app/interfaces/feedback.py` (data model), and
`backend/app/api/routes/feedback.py` (the API). It builds on, and does not
replace, the classifier training pipeline in `docs/TRAINING.md`.

## The loop, end to end

```
WOW Brain prediction (intent / context_mode / action, + confidence)
        |
        v
   User feedback ---------------------------+
   (explicit: thumbs up/down, correction)    |
   (implicit: accepted, edited, rejected...) |
        |                                    |
        v                                    v
  FeedbackEvent (status=RECEIVED)   low-confidence prediction
        |                            logged as NEEDS_REVIEW
        |                            (active learning queue) --> user responds --> RECEIVED
        v
  FeedbackProcessor (app/learning/feedback_processor.py)
    1. consent check          (consent_for_training must be True)
    2. retention check        (event must not have gone stale unprocessed)
    3. PII detect + redact    (RegexPrivacyFilter)
        |
        +--> fails any check --> REJECTED (terminal, reason recorded)
        |
        v
  CANDIDATE  (passed the privacy pipeline; NOT yet training data)
        |
        | <-- a human calls FeedbackProcessor.approve(id, reviewed_by=...)
        v
  APPROVED   (explicitly authorized for dataset inclusion)
        |
        v
  TrainingCandidateBuilder (app/learning/candidate_builder.py)
        |  writes training/datasets/feedback_candidates/<batch>.jsonl
        v
  INCLUDED
        |
        v
  (human-run) dataset version build, merging with the hand-authored seed
        |
        v
  training/training/train.py  -->  new model version
        |
        v
  training/evaluation/evaluate.py  -->  evaluation report
        |
        v
  PromotionManager.decide(candidate_report, baseline_report)
        |
        +--> should_promote=False --> REJECTED (registry)
        |
        v
  ModelRegistry.promote_to_canary / promote_to_production
```

Every arrow above is a real, callable piece of code (see file references
throughout this document) except the "dataset version build" step, which is
deliberately a manual, human-run step for now - see "What's not automatic"
below.

## Feedback types

### Explicit feedback

A direct human judgment about a specific prediction. `FeedbackCategory`
(`backend/app/models/feedback.py` / `backend/app/interfaces/feedback.py`):

| Category | Meaning |
|---|---|
| `CORRECT` | The prediction was right (confirms it as ground truth). |
| `INCORRECT` | The prediction was wrong (no correction supplied). |
| `PARTIALLY_CORRECT` | Right in part, wrong in part. |
| `WRONG_INTENT` | The intent classification was wrong. |
| `WRONG_CONTEXT` | The context mode was wrong. |
| `WRONG_ACTION` | The chosen action was wrong. |
| `WRONG_CALLER_CLASSIFICATION` | KNOWN_CALLER/UNKNOWN_CALLER (or the relationship) was wrong. |
| `WRONG_SUMMARY` | A generated call summary was wrong/misleading. |
| `WRONG_RESPONSE` | The generated reply text was wrong. |
| `USER_CORRECTION` | A general correction not covered by a more specific category. |

Example (matches the worked example in the design spec): WOW predicts
`SET_CONTEXT / SLEEPING`. The user says "No, I'm actually in a meeting."
That becomes:

```json
{
  "predicted_intent": "SET_CONTEXT", "predicted_context_mode": "SLEEPING",
  "category": "wrong_context",
  "corrected_context_mode": "MEETING"
}
```

Another example: WOW identifies `UNKNOWN_CALLER`; the user says "That's
Rahul." That becomes:

```json
{
  "predicted_intent": "UNKNOWN_CALLER",
  "category": "wrong_caller_classification",
  "corrected_intent": "KNOWN_CALLER", "corrected_caller_name": "Rahul"
}
```

Note what's *not* stored: the raw phone number, or any other identifying
detail beyond what's needed to record the correction. See "Privacy" below.

### Implicit feedback

Inferred from behavior rather than stated directly. `ImplicitSignalType`:
`ACCEPTED_SUGGESTION`, `EDITED_SUMMARY`, `CHANGED_CONTEXT_AFTER_PREDICTION`,
`CORRECTED_CONTACT`, `CHANGED_ACTION`, `REJECTED_ACTION`, `TOOK_OVER_CALL`.

### Confidence weighting (`app/learning/confidence.py`)

Feedback signals are not all equally trustworthy, so every processed record
gets a `confidence_weight` used to rank/filter training candidates:

| Tier | Weight | Examples |
|---|---|---|
| Explicit | 1.0 (0.7 for `PARTIALLY_CORRECT`) | Any stated correction/confirmation |
| Implicit, direct edit | 0.8 | Accepted suggestion, edited summary, corrected contact, changed action |
| Implicit, weak behavioral signal | 0.4 | Changed context after prediction, rejected action, took over a call |

This is a fixed lookup table (`EXPLICIT_CONFIDENCE`/`IMPLICIT_CONFIDENCE`
dicts), not a learned value - feedback-signal trust and model-prediction
confidence are different things (see "Model confidence" below).

## Privacy and consent

**Mandatory, not optional**: production conversations do not become
training data automatically, full stop. Every `FeedbackEvent` defaults to
`consent_for_training=False`; a submission must explicitly set it `True`,
or the event is stored (for product review/active-learning purposes only)
and permanently rejected the moment `FeedbackProcessor` sees it - it never
proceeds past `RECEIVED`.

### The privacy pipeline

`FeedbackProcessor.process_one` (`backend/app/learning/feedback_processor.py`)
runs these checks, in order, on every `RECEIVED` event:

1. **Consent check** - `consent_for_training` must be `True`. Fails ->
   `REJECTED`, `rejection_reason="consent_not_given"`.
2. **Retention policy check** (`app/learning/retention.py`) - an event that
   sat unprocessed longer than `RetentionPolicy.max_age_days` (default 90)
   is treated as stale and rejected rather than processed late. Fails ->
   `REJECTED`, `rejection_reason="retention_expired"`.
3. **PII detection + redaction** (`app/learning/privacy_filter.py`,
   `RegexPrivacyFilter`) - regex-based detection/redaction of phone
   numbers, emails, card-like digit sequences, and OTP/PIN codes near their
   keyword. Always runs (not a failure condition); the redacted text is
   what gets stored as `redacted_text` and is the *only* text any later
   stage of the pipeline ever sees or writes to a file. `raw_text` never
   leaves the `FeedbackEvent` row.

A record that passes all three becomes `CANDIDATE` - **still not training
data**. It only becomes eligible for that at the next, explicit step.

### Privacy filter limitations

`RegexPrivacyFilter` is defense-in-depth, not a guarantee. It catches
common, high-confidence PII shapes (digit-pattern PII: phones, cards, OTPs;
emails) via regex. It does **not** attempt named-entity recognition, so a
name mentioned in running prose ("tell Rahul I called") is not redacted -
this is why the corrected-caller-name field is a separate, explicit
structured field (`corrected_caller_name`) rather than something the filter
is expected to find inside free text. Treat this filter as a floor, not a
ceiling; do not assume it makes arbitrary text safe to publish externally.

### Explicit human authorization

`CANDIDATE -> APPROVED` only happens via `FeedbackProcessor.approve(id,
reviewed_by=...)`, which:

- Requires a non-empty `reviewed_by` (an audit trail of *who* authorized
  each inclusion - never anonymous, never automatic).
- Only operates on records already in `CANDIDATE` status (i.e. that already
  passed consent/retention/redaction).

`TrainingCandidateBuilder` (`app/learning/candidate_builder.py`) then only
ever reads `APPROVED` records - never `RECEIVED` or `CANDIDATE`. This is
the literal enforcement of "must never automatically become training data
without explicit authorization": there is no code path that writes a
dataset file from anything less than consent + privacy filtering + a named
human's approval.

### Data-subject rights (`app/learning/privacy_rights.py`, `app/learning/personalization.py`)

| Right | How | Endpoint |
|---|---|---|
| Disable learning | Sets `User.training_data_consent=False` (the default for new submissions) | `PUT /feedback/consent` |
| Delete feedback | Hard-deletes `FeedbackEvent` row(s), any status | `DELETE /feedback` |
| Delete training candidates | Deletes `CANDIDATE`/`APPROVED` rows not yet merged into a dataset file | `DELETE /feedback/candidates` |
| Export feedback data | Returns every `FeedbackEvent` for the user | `GET /feedback/export` |
| See what's used for training | Returns `INCLUDED` events (+ which dataset batch) | `GET /feedback/used-for-training` |
| Reset learned personalization | Deletes the user's `Memory` rows | `POST /feedback/reset-personalization` |

**One honest limitation**: once a candidate reaches `INCLUDED` (it's been
written into a built, anonymized dataset file), it can no longer be
selectively pulled back out of that file - the file carries no user
linkage by that point, by design (see "Personalization vs. model training"
next). Deletion is only guaranteed for events that haven't yet reached
`INCLUDED`. This is a real, disclosed constraint, not glossed over.

## Personalization vs. model training

Two genuinely different systems, easy to conflate - kept structurally
separate:

**A. Personal memory / personalization.** "Aniket prefers family calls
treated as high priority" is a fact about *one user's* preferences. It
belongs in the existing `Memory`/`ContextProfile` system
(`backend/app/models/memory.py`, `backend/app/brain/context_engine.py`) and
is retrieved per-request by `ContextEngine.build_context`. It never touches
`FeedbackEvent`, never gets redacted/anonymized, and never requires
retraining any model - it changes behavior for that one user immediately,
the next time `ContextEngine` runs. `reset_personalization` clears exactly
this data.

**B. Global model improvement.** "WOW repeatedly misreads 'main thodi der
mein meeting mein ja raha hoon' as GENERAL_CONVERSATION" is a pattern
across (potentially many) users' authorized feedback. This is what the
`FeedbackEvent` -> privacy pipeline -> approval -> dataset -> retrain loop
above exists for. It's slow, batched, reviewed, and evaluated before it
changes anything - the opposite of personalization's immediate, per-user
effect.

Rule of thumb used throughout this codebase: if a signal is about *this
user's standing preference*, it's personalization (write it to
`MemoryStore` directly, as `WowBrain`/`ContextEngine` already do). If it's
evidence the *classifier itself* is wrong, it's a training signal (goes
through `FeedbackEvent`).

## Active learning

When a prediction's confidence is below a configurable threshold
(`Settings.intent_confidence_threshold` etc., default 0.6 per head), it's a
candidate for the review queue rather than being trusted outright.
`ConfidencePolicy.assess` (`app/learning/confidence.py`) makes that call
per-head (`intent`/`context`/`action` independently), returning which heads
are low-confidence.

A low-confidence prediction gets logged as a `FeedbackEvent` with
`status=NEEDS_REVIEW` (no feedback yet - just the prediction and its
confidences). The user-facing flow:

```
WOW thought: "SET_CONTEXT / SLEEPING" - was this correct?  [YES] [NO]
```

`GET /feedback/review-queue?user_id=...` lists a user's pending items;
`POST /feedback/{id}/respond` resolves one (`correct: bool` +, if not
correct, the actual labels), which converts it into ordinary explicit
feedback (`RECEIVED`, `category=CORRECT` or `USER_CORRECTION`) and
immediately runs it through the same privacy pipeline as any other
submission. This is deliberately a much higher-value labeling mechanism
than collecting large volumes of unreviewed data: every review-queue
response is a human-confirmed label on exactly the inputs the model was
least sure about.

**Model confidence is never treated as a correctness guarantee** - it only
gates whether WOW acts on a prediction directly vs. falls back to
safer/clarifying behavior and logs it for review. A confident wrong
prediction is still possible; that's what explicit feedback on *any*
prediction (not just review-queue ones) is for.

## Failure mining

`FailureMiner.mine` (`app/learning/failure_mining.py`) takes a batch of
feedback records with corrections and clusters them by
`(predicted_value, corrected_value)` per field (intent/context/action),
producing a ranked `FailureReport`:

```
intent_confusions:
  SET_CONTEXT -> GENERAL_CONVERSATION   (7)
  UNKNOWN_CALLER -> KNOWN_CALLER        (4)
  URGENT_CALL -> NON_URGENT_CALL        (2)
```

This is meant to directly inform hand-authoring in
`training/generation/build_seed_dataset.py:build_hard_negative_examples` -
a recurring confusion is exactly the shape of example that section already
exists to cover (see `docs/TRAINING.md`). It is a report to prioritize
human dataset-authoring effort, not something that writes examples itself.

## Dataset generation and versioning

`TrainingCandidateBuilder.build(batch_name)` writes
`training/datasets/feedback_candidates/<batch_name>.jsonl`, shaped
identically to `training/datasets/schemas/intent_example.py:IntentExample`
so it validates with the existing `training.preprocessing.validate`
tooling. It's kept in its own directory, separate from the hand-authored
`training/datasets/{intents,contexts,...}/seed.jsonl` - provenance (which
examples came from real feedback vs. were hand-authored) stays inspectable,
and the two are never silently merged. Producing a new combined dataset
version (seed + a chosen set of feedback-candidate batches) is a manual,
reviewed step - see "What's not automatic" below.

## Retraining and evaluation

Unchanged from `docs/TRAINING.md`: `training/training/train.py` trains a
new model version from whatever `training/datasets/processed/{train,val}.jsonl`
exists at the time, and `training/evaluation/evaluate.py` scores it against
the rule-based baseline and any prior version(s) side by side, including
per-intent accuracy, a full intent confusion matrix, and mode-collapse
detection. Nothing about the self-learning loop changes how training or
evaluation itself works - it only changes where the *dataset* comes from
(hand-authored seed, optionally plus approved feedback candidates).

## Model registry and versioning

`ModelRegistry` (`app/learning/model_registry.py`), backed by a single JSON
file (`training/models/wow-brain/REGISTRY.json` by default - no database
needed for this). Every entry (`ModelRegistryEntry`) records:

`model_id`, `version`, `base_model`, `dataset_version`, `training_config`,
`training_timestamp`, `metrics`, `dataset_commit_ref` (optional),
`status`.

Status lifecycle:

```
TRAINING -> EVALUATING -> CANDIDATE -> REJECTED
                                     -> CANARY -> PRODUCTION -> ROLLED_BACK
```

`promote_to_production` automatically rolls the previous `PRODUCTION`
version back to `ROLLED_BACK` (there is always at most one `PRODUCTION`
entry). `rollback_to(version)` re-promotes a prior version the same way -
rollback is just promotion of an older entry, so it goes through the exact
same code path (no special-cased "undo").

### What "canary" means today

`CANARY` is a registry *status* only. This codebase does not implement live
percentage-based traffic routing to a canary model version - that's real
infrastructure (request-level routing logic in `app/api/deps.py`'s provider
selection, plus metrics collection to decide when a canary graduates) that
doesn't exist yet. Setting a version to `CANARY` today means "this is the
next thing under manual evaluation before full promotion," a bookkeeping
state for a human-run rollout, not automated traffic splitting.

## Evaluation gate and promotion policy

`PromotionManager.decide(candidate_report, baseline_report)`
(`app/learning/promotion.py`) takes two provider entries shaped like
`training/evaluation/evaluate.py`'s report (`report["providers"][name]`)
and returns a `PromotionDecision` with every check's pass/fail reason -
not just the first failure, so a rejected candidate's full report is
visible at once. Default `PromotionPolicy`:

- `structured_output_validity` must be 1.0 (never regresses - 100% is
  already required today, see `docs/TRAINING.md`).
- `mode_collapse_suspected` must be `False`.
- No tracked metric (`intent_accuracy`, `context_accuracy`,
  `action_accuracy`, `ambiguous_unknown_accuracy`) may regress beyond its
  configured tolerance versus baseline (`max_intent_regression` defaults to
  `0.0` - **any** intent regression blocks promotion; context/action
  default to a small 2pp tolerance; unknown-accuracy to 5pp).
- Optionally, `min_intent_accuracy_gain` can require the candidate to beat
  baseline by a minimum margin, not just tie it.

**Worked example** (matches the spec this was designed against): a
candidate improves intent accuracy 82% -> 88% but regresses action accuracy
86% -> 73% (a 13-point drop, far beyond the 2pp tolerance). The decision is
`should_promote=False` - the intent gain does not buy back the action
regression. See `backend/tests/test_promotion.py` for this exact case
as an executable test.

The policy is a plain dataclass (`PromotionPolicy`) - every threshold is a
constructor argument, so a stricter or looser policy for a given release
doesn't require code changes.

## Continual learning: what this is, and what it deliberately is not

The full loop is intentionally offline and batched:

```
Production model -> Feedback buffer (FeedbackEvent, RECEIVED/CANDIDATE/APPROVED)
    -> periodic, human-run dataset build -> offline training.train
    -> evaluation.evaluate -> PromotionManager.decide
    -> ModelRegistry (CANARY -> PRODUCTION)
```

**Never implemented, and never should be without a much larger safety
review**: a live message immediately updating model weights. Online weight
updates from unreviewed traffic create catastrophic forgetting risk
(a handful of bad examples can silently degrade a model that took a
carefully balanced dataset to train), poisoning risk (anyone who can send
WOW a message could otherwise influence its weights), and unpredictable,
un-auditable behavior drift. Every step in this pipeline exists specifically
to prevent that: consent, redaction, human approval, offline retraining,
and an evaluation gate that can reject a regression before it ever reaches
production.

## What's not automatic (by design)

- Building a new dataset version from approved feedback candidates + the
  hand-authored seed is a manual step (no `DatasetVersionManager` that
  runs unattended).
- Running `training/training/train.py` on a new dataset is manual.
- `PromotionManager.decide` only recommends; nothing calls
  `ModelRegistry.promote_to_production` automatically - a human (or a
  deploy script a human triggers) does, after reading the decision.
- Canary traffic routing is not implemented (see above).
- None of this ever calls a hosted third-party AI API (OpenAI, Claude,
  Gemini, or otherwise) - WOW's training and inference stay fully
  self-hosted, matching the rest of this project's architecture (see
  `docs/ARCHITECTURE.md`).

## API summary

All under `/feedback` (`backend/app/api/routes/feedback.py`):

| Method | Path | Purpose |
|---|---|---|
| POST | `/feedback` | Submit explicit or implicit feedback; runs the privacy pipeline immediately. |
| GET | `/feedback/review-queue?user_id=` | List a user's active-learning review items. |
| POST | `/feedback/{id}/respond` | Resolve a review-queue item into explicit feedback. |
| POST | `/feedback/{id}/approve` | Human authorization: CANDIDATE -> APPROVED. |
| DELETE | `/feedback?user_id=&feedback_id=` | Delete feedback (one event or all for a user). |
| DELETE | `/feedback/candidates?user_id=` | Delete not-yet-included training candidates. |
| GET | `/feedback/export?user_id=` | Export all feedback for a user. |
| GET | `/feedback/used-for-training?user_id=` | List feedback actually included in a dataset. |
| PUT | `/feedback/consent` | Enable/disable the per-user training-data-consent default. |
| POST | `/feedback/reset-personalization?user_id=` | Clear learned personalization (Memory rows). |
