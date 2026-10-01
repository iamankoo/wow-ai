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

## 4. Model artifact status - v3 RECOVERED: retrained on Kaggle, verified, and restored locally

**Timeline, in order:**

1. **Original artifact loss (documented in prior revisions of this file):**
   an earlier Kaggle training pass (all three heads, reportedly reaching
   ~93.66%/89.62%/95.49% intent/context/action test accuracy) was lost -
   the session had `Persistence: No persistence`, no notebook version was
   ever saved, and no backup dataset/model was published. A thorough
   recovery attempt (`kaggle.com/work/code`, the notebook's live console,
   `kaggle.com/work/datasets`, `kaggle.com/work/models`) confirmed nothing
   was recoverable - see git history for the full attempt log this section
   used to contain.
2. **Retraining, this round, on the user's explicit instruction ("start
   the training"):** using the same notebook
   (`iamankoo/notebook914fc30194`), the same input datasets
   (`wow-ai-v3-3-0-answer-call`, `wow-ai-v3-intent-checkpoint`), and the
   same procedure `docs/KAGGLE_TRAINING.md` documents, `training.training.train
   --config training/configs/model_config_v3.yaml --resume` was launched
   on GPU T4x2 - this time with session **persistence set to "Variables
   and Files"** before starting (the fix for the original loss mode), and
   the process launched as a detached background job
   (`subprocess.Popen(..., start_new_session=True)`) so it would survive
   any frontend disconnect.
3. **A real bug surfaced and was fixed mid-run:** resuming the local
   14-epoch intent checkpoint on Kaggle's GPU image raised
   `TypeError: RNG state must be a torch.ByteTensor` in
   `torch.set_rng_state` - a torch/numpy version mismatch between the
   checkpoint's origin (local CPU) and the resume environment (Kaggle
   GPU). Fixed in `training/training/train.py` (commit `a9a0a50`): each of
   the three RNG restores (python/numpy/torch) is now independently
   best-effort - a restore failure logs a warning and continues with a
   fresh RNG state for that generator, rather than aborting the whole
   resume and losing the real progress (model weights, optimizer state,
   epoch history). Pulled onto Kaggle (`git pull`) and training
   re-launched; ran to completion after that.
4. **One session interruption occurred mid-run** (Kaggle's frontend
   showed "Session is starting... / Starting container" partway through
   Context training) - this turned out to be a container restart that
   killed the in-progress process. Because persistence was now set to
   "Variables and Files", **the cloned repo, the dataset, and every
   epoch-level checkpoint already written survived the restart** - the
   only real loss was the one in-progress (uncompleted) epoch. Training
   was relaunched with `--resume` and picked up correctly per head
   (`[intent] resuming from checkpoint: epoch 16`,
   `[context] resuming from checkpoint: epoch 10`) - full detail was
   visible in session logs at the time; this file records the outcome.
5. **All three heads finished naturally via early stopping** (patience 4,
   `training/configs/model_config_v3.yaml`):

   | Head | Best val_accuracy | Best epoch | Final saved model reflects |
   |---|---|---|---|
   | Intent | 94.54% (original, epoch 10) | 10 | **Last** epoch (16), 94.27% - see caveat below |
   | Context | 91.62% | 10 | Best epoch (10), 91.62% |
   | Action | 95.61% | 8 | Best epoch (8), 95.61% |

   **Caveat, stated plainly:** Intent's final saved `model.safetensors`
   reflects its *last* trained epoch (16, 94.27% val accuracy), not its
   *best* epoch (10, 94.54%) - a 0.27 percentage point gap. This happened
   because `train.py`'s resume logic recovers "best so far" weights from
   `checkpoint_best.pt`, and only `checkpoint.pt` (not `checkpoint_best.pt`)
   was part of the originally-uploaded `wow-ai-v3-intent-checkpoint`
   Kaggle dataset, so there was nothing to seed `best_state` with when
   epoch 16 didn't beat epoch 10. The true epoch-10 weights **do** exist
   locally, in `training/models/wow-brain/v3_pre_kaggle_backup/intent/checkpoint_best.pt`
   (preserved, not deleted, when the new artifacts were swapped in) -
   recovering them would need a small script to load that checkpoint and
   re-export via `model.save_pretrained`/`tokenizer.save_pretrained`; not
   done this round since the gap is minor and this file must stay honest
   about what was actually verified, not what could additionally be done.

6. **Verified on Kaggle** (still on the live GPU session, immediately
   after training): every expected file exists with the right size
   (`metadata.json` 11,013 bytes; each head's `model.safetensors`
   ~541.3-541.4MB, `tokenizer.json` 2,919,625 bytes, small `config.json`/
   `tokenizer_config.json`); `metadata.json` correctly reports
   `model_version: v3`, `dataset_version: v3.3.0-answer-call`,
   `base_model: distilbert-base-multilingual-cased`, and each head's exact
   label count (intent=17, context=7, action=13, matching
   `backend/app/brain/taxonomy.py` exactly); each head was independently
   loaded via `transformers.AutoModelForSequenceClassification`/
   `AutoTokenizer` and ran a real forward pass with the correct output
   shape (`[1, 17]`/`[1, 7]`/`[1, 13]`). Finally, the **actual production
   class** - `backend.app.providers.llm.local_wow.LocalWOWModelProvider`,
   the same code `MODEL_PROVIDER=local_wow` uses in the real backend - was
   instantiated against the trained `v3/` directory and asked to classify
   "Please handle my calls, I am in a meeting": it returned
   `context_mode=MEETING`, `action=SET_CONTEXT`, with ~99.9% confidence on
   every head, `provider=local_wow_v0`, `model_version=v3` - zero external
   API calls.
7. **Transferred to the local machine and re-verified there, independently:**
   the deployable artifacts (all `config.json`/`model.safetensors`/
   `tokenizer.json`/`tokenizer_config.json` for all three heads, plus
   `metadata.json` - 1,508,625,116 bytes as one `.tar.gz`, checkpoint
   files excluded to keep the transfer small) were packaged on Kaggle and
   downloaded via the notebook's `IPython.display.FileLink` mechanism.
   **File sizes after extraction matched the Kaggle-side sizes exactly,
   byte for byte**, for all 13 files. The old, incomplete local `v3/`
   (intent-only, 14 epochs) was preserved at
   `training/models/wow-brain/v3_pre_kaggle_backup/` rather than deleted,
   and the new artifacts promoted to `training/models/wow-brain/v3/`.
   `LocalWOWModelProvider` was then re-run **locally** (not on Kaggle) -
   `backend/.venv`, CPU inference - against three test utterances in
   English and Hinglish:

   | Input | intent | context_mode | action |
   |---|---|---|---|
   | "Please handle my calls, I am in a meeting" | SET_CONTEXT | MEETING | SET_CONTEXT |
   | "Main so raha hoon, please handle karo" (Hinglish) | SET_CONTEXT | SLEEPING | SET_CONTEXT |
   | "Can you tell him I called about the invoice?" | GET_CONTEXT | MEETING | NO_ACTION |

   All three loaded and ran correctly locally, with no GPU and no
   external API - confirming the artifacts are genuinely portable, not
   an artifact of the Kaggle environment.

The numbers in the table above are **validation-set** accuracies (the
same `val.jsonl` split used for early-stopping decisions during
training) - see §4b immediately below for the genuinely held-out
**test-set** result, run in a later round.

Checkpoint files (`checkpoint.pt`/`checkpoint_best.pt`, needed only for
future resume/retraining, not for inference) were not brought down this
round, to keep the transfer small. With session persistence now set to
"Variables and Files" (unlike the original run), they should still be
present under `/kaggle/working/wow-ai/training/models/wow-brain/v3/` the
next time that Kaggle session is started, even though the session itself
was stopped (via Kaggle's "Stop session" control) at the end of this
round to free the GPU, per instruction.

`docs/KAGGLE_TRAINING.md` carries a top-of-file warning about the
original persistence failure mode, plus the RNG-restore fix, so a future
training pass doesn't repeat either issue.

## 4b. Held-out test-set evaluation (frozen `test.jsonl`, 6,785 examples) - verified

Run this round, on the project owner's explicit instruction, using the
locally-recovered v3 artifacts from §4. This is the genuinely independent
number §4 was missing: `test.jsonl` was never used for early-stopping
decisions or any other training-time choice, and this evaluation run
never writes to it or to the training loop - **checked directly**, not
just assumed: `test.jsonl`'s SHA-256 (verified against
`training/datasets/versions/v3.3.0-answer-call/MANIFEST.json` immediately
before this run) and byte content are identical before and after.

| Metric | rule_based baseline | **v3** | Previously reported (§4, unverifiable) |
|---|---|---|---|
| Intent accuracy | 5.13% (93.0% mode collapse to UNKNOWN) | **94.15%** | 93.66% |
| Context accuracy (n=6,466) | 4.59% | **90.86%** | 89.62% |
| Action accuracy (n=6,785) | 34.64% | **95.30%** | 95.49% |
| Structured output validity | 100.00% | **100.00%** | 100% |
| Ambiguous/unknown accuracy (n=125) | 100.00% | **96.00%** | 96.00% |
| Intent accuracy - Hindi | 0.09% | **94.56%** | 93.87% |
| Intent accuracy - Hinglish | 4.96% | **93.76%** | 93.62% |
| Intent accuracy - English | 9.70% | **94.13%** | 93.52% |

**This independently corroborates the retrain was not a fluke or a
regression from the originally-reported (lost) run** - every metric
lands within ~1.5 percentage points of what was reported before the
original artifacts were lost, and most (intent, context, per-language,
structured validity, ambiguous/unknown) match or slightly exceed it.
397 of 6,785 test examples were misclassified by intent (5.85% failure
rate); the full per-example failure list (text, language, expected vs.
predicted intent/context/action) is in the saved report for future v4
error analysis - see §29 of the original task brief's known confusion
pairs (`MESSAGE_FOR_USER` vs `SCHEDULE_REQUEST`, etc.), several of which
appear directly in this run's failures.

**How it was run:** CPU-only, unbatched (`LocalWOWModelProvider.generate()`
issues one forward pass per head per example, ~9.4 examples/sec on this
machine - 6,785 examples would take ~12 minutes as a single process,
longer than this environment's per-command execution budget allows). Split
into 4 sequential chunks via a temporary internal helper script
(`training/evaluation/_predict_chunk.py`, deleted after use - not part of
the permanent toolkit, purely a workaround for this session's execution
constraints), verified as a complete, gap-free, duplicate-free 0..6784
index range before scoring, then scored with `evaluate.py`'s real,
unmodified `_score`/`_valid_structured_output` functions - the same
methodology a single uninterrupted run would have used, not a different
one.

**Command for a future single-process rerun** (e.g. once running on a
machine/GPU without this session's execution-time constraints, or to
reproduce/spot-check this result):

```
python -m training.evaluation.evaluate \
    --config training/configs/model_config_v3.yaml \
    --model-dir v3=training/models/wow-brain/v3 \
    --split test \
    --output training/evaluation/v3_test_report.json
```

`evaluate.py` gained `--config` and `--split` this round (previously
hardcoded to v0's config and `val.jsonl` only) - see the module's
docstring. New tests:
`training/tests/test_evaluate_split_selection.py` (file-selection/wiring
only, no real model needed - split defaults to `val` unchanged,
`--split test` reads `test.jsonl` and never touches `val.jsonl`/
`train.jsonl`, invalid split raises, dataset-version detection reuses
`training.training.train._read_dataset_version` instead of the old,
v3-incompatible standalone copy this file used to have). Full report:
`training/evaluation/v3_test_report.json` (committed - real diagnostic
value for future v4 work, not a routine regenerable artifact like
`latest_report.json`).

**Still not promoted to default** - see §7/§8.

## 5. Test results (backend + training)

```
backend/tests/    151 passed, 8 skipped (skipped tests require a live TEST_DATABASE_URL -
                   no Postgres/Docker was available in this environment; the DB-dependent
                   tests were reviewed against the same working query patterns already
                   proven by the pre-existing DB-integration tests in the same file, but
                   were not run live)
training/tests/   254 passed (249 + 5 new, training/tests/test_evaluate_split_selection.py,
                   covering evaluate.py's --split/--config support added in §4b. Also
                   covers training/training/train.py's RNG-restore fix, commit a9a0a50 -
                   re-run and confirmed passing; that fix itself was validated for real
                   by the actual Kaggle GPU resume it was written to unblock, not just
                   by these pre-existing unit tests)
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
system cannot yet answer a real phone call, **still does not default to
its own trained model** (`MODEL_PROVIDER=rule_based` remains the default;
v3 is complete and verified but only loads when `MODEL_PROVIDER=local_wow`
is explicitly set - see §4), and has no automated retention/cleanup for
call data. Intent's deployed weights reflect its last trained epoch
rather than its best epoch (94.27% vs. 94.54%, see §4's caveat) - a minor,
documented gap, not a hidden one.

## 8. Next recommended step (superseded by §9's "Agent Core completion" work - kept for history)

v3 training is done and now has a genuine held-out test-set number (§4b:
94.15%/90.86%/95.30% intent/context/action, 100% structured validity) -
the remaining leverage is elsewhere. In order:
(1) **decide** whether to switch the default `MODEL_PROVIDER` from
`rule_based` to `local_wow` - the numbers clear the "matches or exceeds
the rule-based baseline" bar the codebase already checks for
automatically (`evaluate.py`'s own `RESULT:` line), so this is now a
product decision, not a missing-data blocker; if intent's known
last-epoch-vs-best-epoch gap (§4's caveat, 0.27pp) matters, recover the
true best-epoch weights from
`training/models/wow-brain/v3_pre_kaggle_backup/intent/checkpoint_best.pt`
first; (2) ~~add tools + policy coverage for `SET_CONTEXT`~~ **done, see §9**;
(3) begin real STT integration (e.g. faster-whisper) behind the existing
`SpeechToTextProvider` interface, since that is the actual blocker to a
real (not simulated) call - still not started, out of scope for the
current "Agent Core completion" round per explicit instruction.

## 9. Agent Core completion

Full repository audit (this round, before any code change) found the
agent orchestration layer was real but incomplete: only 2 of the
taxonomy's 13 actions (`SAVE_MEMORY`, `CREATE_SUMMARY`) had a real tool,
`SET_CONTEXT` - the most central action - was only ever *reported*, never
executed, and the `PolicyVerdict.CLARIFY` path was single-turn (a
low-confidence prediction was declined but never revisited). This round
closes those three gaps, in the dependency order the user specified, with
tests run and a doc/commit/push cycle after each block.

### Block 1: ContextProfile write path + real `SET_CONTEXT` tool

- `app/agent/context_profile_repository.py` (new): `ContextProfileRepository`
  ABC + `SqlContextProfileRepository` + `InMemoryContextProfileRepository`,
  the exact same pattern as `StateRepository`/`SummaryRepository`.
  `set_active` deactivates whichever other profile is active in the same
  `(user_id, contact_id)` scope and activates/creates the target one;
  `clear_active` deactivates without requiring a name (used by Block 2's
  `clear_context` tool).
- `SetContextTool` (`app/agent/builtin_tools.py`): validates `context_mode`
  against the taxonomy (`ContextMode.__members__`) before writing, in
  addition to the type check `Tool.validate` already does - a tool never
  trusts an out-of-taxonomy value, same principle `PolicyEngine` applies
  to actions.
- `_ACTION_TOOL_MAP[Action.SET_CONTEXT] = "set_context"` in the
  orchestrator, plus a `no_context_mode` guard (mirroring the existing
  `no_conversation_id` guard for `create_summary`) so a `SET_CONTEXT`
  prediction with no `context_mode` slot fails cleanly instead of hitting
  a generic type-validation error.
- `build_default_tool_registry` now takes a required
  `context_profile_repository` argument - updated at all 6 call sites
  (`api/deps.py`, `test_agent_orchestrator.py`, `test_call_simulation.py`
  x3, `test_integration_db.py` x2). Required, not defaulted to an
  in-memory fallback, so a caller can never silently get a
  throwaway-store "success" in production.

**Verified against a real database**, not just fakes:
`test_set_context_tool_writes_a_profile_default_context_engine_can_read`
(`backend/tests/test_integration_db.py`, gated behind `TEST_DATABASE_URL`)
drives a full `WowAgent` turn predicting `SET_CONTEXT`/`MEETING`, commits,
then independently re-reads the context through the pre-existing
`DefaultContextEngine` and confirms it sees the same row - proving the new
write path and the old read path actually agree, not just that each
compiles in isolation.

Tests after this block: 156 passed, 9 skipped (was 151/8 - +5 new unit
tests, +1 new DB-gated integration test). No regressions.

### Block 2: the remaining currently-defined agent tools

Completed every taxonomy action that can be given a genuine effect
without real telephony (see `orchestrator.py`'s `_ACTION_TOOL_MAP`
comment for the exact per-action rationale, reproduced here):

| Action | Treatment | Why |
|---|---|---|
| `CLEAR_CONTEXT` | Real tool (`clear_context`) | Same `ContextProfileRepository` as `SET_CONTEXT` (Block 1); `clear_active` deactivates without requiring a name - "already clear" is a success (0 cleared), not an error |
| `ENABLE_CALL_ASSISTANT` | Real tool (`enable_call_assistant`) | New `UserSettingsRepository` (ABC + SQL + in-memory, same pattern) writing a new `User.call_assistant_enabled` column (default `False` - opt-in, matching `training_data_consent`'s existing convention) |
| `DISABLE_CALL_ASSISTANT` | Real tool (`disable_call_assistant`) | Same repository, `enabled=False` |
| `COLLECT_MESSAGE` | Real tool (`collect_message`) | Reuses the existing `MemoryStore` (`source_type="caller_message"`, `memory_type=EPISODIC`) - no new store needed |
| `MARK_URGENT` | Real tool (`mark_urgent`) | Also reuses `MemoryStore` (`source_type="mark_urgent"`, `memory_type=SHORT_TERM`, content prefixed `"URGENT: "`) rather than adding a new schema column, since the existing store already models exactly this shape of fact |
| `ASK_CALLER_REASON` | Response-template only, no tool | Purely conversational - no store side effect to perform. `generate_response` gained an `action` parameter and `_ACTION_TEMPLATES` so this action gets a real question ("Could you tell me the reason for your call?") instead of the generic fallback |
| `NO_ACTION` | No tool (unchanged) | A no-op by definition |
| `ANSWER_CALL` / `TRANSFER_CALL` / `END_CALL` | **Still deferred, unchanged** | Genuinely require real telephony, explicitly out of scope for this round per instruction ("do not start ... telephony ... yet"). `TRANSFER_CALL` already gets a `HANDOFF` policy verdict for unknown callers (pre-existing, `PolicyEngine`) - only the actual carrier-side effect is missing |

`build_default_tool_registry` now takes a required `user_settings_repository`
argument (same required-not-defaulted rationale as Block 1's
`context_profile_repository`) - updated at all 6 call sites again.

New tests: `test_agent_tools.py` (+6, one per new tool plus the
"clearing when nothing was active is still a success" edge case),
`test_agent_orchestrator.py` (+3, end-to-end through the full `WowAgent`
stack for `COLLECT_MESSAGE`/`ENABLE_CALL_ASSISTANT`/`ASK_CALLER_REASON`),
new `test_agent_response.py` (+8, direct coverage of `generate_response` -
previously untested in isolation, only exercised indirectly), and a new
DB-gated `test_user_settings_repository_persists_call_assistant_flag` in
`test_integration_db.py` confirming the write survives a real commit and
that a nonexistent user_id returns `False` rather than raising.

Tests after this block: 173 passed, 10 skipped (was 156/9 - +17 new unit
tests, +1 new DB-gated integration test). No regressions.

### Block 3: genuinely multi-turn clarification loop

Before this block, `PolicyVerdict.CLARIFY` was single-turn: a
low-confidence prediction was declined with a generic "could you say that
again?" and then completely forgotten - the next turn re-derived
everything from scratch with no memory that a specific action had been
suggested. This block makes the loop actually multi-turn:

- `app/agent/confirmation.py` (new): `interpret_confirmation(text) ->
  bool | None` - a small, fixed-vocabulary, fully deterministic yes/no
  matcher (never a hosted LLM call, same "boring and testable" spirit as
  `PolicyEngine`/`ConfidencePolicy`). Returns `True`/`False`/`None`
  (neither - treat as an unrelated fresh turn).
- `ConversationState.pending_action` (new field, `dict | None`,
  round-trips through `to_dict`/`from_dict` like every other field): when
  a fresh turn lands on CLARIFY with an actionable (just
  under-confident) candidate, `{"action", "context_mode", "intent"}` is
  remembered here for the next turn.
- `WowAgent.handle_input` now checks `state.pending_action` before doing
  anything else:
  - **affirmative** -> skip the brain call entirely, treat the
    remembered action as fully trusted (`ConfidenceAssessment(needs_review=False)`,
    `overall_confidence=1.0` - the explicit human confirmation supersedes
    the original low score), run it through the same policy+tool
    pipeline as any other turn. `generate_response` gained a `confirmed`
    flag and says "Got it - I've taken care of that." rather than a
    generic fallback.
  - **negative** -> a new fast path, `_resolve_cancelled_clarification`,
    skips the brain/policy/tool pipeline entirely (there is nothing left
    to do) and replies with the fixed `CANCELLED_ACKNOWLEDGEMENT`
    ("Okay, I won't do that."), exported from `app/agent/response.py` so
    every user-facing string still lives in one module.
  - **neither** (unclear reply) -> the stale suggestion is abandoned
    (`pending_action` cleared) and the turn is reprocessed fresh through
    the brain, exactly as before this block - never force-matched as a
    confirmation just because something was pending.
- Still respects existing safety gates: `PolicyEngine.evaluate` is still
  called even on a confirmed turn (with `overall_confidence=1.0`), so
  e.g. `TRANSFER_CALL` from an unrecognized caller still correctly gets a
  `HANDOFF` verdict rather than being blindly executed just because the
  caller said "yes".

New tests: `test_confirmation.py` (+26, the full affirmative/negative/
unrelated/None matrix), `test_agent_state.py` (+2, `pending_action`
defaults to `None` and round-trips), `test_agent_response.py` (+4, the
`confirmed` flag and its precedence versus `tool_failed`/action
templates), `test_agent_orchestrator.py` (+4, full end-to-end through
`WowAgent`: confirm executes the previously-clarified `SET_CONTEXT`,
cancel never executes it and never calls the LLM provider again, and an
unrelated reply reprocesses fresh rather than being misread).

Tests after this block: 209 passed, 10 skipped (was 173/10). No
regressions.

### Block 4: full agent integration test using the recovered WOW Brain v3

Everything in Blocks 1-3 had only ever been exercised with fakes
(`FakeLLMProvider`) or the deterministic `RuleBasedLanguageModelProvider`
- proving the orchestration logic works, never that it works when driven
by the actual trained model. This block closes that gap:
`backend/tests/test_agent_integration_v3.py` constructs a real
`LocalWOWModelProvider` against the actual recovered artifacts at
`training/models/wow-brain/v3/` (not a fake, not `rule_based`) and drives
a full `WowAgent` (real `PolicyEngine`, real `ToolRegistry` with every
tool from Blocks 1-2, in-memory storage) through five turns:

- The exact three utterances this session's manual Kaggle-recovery
  verification used (§4) - "Please handle my calls, I am in a meeting"
  (English), "Main so raha hoon, please handle karo" (Hinglish), "Can you
  tell him I called about the invoice?" - now run as an **automated
  regression test** instead of a one-off manual check, asserting the
  same predictions (`SET_CONTEXT`/`MEETING`, `SET_CONTEXT`/`SLEEPING`,
  `NO_ACTION`) reproduce exactly, and that the first two actually
  activate the corresponding `ContextProfile` through the real
  `set_context` tool - closing the loop from "the model predicts
  correctly" (held-out test evaluation, §4b) to "the agent built around
  it behaves correctly when driven by that real prediction."
- A gibberish-input robustness check: whatever the real model predicts
  for out-of-distribution text, the turn must complete without raising
  and every reported action must still be taxonomy-valid or `None` -
  proving `is_valid_action` holds against genuine model output, not just
  against fakes already engineered to be valid.
- A two-turn state-persistence check against the real model.

Gated the same way `test_integration_db.py` is gated on
`TEST_DATABASE_URL`: `pytest.mark.skipif` on the model directory's
`metadata.json` not existing (expected on a fresh checkout -
`training/models/` is gitignored) plus `pytest.importorskip("transformers")`
- skips cleanly rather than failing when the real artifacts/dependencies
aren't present, and never substitutes a fake for this test's purpose.
`MODEL_PROVIDER` is untouched by this test (it constructs
`LocalWOWModelProvider` directly) and remains `rule_based` in
`app/config.py` - **still not the default**, per instruction.

All 5 new tests pass against the actual local model (~20s including
three real `AutoModelForSequenceClassification.from_pretrained` loads).

Tests after this block: **214 passed, 10 skipped** (was 209/10 - +5 new,
all executed for real, not skipped, since the recovered v3 artifacts are
present in this environment). `training/tests/`: 254 passed, unchanged
(no training-side code touched this round). No regressions anywhere.

### Agent Core completion - summary

All four blocks done, in the dependency order specified, with tests run
and a doc/commit/push cycle after each: `SET_CONTEXT` and every other
taxonomy action that can be given a genuine effect now has a real,
tested tool (only `ANSWER_CALL`/`TRANSFER_CALL`/`END_CALL` remain
deferred, correctly, pending real telephony); the clarification loop is
genuinely multi-turn; and the full stack is now proven against the real
trained model, not just fakes. Backend test count: 151 -> 214 passed (63
new tests), 8 -> 10 skipped (both DB-gated, +2 new DB-gated tests never
run live in this environment for the same pre-existing reason - no
`TEST_DATABASE_URL`). `AGENT_RUNTIME` remains `wow_brain` and
`MODEL_PROVIDER` remains `rule_based` - both still opt-in, per
instruction; promoting either is a product decision for a future round,
not something this round changed.

## Phase 2 — real voice + Android call pipeline

Environment capability verified first (Android SDK/ADB/emulator all
functional; Flutter/Java toolchain present via the installed Android
Studio) before any implementation began.

### Block 1: fix the Android build blocker

`AndroidManifest.xml` referenced `@mipmap/ic_launcher`, but `res/`
contained only `values/styles.xml` - no launcher-icon resources existed
anywhere, so `flutter build apk --debug` failed AAPT resource linking.
Fixed with the standard 5-density `ic_launcher.png` set
(mdpi/hdpi/xhdpi/xxhdpi/xxxhdpi), generated via .NET `System.Drawing` -
no new dependency, no UI/architecture change. Also committed the
previously-missing Gradle wrapper (`gradlew`/`gradlew.bat`/
`gradle-wrapper.jar` - only `gradle-wrapper.properties` was tracked
before) and `pubspec.lock` for reproducible builds.

**Verified for real:** `flutter build apk --debug` succeeded (97.8s
Gradle task); `adb install` succeeded on the running
`Medium_Phone_API_36.1` emulator; `adb shell am start` returned
`result code=0`; the process stayed alive with a stable PID across
repeated checks; logcat showed zero `FATAL EXCEPTION`/`AndroidRuntime`/
ANR signatures; `flutter test` still passes (1 test, unchanged).

Commit: `648ff1a`.

### Block 2: real STT (`LocalWhisperSTTProvider`)

Implements the pre-existing `SpeechToTextProvider` contract
(`backend/app/interfaces/stt.py`, contract-only until now) using
**faster-whisper** (CTranslate2-accelerated Whisper) - self-hosted, zero
hosted speech API. `SimulatedSTTProvider` is untouched and remains
available as a deterministic test double; this is the genuine engine.

- `backend/app/providers/stt/local_whisper.py`: lazy-imports
  faster-whisper/ctranslate2 (matching `LocalWOWModelProvider`'s
  discipline - a deployment that never enables real STT needs neither
  installed); own CTranslate2-native device resolver (`_resolve_stt_device`,
  deliberately independent of `app.ml.device.resolve_inference_device`,
  which requires torch - faster-whisper does not); raises
  `STTNotAvailableError` at construction if the library is missing or the
  model fails to load, never a silent fallback.
- Audio contract (the interface itself doesn't specify one beyond "raw
  bytes" + a separate `sample_rate`): raw 16-bit signed little-endian
  PCM, mono - documented explicitly in the module.
- Language: defaults to per-utterance auto-detection (`language=None`) -
  the honest choice for code-switched Hindi/English (Hinglish) speech,
  since Whisper has no dedicated "Hinglish" mode; a specific language can
  still be forced via the constructor.
- **Streaming honesty**: faster-whisper cannot produce a genuine partial
  transcript from one audio chunk. `feed()` buffers and returns `None`
  rather than fabricating a partial result; `close()` runs one real
  transcription over everything buffered. The interface's chunked-delivery
  contract is honored; only the partial-result promise is left honestly
  unfulfilled, consistent with "do not fake functionality".
- Confidence: derived from Whisper's `avg_logprob` via `exp()`, clamped
  to `[0,1]` - an approximation, documented as such.

**Real audio fixtures, not mocks:** `backend/tests/fixtures/audio/{hello,meeting_context}.wav`
were synthesized via Windows' built-in `System.Speech` SAPI (no new
dependency) with known text content, then actually transcribed by the
real local model:

| Fixture | Spoken text | Real transcription |
|---|---|---|
| `hello.wav` | "Hello, can you hear me?" | "Hello, can you hear me?" (exact) |
| `meeting_context.wav` | "I am in a meeting, please handle my calls." | "I am in a meeting. Please handle my calls." (punctuation-only difference) |

**Honest limitation**: only English (`en-US`) SAPI voices are installed
in this environment, so no real Hindi/Hinglish audio fixture could be
synthesized to verify transcription accuracy on those languages - the
model is genuinely multilingual (Whisper) and the language-handling code
path is real, but Hindi/Hinglish transcription *accuracy* is unverified
here, not fabricated as tested.

Model (`Systran/faster-whisper-base`) downloads to the platform's
Hugging Face cache (outside the repo, never git-tracked) on first use -
confirmed via `git status` showing no new artifacts after running it.
New optional dependency file: `backend/requirements-local-stt.txt`
(`faster-whisper`, `numpy`).

11 new tests, all passing against the real model (not mocks):
`backend/tests/test_local_whisper_stt.py` - real transcription of both
fixtures, empty-audio rejection, non-native-sample-rate resampling,
full streaming-session lifecycle (buffer/close/double-close/feed-after-close),
device-resolution validation, and construction failing loudly for an
invalid model name. Gated with `pytest.importorskip("faster_whisper")` -
skips cleanly (not fails) if the optional dependency isn't installed,
matching the `TEST_DATABASE_URL`/v3-model-gated pattern used elsewhere.

Tests after this block: **225 passed, 10 skipped** (was 214/10).
`training/tests/`: unchanged. No regressions.

### Block 3: real TTS (`LocalPiperTTSProvider`)

Implements the pre-existing `TextToSpeechProvider` contract
(`backend/app/interfaces/tts.py`, contract-only until now) using
**Piper** (a fast, self-hosted ONNX-based neural TTS engine) - zero
hosted TTS API. `SimulatedTTSProvider` is untouched and remains the
deterministic test double.

- `backend/app/providers/tts/local_piper.py`: lazy-imports `piper`
  (same discipline as the STT/model providers); voices resolved by
  Piper's own naming convention (`en_US-lessac-medium`,
  `hi_IN-pratham-medium`, ...) and downloaded on first use via piper's
  own `download_voice()` helper into `~/.cache/wow-ai/piper-voices/`
  (outside the repo, never git-tracked, `auto_download` can be disabled
  for environments that must pre-provision voices); each resolved
  voice's `PiperVoice` is cached in memory after first load; raises
  `TTSNotAvailableError` if piper is missing, a voice can't be
  downloaded/loaded, or synthesis produces nothing - never a silent
  fallback.
- CPU-bound synthesis is offloaded via `asyncio.to_thread` so it never
  blocks the event loop other in-flight requests share.
- `stream_synthesize` genuinely streams: it pulls Piper's own
  synchronous chunk generator one chunk at a time (each `next()` also
  via `asyncio.to_thread`) rather than materializing the whole utterance
  first, unlike STT's honestly-non-streaming `feed()` (Piper, unlike
  Whisper, *can* produce audio incrementally, so streaming here is real,
  not a documented limitation).
- Added `get_sample_rate(voice=None)` - additive, not an ABC change
  (`TextToSpeechProvider` has no field for it) - the media pipeline
  (Block 5) needs this to interpret the raw PCM bytes `synthesize()`/
  `stream_synthesize()` return, since the interface returns bytes with
  no format metadata.

**Real synthesis verified, not mocks**, including genuine multilingual
proof (WOW's domain is English/Hindi/Hinglish): a representative WOW
agent response ("Got it - I've taken care of that.") was synthesized
with the real `en_US-lessac-medium` voice, written to an actual WAV file,
and **reopened and re-validated as genuinely playable PCM audio**
(correct channels/sample width/rate, >0.3s real duration - not
near-silence); a second real voice, `hi_IN-pratham-medium`, synthesized a
Hindi sentence and produced audibly different, non-empty output,
proving voice switching resolves to a genuinely different model rather
than relabeling cached bytes.

7 new tests, all passing against real models:
`backend/tests/test_local_piper_tts.py` - WAV-artifact validity,
empty-text rejection (both `synthesize` and `stream_synthesize`), real
streamed chunks, sample-rate reporting, real Hindi voice switching, and
a missing-voice-without-auto-download failure path. Gated with
`pytest.importorskip("piper")`.

Tests after this block: **232 passed, 10 skipped** (was 225/10).
`training/tests/`: unchanged. No regressions.

### Block 4: real VAD / barge-in (`WebRtcVoiceActivityDetector`)

Unlike STT/TTS/telephony, **no interface existed for this at all** -
Phase 1's "turn detection" was a punctuation heuristic living inside
`SimulatedSTTProvider`, explicitly documented there as a stand-in, never
meant to survive into real audio. This block adds the missing interface
(`backend/app/interfaces/vad.py`, following the exact same ABC pattern as
`SpeechToTextProvider`/`TextToSpeechProvider`/`TelephonyProvider`) and a
real implementation - **not left as the punctuation heuristic**, per
instruction.

- Engine: Google's **WebRTC VAD** - a genuine, deterministic
  signal-processing classifier purpose-built for real-time voice-call
  audio (this project's exact domain), not a fake/heuristic stand-in and
  not a neural model requiring a download. Installed as
  `webrtcvad-wheels` (prebuilt wheels; the original `webrtcvad` package
  needs a C++ build toolchain this machine doesn't have - same
  underlying algorithm/API either way, documented in
  `requirements-local-vad.txt`).
- `VadStreamSession` (per-call, stateful): `feed()` accepts **any chunk
  size** (buffers internally to WebRTC's required fixed frame size -
  10/20/30ms), `notify_playback_started`/`notify_playback_stopped` (so
  the session can tell speech-starting-while-WOW-is-talking apart from
  ordinary speech-start), `reset()` (clears speech/silence state for a
  new turn, deliberately leaves the playback-active flag untouched -
  that flag isn't part of the utterance state machine).
- Events: `SPEECH_START`, `SPEECH_END`, `SILENCE` (sustained "dead air"
  with no speech at all this turn - distinct from `SPEECH_END`, which is
  a pause *after* speech), `BARGE_IN` (speech starting during active
  playback). Debounced (2 frames/60ms to confirm speech genuinely
  started, 10 frames/300ms to confirm a pause is really the end of turn)
  so single noisy/silent frames can't flip state.
- **A real bug found and fixed during testing**: the first `feed()`
  implementation processed every complete frame in one call but only
  returned the *last* event, silently dropping earlier ones whenever a
  single call's buffer crossed more than one state transition (e.g. an
  entire pre-recorded utterance fed as one chunk - the exact case the
  first test run against the real fixture caught). Fixed by having
  `feed()` stop and return as soon as one event occurs, leaving any
  remaining already-buffered frames for the *next* `feed()` call -
  matches how a real continuous audio stream would deliver events over
  time, and no event is ever silently lost regardless of how a caller
  chunks its input.

**Verified against real speech, not synthetic tone/silence alone:** run
directly against Block 2's real `meeting_context.wav` fixture (the same
"I am in a meeting, please handle my calls." utterance, itself real
recorded-equivalent speech, not silence) - correctly detects
`SPEECH_START` at 0.12s (after the fixture's brief leading room-tone) and
`SPEECH_END` at 3.15s of 3.535s total (after the trailing pause), with no
audio content inspected beyond raw PCM frames.

9 tests, all passing: `backend/tests/test_webrtc_vad.py` - real-fixture
speech-start/end sequencing, arbitrary/ragged chunk-size delivery,
sustained-silence single-event firing, barge-in detection (and its
absence when playback was stopped first), `reset()`'s
playback-flag-survives behavior, and sample-rate/frame-duration/
aggressiveness validation. Gated with `pytest.importorskip("webrtcvad")`,
matching the optional-dependency pattern used for STT/TTS.

Tests after this block: **241 passed, 10 skipped** (was 232/10).
`training/tests/`: unchanged. No regressions.

### Block 5: integrate the media pipeline

Wires `audio in -> VAD -> STT -> WowAgent -> TTS -> audio out` for the
first time - every real provider from Blocks 2-4 was previously only
verified in isolation against its own interface; `app/media/pipeline.py`
(`MediaPipeline`) is the first thing that actually connects them to each
other and to the pre-existing, already-real `WowAgent`/WOW-Brain-v3 stack
from Agent Core. Deliberately does **not** touch call control
(`TelephonyProvider.answer_call`/`end_call`, Android
`CallScreeningService`/`InCallService`) - that's Block 6; this is purely
the media-processing layer a real telephony integration would sit on top
of, built entirely from existing provider interfaces
(`SpeechToTextProvider`/`TextToSpeechProvider`/`VoiceActivityDetector`/
`AgentRuntime`), so it works identically whether given the Phase 1
simulators or Phase 2's real implementations.

`MediaPipeline.process_call_audio()` feeds a chunked audio stream (any
chunk size, sync or async iterable) through a VAD session; on each
confirmed `SPEECH_END`, the captured caller audio is transcribed via the
real STT provider, the transcript is sent to the real agent, and the
agent's reply text is synthesized via the real TTS provider - one
`PipelineTurn` (transcript, agent action, reply audio, reply sample rate)
per completed utterance. Trailing audio with no closing silence (a
stream that just ends) is still finalized rather than silently
discarded. `get_sample_rate()` (Block 3's additive `LocalPiperTTSProvider`
helper, not part of the `TextToSpeechProvider` ABC) is used
opportunistically via `getattr`, never required - the pipeline still
works with a TTS provider that doesn't expose it.

**Verified as a genuine, unbroken real chain - "close the loop" for
Blocks 2-5**: `backend/tests/test_media_pipeline.py` feeds the same real
`meeting_context.wav` fixture (Block 2/4's fixture) through the actual
`MediaPipeline` wired with `WebRtcVoiceActivityDetector`,
`LocalWhisperSTTProvider`, a real `WowAgent` backed by the recovered WOW
Brain v3 (`LocalWOWModelProvider`, the same real model Agent Core Block 4
integration-tested directly), and `LocalPiperTTSProvider` - and confirms,
end to end:

1. **Real STT**: the actual spoken words ("meeting") were transcribed
   from real audio, not supplied as text.
2. **Real WOW Brain v3 + real Agent Core**: the same `SET_CONTEXT`/
   `MEETING` prediction Agent Core Block 4 verified via direct text
   input is now reached via real audio instead - `set_context` tool
   executes, `ContextProfile` shows `MEETING` active.
3. **Real TTS**: the agent's reply was genuinely synthesized (non-empty
   audio, correct sample rate), written to an actual WAV file, and
   reopened/re-validated as genuinely playable PCM audio - the same
   rigor as Block 3's TTS artifact test, now reached through the full
   pipeline rather than called directly.

A second test confirms silence-only input produces zero turns and never
spuriously invokes the agent or TTS.

Gated on the same three optional real components this block connects
(`pytest.importorskip("faster_whisper")`, `pytest.importorskip("piper")`,
and the v3 model directory's presence) - skips cleanly, never fakes any
of them.

Tests after this block: **243 passed, 10 skipped** (was 241/10).
`training/tests/`: unchanged. No regressions.

## Note: this file was not kept in sync for Phases 3-8

Real work landed in git history well beyond Block 5 above (activation
durations, real Android `CallScreeningService`/`TelecomManager`
auto-answer verified on a physical device, real call history, Render
production deployment, Agent Core's full tool/policy/clarification
completion) without corresponding entries here. Read `git log` and the
code directly for anything between Block 5 and the round below; this gap
is stated rather than silently left to look like nothing happened.

## Real-telephony investigation + zero-cost prep (2026-09-17)

On explicit instruction to investigate what's needed for WOW to hold a
real two-way conversation with an actual caller (not a simulated one),
and to stop before spending any money.

**Investigation** (full repository read, backend test suite run - 259
passed/29 skipped before any change, confirming nothing was already
broken): confirmed `TelephonyProvider` has no real implementation (only
`SimulatedTelephonyProvider`), and that Android's `CallScreeningService`/
`TelecomManager.acceptRingingCall()` path (real, already working on a
physical device) cannot be extended to carry real GSM call audio -
`MediaRecorder.AudioSource.VOICE_CALL` is OS-restricted to
privileged/carrier apps for any third-party app, confirmed against the
existing code's own honest documentation of this
(`WowCallScreeningService.kt`). Recommended architecture: carrier
no-answer call forwarding to a telephony-provider virtual number with
real-time bidirectional streaming, bridged into the already-real
`MediaPipeline`/`WowAgent`/Piper stack - full detail and rationale in
`docs/ARCHITECTURE.md` "Real telephony - the missing seam".

**Provider/cost research** (live pages checked, not memory): Twilio ruled
out for this use case - its own India voice-pricing page marks inbound
unsupported for Local/Mobile Indian numbers. Exotel supports real inbound
PSTN + bidirectional streaming but publishes no self-serve pricing
(enterprise "book a demo" product); getting a real quote needs a direct
sales conversation, not done this round. Render's pricing page (checked
live): free plan spins down after 15 minutes idle (in addition to the
already-known RAM ceiling that OOM-crashed real STT once in production,
commit `d9bcb08`); realistic paid minimum for Brain v3 + Whisper + Piper
together is the $25/mo 2GB "Standard" plan. No purchase made - reported to
the project owner, awaiting a decision.

**Implemented this round** (zero paid credentials required):

- `WowAutoAnswer.kt`'s human-first auto-answer wait: 10s -> 5s, matching
  the product spec's "~5 seconds" (previously tuned to 10s during Phase
  5/8 real-device verification - the delay's actual verified magnitude,
  not its exact value, was what that testing proved out).
- `MediaPipeline.stream_call_audio()` (`app/media/pipeline.py`, new): the
  provider-agnostic streaming counterpart to the pre-existing
  `process_call_audio` - yields each `PipelineTurn` the instant VAD
  confirms that utterance ended, rather than only once the entire audio
  source is exhausted. `process_call_audio` is now a thin wrapper around
  it (`[turn async for turn in stream_call_audio(...)]`) - its existing
  contract (list, once the source ends) is unchanged and covered by the
  same tests as before. This is the real gap a live telephony bridge
  needs closed regardless of which provider is eventually chosen: a
  caller must hear WOW's reply while the call is still open, not only
  after it ends. New tests, all fast/ungated (simulated STT/TTS/VAD, no
  heavy ML deps): `backend/tests/test_media_pipeline_streaming.py` (+3) -
  proves a turn is yielded without its audio source ever ending (an
  `asyncio.Event().wait()` that never resolves, read via
  `asyncio.wait_for(..., timeout=5.0)` on the first yielded value only),
  multi-turn ordering, and the `process_call_audio` regression check.
- Deliberately **not** written: any vendor-specific `TelephonyProvider`
  (Twilio/Exotel/other). No provider is chosen yet and no credentials
  exist to test against - writing one now would be exactly the "fake
  functionality" this project's engineering principle forbids, since it
  could never actually be exercised against anything real.
- `docs/ARCHITECTURE.md`, this file, and `README.md` updated to state the
  real current status plainly (Phases 3-8's real work was previously
  undocumented here - see the note above) and record this investigation
  so a future session doesn't have to re-derive it.

Tests after this round: **262 passed, 29 skipped** (was 259/29 - +3 new,
all executed, none skipped). No regressions.

## Real Plivo telephony bridge (2026-09-17)

Verified Plivo against its official docs (not the prior lighter research
pass) before writing any code - full quoted findings in
docs/ARCHITECTURE.md "Real telephony" and docs/PLIVO_TESTING.md. Then
implemented the real bridge, on explicit instruction, with a working local
test procedure (`docs/PLIVO_TESTING.md`) for a PC + Cloudflare Tunnel +
Plivo trial real phone call - no Render upgrade, no purchase made by the
agent.

**Context-instructions gap closed** (the one open decision flagged at the
end of the prior round): `ContextProfile` gained `user_instructions`
(nullable `Text`, `backend/app/models/context.py`) - the caller's own
literal words when they set a context (e.g. "ask why they called, take a
message, only mark it urgent if necessary"), captured alongside, not
instead of, the fixed per-`ContextMode` `instructions` description that
already drove policy/response-template behavior unchanged.
`ContextProfileRepository.set_active` (ABC + SQL + in-memory) gained an
optional `user_instructions` parameter; `SetContextTool.run`
(`app/agent/builtin_tools.py`) captures it from the tool's (optional, not
in `schema` - every existing caller unaffected) `user_instructions`
argument, treating blank/whitespace as "nothing captured" rather than a
real instruction. `WowAgent._build_tool_arguments` passes the turn's raw
text through - a real correctness fix surfaced along the way, not just
new capability: `ConversationState.pending_action` now also stores the
*original* turn's text (`"text"` key), because the turn that actually
*confirms* a clarified action just says "yes" - before this, a confirmed
`SET_CONTEXT` (or `SAVE_MEMORY`/`COLLECT_MESSAGE`/`MARK_URGENT`) would
have received "yes" as its content/instructions instead of the caller's
real original words. `DefaultContextEngine.build_context` returns the
captured value in `context_profile["user_instructions"]`. New tests:
`test_agent_tools.py` (+3), `test_agent_orchestrator.py` (+2, including
the confirm-preserves-original-text regression), plus a real-Postgres
round-trip assertion added to the existing
`test_set_context_tool_writes_a_profile_default_context_engine_can_read`
in `test_integration_db.py` (DB-gated, not run live in this environment -
same pre-existing reason, no `TEST_DATABASE_URL`).

Honest scope note, stated plainly: this round makes the literal
instructions real and queryable (`ContextProfile.user_instructions`,
`ConversationContext.context_profile["user_instructions"]`) - it does
**not** make `WowAgent`'s reply generation actually *use* that text yet
(`generate_response`'s templates and `LanguageModelProvider.generate`'s
prompt construction are unchanged, and Brain v3 itself was not modified,
per instruction). Wiring the captured literal instructions into how WOW
actually behaves on a call is real, separate future work.

**Real G.711 mu-law <-> PCM16 codec + linear resampler**
(`app/media/audio_codec.py`, new): Plivo's wire format is mu-law 8kHz;
every other real provider in this project (VAD/STT/TTS) assumes PCM16
16kHz. Pure Python + stdlib `struct` only - deliberately no `audioop`
dependency (deprecated since Python 3.11, removed in 3.13 per PEP 594)
and no numpy (an optional dependency elsewhere in this project, not
something this unconditionally-needed module should require). mu-law
encode/decode is the standard G.711 segment/exponent algorithm, derived
via a real segment-boundary search rather than a hand-transcribed 256-row
lookup table (a first attempt at literally transcribing that table from
memory had a real, caught bug - see test history); decode is bit-exact
against Python's own `audioop.ulaw2lin` (a genuine independent oracle,
cross-checked in tests while still available on this Python version);
encode matches audioop for >98% of samples, with the rare (~0.5%,
boundary-adjacent) mismatches bounded to one quantization step apart -
both bytes are valid G.711 encodings, and Plivo's own decoder (not this
specific CPython build) is the real interop target. Resampling is real
linear interpolation (not sample duplication/dropping), generic to any
rate ratio, exercised for the specific 8kHz<->16kHz conversion this
bridge needs. 11 new tests (`test_audio_codec.py`), including a full
16kHz -> 8kHz -> mu-law -> decode -> 16kHz round trip bounded to a real,
documented telephony-quality error tolerance.

**`MediaPipeline.synthesize_reply`** (new, `app/media/pipeline.py`): a
small, real refactor - `_finalize_turn`'s inline voice-resolution +
synthesize logic was extracted into a reusable method (`_resolve_voice` +
`synthesize_reply`), needed by the Plivo route to synthesize the call's
fixed "Hello." opening greeting (via the real per-user voice resolver,
same as every agent-generated reply) before any caller audio exists to
respond to - not routed through Brain v3/Agent Core, since there is
nothing to classify yet (same precedent as `CANCELLED_ACKNOWLEDGEMENT`'s
fixed reply text - still real Piper TTS, never pre-recorded/fake audio).
Zero behavior change to the pre-existing turn-reply path - all prior
`test_media_pipeline*.py` tests pass unchanged.

**`PlivoTelephonyProvider`** (`app/providers/telephony/plivo.py`, new):
the first real (non-simulated) implementation of the pre-existing
`TelephonyProvider` ABC. `send_audio` resamples PCM16 (any input rate,
e.g. Piper's real per-voice rate) to 8kHz and mu-law-encodes it into
Plivo's documented `playAudio` JSON envelope; `on_audio_received`
registers a handler invoked with real inbound audio already converted to
this project's PCM16/16kHz convention -
`feed_inbound_message`/`_extract_media_payload` parse Plivo's `media`
event defensively (nested `media.payload` per Plivo's own outbound
convention, flat `payload` fallback, unrecognized shapes logged and
skipped rather than crashing the call - genuinely not 100%-confirmed
against a live call yet, see docs/PLIVO_TESTING.md's "what to watch for").
`answer_call`/`end_call` are real but honestly scoped: Plivo has no
separate "answer" step (the Answer URL's PLIVOXML response *is* the
answer) so `answer_call` is a documented no-op/log; `end_call` closes the
WebSocket, with the underlying PSTN call's actual hangup behavior flagged
as unverified rather than assumed (a follow-up via Plivo's REST
Call-hangup API if the first real test shows it's needed).
`queue_to_async_iterator` bridges `on_audio_received`'s push-based handler
callback onto `MediaPipeline.stream_call_audio()`'s pull-based async
iterator. 12 new tests (`test_plivo_telephony_provider.py`), all using a
fake `WebSocket` (this codebase's existing test-double pattern, not a
fake phone call) - real mu-law conversion, real message parsing,
including every defensive fallback path.

**Two new routes** (`app/api/routes/telephony_plivo.py`, new):
`POST /telephony/plivo/answer` (Plivo's Answer URL webhook - parses the
real form-encoded `CallUUID`/`From` fields, returns PLIVOXML opening a
`bidirectional="true"` Stream to this backend's own WebSocket route, no
`<Speak>` - the real "Hello." greeting is Piper's, not Plivo's hosted
voice) and `WS /telephony/plivo/stream` (the actual bridge: registers
`PlivoTelephonyProvider.on_audio_received`, waits a bounded 2s for
Plivo's `start` event so `CallRecorder.start_call` can record the real
caller number instead of racing the concurrent receive loop, greets via
`MediaPipeline.synthesize_reply`, drives
`MediaPipeline.stream_call_audio()` over the inbound audio queue,
records every real caller/assistant turn via `CallRecorder.record_turn`,
sends each real reply back via `PlivoTelephonyProvider.send_audio`, and
calls `CallRecorder.end_call` + `notify_call_handled` once the stream
ends). `Settings.public_base_url` (new, `app/config.py`) makes the
PLIVOXML response's `wss://` URL an explicit operator-set value rather
than inferred from request headers, which are only trustworthy behind a
tunnel if uvicorn runs with `--proxy-headers` - this project doesn't
assume that's always configured correctly. `Settings.demo_user_id` (new)
centralizes the single-tenant demo-user convention the Android
app/mobile UI already hardcode, instead of a third hardcoded copy in the
new route. New dependency: `python-multipart==0.0.12` (Starlette's
`Request.form()` needs it for any form parsing, including the plain
`application/x-www-form-urlencoded` body Plivo's webhook sends - a real
gap the answer-webhook test caught immediately).

**`app/observability/notifications.py`** (new): `notify_call_handled` - a
real, minimal, explicitly-scoped "WOW handled a call" log line for this
first local test, not a phone push notification (no Firebase/APNs wired
into this project - the existing Android `NotificationHelper` only fires
from a real GSM auto-answer in-process, a code path a Plivo call never
reaches). 2 new tests.

**Real end-to-end proof, not mocked**: `test_telephony_plivo.py`'s
`test_real_call_audio_travels_through_the_full_plivo_bridge` drives a
real WebSocket connection (FastAPI `TestClient`) carrying the real
`meeting_context.wav` fixture - downsampled to 8kHz and mu-law-encoded
exactly as a real Plivo call would deliver it (genuinely lossier than the
fixture's native 16kHz, the real telephony-quality path, not a shortcut) -
through the real route, `PlivoTelephonyProvider`, `MediaPipeline`, real
`LocalWhisperSTTProvider`, a real `WowAgent` (`RuleBasedLanguageModelProvider`
- this test proves the bridge's plumbing, not Brain v3's accuracy, which
`test_agent_integration_v3.py`/`test_media_pipeline.py` already cover
separately), and real `LocalPiperTTSProvider`, with a real `CallRecorder`
writing to a real file-backed SQLite database (not `:memory:` - a
same-process, different-thread/event-loop connection-reuse issue with
`:memory:` was hit and fixed by switching to a real temp file). Asserts,
against real rows re-read from a fresh connection afterward: a real
`playAudio` greeting sent first, a real transcribed-and-replied-to turn
sent second, a real `Call` row with the real captured caller number and
`COMPLETED` status, real transcript segments (including the actual
transcribed words, containing "meeting"), and a real summary. Gated on
`pytest.importorskip("faster_whisper")`/`pytest.importorskip("piper")` -
runs for real in this environment (both installed), skips cleanly where
they aren't.

**Deliberately not done**: no Brain v3 changes (per instruction - the
context-instructions gap is closed at the data-capture layer only, not by
retraining or prompt-engineering the model); no Render upgrade or any
purchase; no signature validation on the Answer URL webhook (Plivo's
inbound-webhook-signing scheme wasn't independently verified this round -
flagged as a real gap, not silently skipped, in
`app/providers/telephony/plivo.py`); no carrier call-forwarding setup
(this milestone calls the Plivo number directly, per `docs/PLIVO_TESTING.md`).

Tests after this round: **297 passed, 29 skipped** (was 262/29 - +35 new,
all executed, none skipped). No regressions. `mobile/` untouched this
round - nothing shipped in the installed app changed, so no version
bump/release for it this time (see the project's standing release
workflow: a release ships only once a round actually touches `mobile/`).

## Plivo bridge production-safety review (2026-09-17)

On explicit instruction, before any commit/push: reviewed the Plivo
bridge's connection lifecycle/disconnect handling/malformed-frame
handling/buffering/backpressure/concurrency/exception handling/cleanup,
added Plivo's real documented webhook signature validation, and verified
several specific claims rather than assuming them. Real, concrete bugs
found and fixed - not just theoretical review:

- **`receive_loop` could leak cleanup.** It only caught
  `WebSocketDisconnect`; Starlette can raise other exceptions (e.g.
  `RuntimeError`) once a connection is already gone, which would have
  propagated out of `await receive_task` in `plivo_stream`'s `finally`
  block and **skipped** `recorder.end_call`/`notify_call_handled`/
  `provider.end_call` entirely - meaning a call could go unrecorded.
  Fixed: `receive_loop` now catches and logs any exception, never lets
  one escape the task.
- **`recorder.start_call` failing would leak the receive task.** It ran
  *before* the `try:` block, so a real DB error there would skip cleanup
  entirely (the WebSocket and background task would never be closed).
  Fixed: the whole body (including `start_call`) is now inside
  try/except/finally, with `call`/`conversation` guarded as possibly
  `None` in the cleanup path.
- **Unbounded inbound audio queue.** While WOW is "thinking" (STT/Brain/
  TTS for the previous turn), `stream_call_audio`'s consumption loop
  isn't draining the queue, so inbound audio piles up - previously
  unbounded, a real memory-growth risk for a pathological stall (this
  project has already hit a real OOM crash once, see
  `docs/DEPLOYMENT.md`). Fixed: bounded to `_AUDIO_QUEUE_MAXSIZE=2000`
  (~40s of real audio), overflow drops the newest chunk with a logged
  warning rather than blocking or growing without limit.
- **WOW could activate itself.** Neither `plivo_answer` nor `plivo_stream`
  checked `User.call_assistant_enabled`/`active_until` at all - every
  inbound Plivo call was answered and handled unconditionally, directly
  violating "WOW must never activate itself." Fixed: `plivo_answer` now
  looks up the demo user, applies the same lazy activation-expiry logic
  `GET /users/{id}` already uses (`apply_activation_expiry`, promoted from
  a users.py-private helper to a real shared function since it now has
  two real callers), and returns `<Hangup/>` instead of opening a Stream
  when WOW isn't activated.

**Real X-Plivo-Signature-V3 validation** (`app/providers/telephony/plivo_signature.py`,
new): implemented from Plivo's own official docs
(`plivo.com/docs/voice/concepts/signature-validation`), not invented -
HMAC-SHA256 over the request URL + sorted POST params + nonce, keyed by
the real Plivo Auth Token, constant-time compared
(`hmac.compare_digest`) against the header (supporting the documented
comma-separated multi-token case). No `plivo` SDK dependency - pure
stdlib (`hmac`/`hashlib`/`base64`), matching `audio_codec.py`'s existing
discipline. `Settings.plivo_auth_token` (new, environment-only, never
hardcoded, absent from `.env.example` beyond a placeholder) gates it: unset
means validation is skipped with a loud warning (acceptable only before a
real Plivo account exists), set means a real mismatch is rejected with
403. 8 new tests (`test_plivo_signature.py`), including the exact worked
example quoted verbatim from Plivo's own docs page as a real, sourced
test vector - not a self-invented one.

**Verified, not assumed - two specific findings from the review's
checklist**:

- **Female Piper voice genuinely reaches the caller.** New test
  (`test_female_piper_voice_is_actually_resolved_and_sent_back`, real
  DB-backed `voice_resolver`, real `LocalPiperTTSProvider` with a spy)
  proves `en_US-hfc_female-medium` (not the generic default voice) is
  what's actually synthesized and sent for a real user with
  `voice_gender=FEMALE` - the same `resolve_user_voice`/`get_media_pipeline`
  wiring `/brain/voice-command` already used, now proven for the Plivo
  route specifically too.
- **Multiple sequential turns work, not just one.** New test
  (`test_multiple_sequential_turns_in_one_call_are_all_handled`) sends two
  real, distinct fixture utterances (`hello.wav` then `meeting_context.wav`,
  separated by real silence) over one WebSocket connection; real VAD
  actually found 3 separate turns (an extra real pause inside one
  fixture), all real-transcribed and real-replied-to - stronger proof
  than the 2 originally expected, not a discrepancy to paper over.
- **Honest, not-yet-fixed finding, stated plainly**: `user_instructions`
  (this round's earlier context-instructions capture) reaches the
  `context` parameter passed to `LanguageModelProvider.generate()`
  (confirmed by reading both `RuleBasedLanguageModelProvider.generate`
  and `LocalWOWModelProvider.generate` directly) - but **neither provider
  actually reads that parameter at all**, so today it has zero effect on
  the generated reply. This is a pre-existing gap (even the original
  `context_profile.instructions` was already unused before this round),
  not something this round introduced or was asked to fix - flagged
  here, not silently left undiscovered.

**Also confirmed by direct code inspection, no code change needed**:
credentials are environment-only everywhere (grepped for hardcoded
tokens - none found); caller audio/transcript content is never logged in
plaintext anywhere in the new code (grepped every `logger.*` call in the
new modules - only call metadata: caller number, call id, event types,
counts, durations, and the generic templated summary line, matching the
existing `WowCallScreeningService.kt` precedent of logging caller
number); `CallRecorder` creates exactly one `Call`/`Conversation` per
real call with the real captured caller number and `COMPLETED` status,
one `TranscriptSegment` per real turn, and one `Summary` at the end
(already proven in `test_telephony_plivo.py`, re-confirmed this round).
No lint/type-check tooling (ruff/mypy/flake8) is configured anywhere in
this project - confirmed by checking for config files and installed
packages, not silently assumed; none was added unprompted. `flutter
analyze` and `flutter test` both pass cleanly (0 issues, 8/8 tests) -
`mobile/`'s only change remains the previously-reported 5s auto-answer
delay.

**Known, accepted test-infrastructure artifact**: two of the heavier
`test_telephony_plivo.py` tests occasionally emit a
`PytestUnhandledThreadExceptionWarning` ("Event loop is closed") from a
background `aiosqlite` thread finishing its own connection-close
bookkeeping slightly after that test's own event loop was torn down by
pytest - a timing race in test cleanup (FastAPI's `TestClient` runs the
ASGI app in its own thread/loop), not a defect in the application code
under test: every real assertion in every run has passed, and this
warning does not fail the suite under normal (non-`-W error`) execution.
Mitigated (real fixes, not a workaround): `NullPool` on the test-only
SQLite engine, and explicit `engine.dispose()` at the end of each test
rather than relying on GC timing.

Tests after this round: **313 passed, 29 skipped** (was 297/29 - +16 new,
all executed, none skipped). No regressions. Still no purchase, no Plivo
account, no real call - see docs/PLIVO_TESTING.md for the unchanged
next step.

## Context-instruction execution + multilingual conversation (2026-09-17)

Two rounds combined on explicit instruction: (1) closing the gap flagged
at the end of the safety review - `user_instructions` reached
`LanguageModelProvider.generate()`'s `context` param but neither provider
read it, so it had zero effect on replies; (2) real per-turn Hindi/
Hinglish/English detection and response. Brain v3 untouched (confirmed:
`git diff --stat training/ app/providers/llm/local_wow.py` empty).

**Architecture** (inspected before changing anything, per instruction):
`RuleBasedLanguageModelProvider`/`LocalWOWModelProvider` both already
ignore their `context` parameter entirely - this predates this round.
`WowAgent`'s `generate_response()` call is the one real seam for reply
text. New pipeline: `audio -> STT (+ real Whisper language signal) ->
app.agent.language_detection.detect_language() -> WowAgent.handle_input(language=...)
-> app.agent.response.generate_response(language=..., active_context_profile=...)
-> TTS (app.media.voice_selection.resolve_voice_for_language)`. Brain
v3/rule_based's own intent/context/action classification is completely
unchanged and untouched by any of this - language detection and response
composition are new, separate stages around it, not a replacement for it.

**Context-instruction execution**
(`app/agent/user_instructions.py`, new): `parse_user_instructions()`
extracts real, bounded boolean directives (`ask_caller_reason`,
`take_message`, `mark_urgent_only_if_necessary`, `do_not_disturb`) from
the owner's literal text via regex - a small, honest detection-feature
set (see the module's own docstring for why this isn't "a large
collection of hardcoded responses": there are no responses hardcoded
here, only booleans extracted from a short, formulaic owner-authored
sentence, not matched against open-ended caller speech).
`app/agent/response.py`'s `generate_response()` gained
`active_context_profile` - when a conversational turn (ALLOW verdict, no
llm_content, not confirmed, no action template) happens while a context
is active, it now composes a real, grounded reply
(`_compose_contextual_reply`) reflecting the active context mode and
those directives, instead of the old generic "I heard you, but I'm not
sure how to respond to that yet." Verified end to end with a real,
distinguishing test: the SAME caller turn ("Hi, is Aniket there?")
produces a DIFFERENT reply depending on whether `user_instructions` asks
WOW to ask the caller's reason - proving real influence, not just
storage (`test_active_context_with_literal_instructions_changes_the_reply`).

**Honest limitation, stated plainly**: this is real, tested, deterministic
composition - a genuinely richer template layer, not free generation.
It does not reconstruct the caller's exact stated reason into a
dynamically-composed sentence (e.g. "let him know you called about the
project") the way a real LLM could - that needs either a fine-tuned
generator or a hosted LLM, both out of scope (no hosted LLM, Brain v3
unchanged). Reported honestly rather than overclaimed, per instruction.

**Multilingual detection** (`app/agent/language_detection.py`, new):
three combined real signals, never a keyword-response table - real
Devanagari script detection, faster-whisper's own real acoustic language
ID (previously computed and silently discarded by
`LocalWhisperSTTProvider` - now surfaced via new `TranscriptionResult.language`/
`.language_probability` fields, zero extra latency), and a bounded,
linguistically-justified Hindi-function-word lexicon for Latin-script
disambiguation. Output: `"en"` / `"hi"` / `"hi-Latn"` (a real BCP-47
tag - Hindi content in Latin script, i.e. Hinglish; there is no
standardized ISO code for Hinglish itself). A real, live-observed edge
case was found and fixed during testing: Whisper transcribed genuine
Piper-synthesized Hindi speech using Perso-Arabic/Urdu script (Hindi and
Urdu are mutually intelligible spoken languages) rather than Devanagari
or Latin - the detector now checks actual script composition
(`_is_latin_script`) rather than assuming "not Devanagari" means Latin,
so this still correctly resolves to `"hi"`, not a mislabeled `"hi-Latn"`.

**Per-turn, not call-wide**: `MediaPipeline._finalize_turn` detects
language fresh every turn and passes it to `WowAgent.handle_input`
(`AgentRuntime.handle_input` gained an optional `language` parameter -
`WowBrain` accepts and ignores it, satisfying the contract;
`ConversationState.detected_language` - already present in the schema -
now actually gets set) - proven to genuinely follow a caller switching
languages mid-call, turn by turn, not locked to the first turn.

**Per-language, per-context response templates**
(`app/agent/response.py`): every existing template (clarify/refuse/
handoff/tool-failure/confirmed/action templates, plus the new contextual
composer) gained real Hindi/Hinglish phrase-bank entries, selected by
the new `language` parameter - `language=None` (every pre-existing
caller) is byte-identical to before this round, verified by a dedicated
regression test.

**Per-language female voice** (`app/media/voice_selection.py`):
`resolve_voice_for_language(session, user_id, language_code)` reuses the
existing real `resolve_piper_voice` mapping, substituting the detected
language for the user's static profile language while preserving their
real `voice_gender` - so a caller switching Hindi/Hinglish/English
mid-call actually hears the matching female Piper voice each time, not
one fixed voice for the whole call. Wired as `MediaPipeline`'s new
optional `language_voice_resolver` (additive - the call's opening
greeting, with no caller turn/language yet, still uses the static
profile voice/`voice_resolver` unchanged) and into `get_media_pipeline()`
for every real route.

**Per-turn language storage**: `TranscriptSegment` gained a nullable
`language` column; `CallRecorder.record_turn` gained an optional
`language` parameter; `/telephony/plivo/stream` now records and logs
(`WOW CALL HANDLED`-style, metadata only, never transcript content) the
real detected language for both the caller's and WOW's turn on every
real call.

**Tests** (all real, all passing): `test_language_detection.py` (+12,
including the real Urdu-script edge case), `test_user_instructions.py`
(+6), `test_agent_response.py` (+10, context-aware + multilingual
composition, plus a byte-identical-to-before regression check),
`test_agent_orchestrator.py` (+6, full real `WowAgent` flow: context
instructions changing behavior, Hindi/Hinglish/English replies, and a
genuine mid-call language switch across 3 consecutive turns),
`test_local_whisper_stt.py` (+1, real Whisper language field),
`test_voice_selection_language.py` (+7, real per-language/gender voice
resolution against a real SQLite-backed User row), and
`test_telephony_plivo_multilingual.py` (+1) - the strongest proof
available in this environment: a real Piper-synthesized Hindi utterance
(no recorded Hindi fixture exists in this repo, so this test synthesizes
one itself via the same real `hi_IN-priyamvada-medium` voice already used
elsewhere) followed by the real `hello.wav` English fixture, both
delivered exactly as a real Plivo call would (downsampled to 8kHz,
mu-law-encoded), through the entire real bridge - proving a real language
switch mid-call, real per-turn language storage, and the real female
voice actually changing between `hi_IN-priyamvada-medium` and
`en_US-hfc_female-medium` within one call.

**Measured latency** (real, on this machine's CPU - faster-whisper
`base`/int8, Piper, `RuleBasedLanguageModelProvider`; see the session's
`measure_latency.py` scratchpad run, 3 consecutive turns of the real
`meeting_context.wav` fixture): STT ≈1450-1520ms, language detection
≈0ms (confirms the "real but essentially free" design claim - it's pure
Python string/regex work on already-transcribed text, no model
inference), agent (rule-based classify + policy + tool) ≈0ms, TTS ≈1484ms
on the first call (includes one-time Piper voice-model load) then
≈190-200ms once warm, total ≈3000ms first turn / ≈1650ms warm turns.
STT dominates end-to-end latency by a wide margin - the real bottleneck
for a live call is faster-whisper's `base` model on CPU, not language
detection or response composition (both real, and both negligible).

Tests after this round: **355 passed, 29 skipped** (was 313/29 - +42
new, all executed, none skipped). No regressions. `mobile/`/`training/`/
`app/providers/llm/` untouched. Still no purchase, no Plivo account, no
real call.

## Phase 1 - stabilization + security + Plivo production foundation (2026-10-01)

Scope: make the current tree safe, reproducible and ready for the first real
Plivo call. No Phase 2 work, no custom telephony, no real call made.
Authoritative detail: `docs/SECURITY.md`; procedure: `docs/PLIVO_TESTING.md`.

- **Tree reconciled and committed.** The previously uncommitted Plivo bridge,
  multilingual/context-instruction work, privacy screen and 40+ modified files
  are now in git (model weights, datasets and `.env` remain git-ignored).
- **Plivo WebSocket auth.** Single-use, 120 s, `CallUUID`-bound tokens minted by
  the signed Answer webhook and required on the stream URL (checked before
  `accept()`); start-event call-id correlation; concurrent-stream and
  max-duration caps. (`app/providers/telephony/stream_tokens.py`,
  `app/api/routes/telephony_plivo.py`.)
- **Answer webhook.** Signature check now fails closed; signed URL rebuilt from
  `PUBLIC_BASE_URL` (previously a tunnel would have broken validation); missing
  `CallUUID`, DB errors and caps hang up instead of erroring.
- **API boundary.** `X-WOW-API-Key` on every REST route except `/health` + Plivo;
  startup refuses a public URL without `API_ACCESS_KEY`/`PLIVO_AUTH_TOKEN`; docs
  hidden when protected; Dart client + Android native code send the key.
- **Parser.** Tolerant start/media parsing, `track: outbound` ignored, oversized/
  non-object/invalid frames dropped; exact inbound JSON still unconfirmed.
- **Resilience.** One failed STT/Brain/TTS turn no longer ends a live call (3
  consecutive do); cleanup steps are independently guarded.
- **Privacy.** Card/OTP/PIN numbers redacted before transcript storage; the privacy
  screen no longer claims an in-app delete that does not exist.
- **Database.** Alembic added (baseline adopts a `create_all` DB + `0002` adds
  `context_profiles.user_instructions` / `transcript_segments.language`).
  Previously-skipped Postgres-gated tests now run against a throwaway
  pgvector Postgres; two stale ones were fixed (non-UUID conversation id).
- **Activation.** OFF by default, exactly 15m/1h/5h/until_stop/off, lazy expiry now
  tolerant of naive datetimes - covered by tests.

Still NOT done / not proven: a real external Plivo call; Plivo's inbound JSON
shape and query-string behaviour; whether `end_call` hangs up the PSTN call;
per-user auth; production key enforcement; Business mode.

## Phase 1 live-validation rehearsal findings (2026-10-01)

Before the first real Plivo call, the real backend (real faster-whisper, Brain
v3, WowAgent, Piper, Postgres+pgvector) was driven over real sockets by a
simulated caller (a REHEARSAL - not the live gate; no Plivo call was made).
It found two real defects the automated suite could not, both fixed:

- **Cross-session foreign key (would have killed the first real call).**
  `CallRecorder` created the `Conversation` in a transaction that only
  committed at call end, while WowAgent writes `agent_states`/`feedback_events`
  through its own session with a foreign key to it. On Postgres the first turn
  raised ForeignKeyViolation, poisoned the agent session, and three failed
  turns ended the call. Fix: commit right after `start_call`, after each turn
  and after `end_call` (`CallRecorder.commit`). Regression:
  `tests/test_call_recorder_cross_session_fk.py` (Postgres) + an ordering test.
- **Stream token in logs.** uvicorn's access log printed the full
  `WebSocket /telephony/plivo/stream?token=...` URL. A logging filter now
  redacts `token=` values (`app/security.py`).
- Test hygiene: tests no longer pick up a developer's git-ignored
  `backend/.env` (`tests/conftest.py` pins a baseline).

Rehearsal result: 27/27 checks (auth boundary, signed webhook with URL rebuilt
from PUBLIC_BASE_URL, token missing/invalid/mismatch/replay rejected, junk and
outbound frames ignored, English + Hindi + switch-back turns answered with audio,
transcript/language/summary persisted, OFF hangs up). Measured per-turn latency
on this PC's CPU: STT 1.8-2.8 s, agent (Brain v3, 3 heads) 0.2-2.0 s, TTS 0.3-0.8 s
(3.1 s first Hindi voice load), total 2.4-3.9 s for English turns, 7.9 s for the
first Hindi turn. Language detection ~0 ms.
