# WOW AI - Implementation status

Snapshot, not a final report - this file is updated as work continues, not
written once at the end. Every claim below is either backed by a passing
test in this repository or explicitly marked as not yet verified. See
README §3/§18 for the shorter, user-facing version of the same claims.

## 1. What was already in place before this round of work

A working Phase 1 backend: FastAPI + SQLAlchemy (async) + Postgres/pgvector
+ Redis, 9 domain models, provider interfaces (`app/interfaces/`) with zero
hosted-AI-API dependency, a rule-based reasoning provider and a
self-trained-model provider (`LocalWOWModelProvider`), `PgVectorMemoryStore`,
`DefaultContextEngine`, `WowBrain` v0 (a straight-line 3-step orchestrator),
and a fully built self-learning *pipeline scaffolding* - consent gating,
PII redaction, human-approved candidates, dataset versioning/checksums,
model registry with CANARY/PRODUCTION/REJECTED states, a regression-blocking
promotion gate, and data-subject rights (export/delete/disable-consent).
Also: the WOW Brain v3 dataset (66,000 checksummed examples), and an
Android app shell that round-trips a text command through the backend.

## 2. What this round of work implemented

All of the following is opt-in/additive - nothing pre-existing was
removed, renamed, or had its tested behavior changed. Full detail and
rationale for each is in `docs/ARCHITECTURE.md`; this is the checklist
view.

| Area | What was built | Where |
|---|---|---|
| Conversation state | Explicit, serializable `ConversationState` (lifecycle status, transcript, intent/context/candidate action, memory results, tool results, confidence) - never a hidden global | `backend/app/agent/state.py` |
| Memory safety | `memory_type` (episodic/semantic/contact/short_term), `status` (observed -> confirmed/user_approved), `confidence`, soft `deleted_at`; `/memories` API (create/list/delete/approve) | `backend/app/models/memory.py`, `interfaces/memory_store.py`, `api/routes/memories.py` |
| Policy engine | Deterministic ALLOW/CLARIFY/REFUSE/HANDOFF gate; out-of-taxonomy or low-confidence predictions are never trusted regardless of reported confidence; sensitive actions need a higher confidence bar | `backend/app/agent/policy.py` |
| Tool registry | Schema-validated, authorization-checked, timeout-bounded, audited tool invocation; two real tools (`save_memory`, `create_summary`) wired to existing stores | `backend/app/agent/tools.py`, `builtin_tools.py` |
| Agent orchestrator | `WowAgent` (opt-in, `AGENT_RUNTIME=wow_agent`): state -> memory-aware context -> brain -> confidence/validation -> policy -> tool execution -> response -> persisted state. Implements the same `AgentRuntime` contract as `WowBrain` v0 | `backend/app/agent/orchestrator.py` |
| Response generation | Verdict-aware fallback templates so a reply is never blank, even when the model predicts structure but no free text | `backend/app/agent/response.py` |
| STT/TTS/Telephony simulators | Deterministic local stand-ins for the previously contract-only interfaces - explicitly documented as simulators, never presented as real ASR/TTS/carrier integration | `backend/app/providers/{stt,tts,telephony}/simulated.py` |
| Simulated-call harness | Drives a scripted conversation through the real orchestration stack (only the audio source/sink is simulated) - the closest thing Phase 1 has to a demonstrable end-to-end call | `backend/app/simulation/call_simulator.py` |
| Call history persistence | `CallRecorder`: Call/Conversation/TranscriptSegment/Summary rows from a (simulated or, later, real) call | `backend/app/agent/call_recorder.py` |
| Observability | Per-stage latency (`context`/`brain`/`policy`/`tool`/`response`) + one structured log record per turn, whose signature has no text/transcript parameter at all | `backend/app/observability/` |
| Active learning wiring | Low-confidence `WowAgent` predictions now actually reach the pre-existing (previously untriggered) `NEEDS_REVIEW` queue | `backend/app/agent/orchestrator.py` (`_log_for_review`) |
| Call retention | `CallRetentionPolicy` (default 15 days) + `cleanup_expired_calls` - deletes a COMPLETED call's full history (Conversation/TranscriptSegment/Summary/AgentState) past the retention window; externally scheduled, no in-app scheduler | `backend/app/learning/call_retention.py`, `run_call_retention_cleanup.py` |
| Git hygiene | `kaggle-upload/` (a 1.6GB checkpoint + dataset staged for Kaggle upload) was untracked but not gitignored - fixed before it could be accidentally committed | `.gitignore` |

## 3. What remains external / not implemented

Stated plainly, matching README §18:

- **No real telephony, ASR, or TTS integration.** The simulators above make
  the orchestration layer real and testable; they are not a path to
  answering an actual phone call. Android `CallScreeningService`/
  `InCallService`, a self-hosted ASR engine (e.g. faster-whisper), and a
  self-hosted TTS engine (e.g. Piper/Coqui) are all still to be built.
- **`WowAgent` is opt-in, not the default** (`AGENT_RUNTIME=wow_brain` still
  is). It should only be promoted once it has run against more than
  simulated traffic.
- **No policy/tool coverage for most `Action` values yet** - only
  `SAVE_MEMORY` and `CREATE_SUMMARY` have real tools. `SET_CONTEXT`,
  `ANSWER_CALL`, `TRANSFER_CALL`, etc. are reported in the response
  payload but not executed, because executing them needs a real API-side
  effect (a `ContextProfile` write endpoint, real telephony) that doesn't
  exist yet - reporting without executing was the honest choice over
  faking it.
- **No real VAD/barge-in/interruption handling.** The simulated turn
  detection (sentence-ending punctuation) is a stand-in, not a timing
  model.
- **Mobile app unchanged this round** - still the pre-existing connectivity
  proof-of-concept.
- **v4 dataset/model pipeline not started** - v3's known confusion pairs
  (MESSAGE_FOR_USER vs SCHEDULE_REQUEST, etc.) are documented but no v4
  candidate data collection has begun.

## 4. Model artifact status - v3 artifact recovery attempt (verified against the actual local repo and the actual Kaggle account, not assumed)

**Local repo, as of this round:** `training/models/wow-brain/v3/` contains
**only an `intent/` head**, checkpointed at **14 of 20 configured epochs**
(best val accuracy 94.54% at epoch 10). There is no `context/` or
`action/` head for v3, and no `metadata.json`, so `LocalWOWModelProvider`
cannot currently load v3 - `MODEL_PROVIDER=rule_based` remains the default
for exactly this reason.

**Reported training history:** the project owner reports that WOW Brain
v3's Intent head was resumed and Context/Action were trained from scratch
on Kaggle (2x Tesla T4), reaching held-out test accuracy of 93.66%
(Intent) / 89.62% (Context) / 95.49% (Action) on the 66,000-example
`v3.3.0-answer-call` test set, and that a `wow-brain-v3-final.tar`
(~7.1GB, all three heads + evaluation reports) was created and verified
before the Kaggle session ended.

**Recovery attempt performed this round (via the Kaggle web UI, logged
in as `iamankoo`):**

1. `kaggle.com/work/code` -> exactly one notebook exists:
   `iamankoo/notebook914fc30194`. Opened it.
2. The notebook's read-only view reports **"No saved version"** - the
   author never ran "Save & Run All"/committed a version, so there is no
   persisted Output tab to pull artifacts from via `kaggle kernels output`.
3. Reconnected to the notebook's **live editor session** (a fresh, ~10-
   minute-old "Draft Session", GPU T4x2 selected as accelerator, input
   datasets `wow-ai-v3-3-0-answer-call` and `wow-ai-v3-intent-checkpoint`
   correctly attached - confirming this is the right notebook). Session
   options show **`Persistence: No persistence`** - on Kaggle this means
   `/kaggle/working` is wiped every time the interactive session resets;
   nothing survives across sessions unless a version is saved or files are
   explicitly exported.
4. Ran a live command in the session's Python console:
   `find /kaggle/working -maxdepth 6`. Output:
   ```
   /kaggle/working
   /kaggle/working/.virtual_documents
   /kaggle/working/.virtual_documents/__notebook_source__.ipynb
   ```
   No `training/` directory, no model files - matching the project
   owner's own report of what the current session shows. The Output panel
   independently corroborates this: **112KiB** total (not the multi-GB the
   trained artifacts would occupy).
5. Checked `kaggle.com/work/datasets` for a backup: only the same **two
   input** datasets exist (`wow-ai-v3-intent-checkpoint`, 833MB - the
   pre-training 14-epoch checkpoint; `wow-ai-v3-3-0-answer-call`, 4MB - the
   dataset manifests) - no output dataset was ever published from the
   completed run.
6. Checked `kaggle.com/work/models` (Kaggle's separate Models feature):
   **no models published.**

**Conclusion: the trained v3 artifacts (Context/Action heads, the
finished Intent head, and the `wow-brain-v3-final.tar` archive) are not
recoverable from any avenue available in this environment.** They existed
only on the ephemeral disk of an interactive Kaggle session with
persistence disabled, and were never checkpointed to a durable Kaggle
artifact (a saved notebook version, an output dataset, or a published
model) before that session was reset. This is not a "couldn't find it"
result - it is a definitive "the only remaining record of that session is
this empty working directory," confirmed directly against the live
Kaggle session, not inferred.

**Per instruction, no retraining was performed.** The training *history*
(hyperparameters, that it ran, the reported metrics) is treated as real
and should inform a future v3 restoration, but the *artifacts* themselves
must be produced again - there is nothing left to recover. If v3 is
restored in the future, the most direct path is resuming
`training/models/wow-brain/v3/intent/checkpoint.pt` (14 completed epochs,
still present locally) exactly as `docs/KAGGLE_TRAINING.md` describes,
this time **saving a Kaggle Dataset version of `training/models/wow-brain/v3/`
before the session ends** (`docs/KAGGLE_TRAINING.md` step 12B already
documents the command; it was not actually run for this training pass).

`docs/KAGGLE_TRAINING.md` has been updated with an explicit warning about
this exact failure mode for future runs.

## 5. Test results (this round, backend)

```
backend/tests/    151 passed, 8 skipped (skipped tests require a live TEST_DATABASE_URL -
                   no Postgres/Docker was available in this environment; the DB-dependent
                   tests were reviewed against the same working query patterns already
                   proven by the pre-existing DB-integration tests in the same file, but
                   were not run live)
training/tests/   249 passed (unaffected by this round - no training/ code was changed)
```

Every new module has both non-DB unit tests (fakes/in-memory doubles, no
database required) and, where the code touches Postgres, DB-integration
tests gated behind `TEST_DATABASE_URL` the same way the pre-existing ones
are.

## 6. Security review

A manual security review (no automated scanner available in this
environment) of every file changed this round found no high-confidence
new vulnerabilities - see the session's review notes. Summary: all new
queries are parameterized through SQLAlchemy, model-predicted
actions/tools are validated against a fixed taxonomy before being trusted,
memory mutations are scoped by `(user_id, memory_id)`, and no
`eval`/`exec`/`pickle`/`yaml.load`/subprocess was introduced. The new
`/memories` endpoints trust a caller-supplied `user_id` with no auth
check - but that matches the existing, pre-existing, app-wide trust model
of every other route (no authentication system exists yet anywhere in
this Phase 1 codebase), so it is not a new class of risk, just consistent
with the existing single-tenant-personal-use design.

## 7. Known limitations (repeated from README, kept in sync)

Do not treat anything in section 3 above as done. In particular: this
system cannot yet answer a real phone call, does not yet default to its
own trained model, and has no automated retention/cleanup for call data.

## 8. Next recommended step

In order of leverage: (1) decide whether to resume v3 training on a real
GPU (the artifacts and procedure are ready, see `docs/KAGGLE_TRAINING.md`)
or continue building agent capability against `rule_based`/`local_wow` v0/v1;
(2) add tools + policy coverage for `SET_CONTEXT` (would need a
`ContextProfile` write path) so more of the taxonomy is actually
executable, not just reported; (3) begin real STT integration (e.g.
faster-whisper) behind the existing `SpeechToTextProvider` interface,
since that is the actual blocker to a real (not simulated) call.
