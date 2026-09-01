# Training WOW Brain

This document covers the WOW Brain classifier training pipeline under
`training/`: the dataset, the v0 post-mortem that drove the v1 rework, the
v1 dataset/training strategy and results, the v1.1 dataset improvement
(prepared and validated, not yet trained - see "Train WOW Brain v1.1
yourself" below), and how to reproduce every step.

WOW Brain is not one model - it's three lightweight text-classification
heads (intent / context_mode / action) fine-tuned from the same base
encoder, trained and served together as one "model version" directory
(`training/models/wow-brain/<version>/{intent,context,action}/`).

## Privacy

Every dataset example under `training/datasets/` is hand-authored or
composed by a developer for this project. **None of it is derived from
real user/production conversations.** `training/generation/build_seed_dataset.py`
is the single source of truth for how every example was produced - read it
directly rather than trusting summaries of it.

## Pipeline

```
training/generation/build_seed_dataset.py   hand-authored examples -> training/datasets/{intents,contexts,call_scenarios,conversations,summaries}/seed.jsonl
training/preprocessing/validate.py          schema/dup/consistency checks over every seed.jsonl
training/preprocessing/build_training_set.py  unifies intents+contexts+call_scenarios+conversations -> processed/{train,val}.jsonl (stratified split)
training/preprocessing/stats.py             distribution report over the unified dataset and the split
training/training/train.py                  fine-tunes intent/context/action heads -> training/models/wow-brain/<version>/
training/evaluation/evaluate.py             scores rule_based vs one or more trained versions on val.jsonl
```

Run the whole pipeline for a given config:

```bash
cd wow-ai
backend/.venv/Scripts/python.exe -m training.generation.build_seed_dataset
backend/.venv/Scripts/python.exe -m training.preprocessing.validate
backend/.venv/Scripts/python.exe -m training.preprocessing.build_training_set
backend/.venv/Scripts/python.exe -m training.preprocessing.stats
backend/.venv/Scripts/python.exe -m training.training.train --config training/configs/model_config_v1.yaml
backend/.venv/Scripts/python.exe -m training.evaluation.evaluate \
    --model-dir v0=training/models/wow-brain/v0 \
    --model-dir v1=training/models/wow-brain/v1
```

`training.training.train` and `training.evaluation.evaluate` need
`backend/requirements-local-model.txt` installed (torch + transformers +
sentencepiece) in addition to `backend/requirements.txt`; everything else
in the pipeline is pure Python.

## Train WOW Brain v1.1 yourself (PowerShell)

Everything for v1.1 is prepared and validated - the dataset (v2.1.0), the
config (`training/configs/model_config_v1_1.yaml`), and the training
pipeline's GPU support. Nothing has been trained; run these yourself from
the repo root (`wow-ai\`) in PowerShell.

### Check GPU

```powershell
backend\.venv\Scripts\python.exe -c "import torch; print(torch.cuda.is_available()); print(torch.cuda.get_device_name(0) if torch.cuda.is_available() else 'No CUDA GPU')"
```

### Validate dataset

```powershell
backend\.venv\Scripts\python.exe -m training.preprocessing.validate
backend\.venv\Scripts\python.exe -m training.preprocessing.stats
```

(Both already run clean against v2.1.0 - see "v1.1 dataset" below for the
numbers. Safe to re-run any time; neither writes model weights.)

### Train on GPU

```powershell
$env:TRAINING_DEVICE="cuda"
backend\.venv\Scripts\python.exe -m training.training.train --config training/configs/model_config_v1_1.yaml
```

If CUDA isn't actually available, this fails immediately with a clear
`RuntimeError` - it will not silently train on CPU instead (see
"Training device selection" below).

### Train automatically

```powershell
$env:TRAINING_DEVICE="auto"
backend\.venv\Scripts\python.exe -m training.training.train --config training/configs/model_config_v1_1.yaml
```

CUDA -> MPS -> CPU, first available wins. This is also what happens if you
don't set `TRAINING_DEVICE` at all - `model_config_v1_1.yaml` already
specifies `training_device: "auto"`.

### Train on CPU

```powershell
$env:TRAINING_DEVICE="cpu"
backend\.venv\Scripts\python.exe -m training.training.train --config training/configs/model_config_v1_1.yaml
```

### Evaluate

```powershell
backend\.venv\Scripts\python.exe -m training.evaluation.evaluate --model-dir v0=training/models/wow-brain/v0 --model-dir v1=training/models/wow-brain/v1 --model-dir v1.1=training/models/wow-brain/v1.1
```

### Predict

```powershell
backend\.venv\Scripts\python.exe -m training.inference.predict --model-dir training/models/wow-brain/v1.1 "I'm sleeping, handle my calls"
```

(Omit `--model-dir` to default to v1, which already exists, if you want to
sanity-check the command before v1.1 finishes training.)

### What the training log will show

Every run now prints, before any epoch:

```
Training device: cuda
CUDA available: True  MPS available: False
GPU: <your actual GPU name> (<X.XX> GB)
```

(`cpu`/`auto` runs print `Training device: cpu` and the availability flags,
with no `GPU:` line - device/GPU info is only ever what
`torch.cuda`/`torch.backends.mps` actually report, never fabricated.) Each
epoch then prints loss, validation accuracy, wall-clock seconds, and
samples/sec, e.g.:

```
Training head: intent (base_model=distilbert-base-multilingual-cased, batch_size=16)
  [intent] epoch 1/20 - loss 2.7972 - val_acc 0.2752 - 4.1s (312.4 samples/sec)
```

All of this - device, GPU name/memory, per-epoch timing/throughput - is
also saved into `training/models/wow-brain/v1.1/metadata.json` once
training finishes, for a permanent record of what actually trained the
model.

### After you train: the exact next commands

Once your training run finishes (v1.1 exists at
`training/models/wow-brain/v1.1/`), here's the full sequence to get it
evaluated and, only if it earns it, promoted - none of this has been run
for you:

```powershell
# 1. (already done above) validate + train
# 2. evaluate v1.1 against rule_based, v0, and v1 on the same val set
backend\.venv\Scripts\python.exe -m training.evaluation.evaluate `
    --model-dir v0=training/models/wow-brain/v0 `
    --model-dir v1=training/models/wow-brain/v1 `
    --model-dir v1.1=training/models/wow-brain/v1.1

# 3. inspect the report - especially per_intent_accuracy, mode_collapse_suspected,
#    and the UNKNOWN/context numbers v1.1's dataset targeted
type training\evaluation\latest_report.json
```

Then, in a Python shell or short script (see `backend/app/learning/promotion.py`
and `docs/SELF_LEARNING.md` "Evaluation gate and promotion policy" for what
this actually checks):

```python
import json
from app.learning.promotion import PromotionManager, PromotionPolicy

report = json.load(open("training/evaluation/latest_report.json", encoding="utf-8"))
decision = PromotionManager(PromotionPolicy()).decide(
    report["providers"]["v1.1"], report["providers"]["v1"],  # or ["rule_based"]
)
print(decision.should_promote, decision.reasons)
```

**Promote only if the gate passes.** If `should_promote` is `False`, read
`decision.failed_checks` - it names exactly which metric regressed and by
how much (this is precisely what caught v1 itself failing the gate against
`rule_based` on UNKNOWN accuracy, despite huge intent/context/action gains
- see "v1 results" below). Do not loosen the policy just to force a pass;
either accept the regression deliberately (documented, deliberate policy
change) or address it in the next dataset round.

## WOW Brain v0 post-mortem

v0 (`training/configs/model_config.yaml`, `prajjwal1/bert-tiny`) was trained
on a 117-example seed set (99 train / 18 val) as a "genuine, reproducible
smoke test" - explicitly not claimed to be production-quality. Evaluating it
with `training.evaluation.evaluate` confirmed exactly that, and worse:

| Metric | rule_based baseline | WOW v0 |
|---|---|---|
| Intent accuracy | 33.3% | 16.7% |
| Context accuracy (n=7) | 14.3% | 14.3% |
| Action accuracy | 44.4% | 16.7% |
| Structured output validity | 100% | 100% |

v0 didn't just underperform a handful of regex rules - it exhibited
**majority-class mode collapse**: 13 of its 15 validation failures predicted
`SET_CONTEXT` (12 of those with context `BUSY`), regardless of the true
label, including on inputs like "Just wanted to say happy birthday!" and
"Theek hai, bas itna hi tha, dhanyavaad." Two compounding root causes were
identified:

1. **Dataset too small and imbalanced for the label space.** 99 train
   examples spread across 17 intents / 12 actions / 7 context modes, with
   `SET_CONTEXT`/`BUSY` the largest classes. With unweighted cross-entropy,
   the loss-minimizing strategy on an imbalanced set this small is to
   default to the majority class - which is exactly what happened.
2. **Base model couldn't represent Hindi at all.** See below.

### Why bert-tiny was replaced

`prajjwal1/bert-tiny` uses the stock `bert-base-uncased` vocabulary -
English-only WordPiece, 30522 tokens. Verified by hand:

```python
>>> BertTokenizer.from_pretrained("prajjwal1/bert-tiny").tokenize("मैं सो रहा हूँ, कॉल्स संभाल लेना।")
['म', 'स', '##ो', 'र', '##ह', '##ा', 'ह', ',', '[UNK]', 'स', '##भ', '##ा', '##ल', 'ल', '##न', '##ा', '।']
```

Devanagari text fragments into isolated single characters (plus an outright
`[UNK]` for a combining vowel sign) - there is no whole-word or meaningful
subword structure for the model to learn from, and since bert-tiny was
never pretrained on Hindi, even Roman-Hindi/Hinglish subwords that do
tokenize cleanly carry no real semantic content. This lines up with the
evaluation data: `hi` was the worst-performing language for both the
rule-based baseline (22.2%) and v0 (11.1%). See `docs/MODEL_ARCHITECTURE.md`
for the v1 replacement and the same check against it.

## v1 dataset strategy

`training/generation/build_seed_dataset.py` was rewritten (dataset_version
`2.0.0`, superseding v0's `1.0.0`) to fix both root causes directly:

- **Scale and balance**: 724 unified classification records (740 total
  including the summaries category), every intent and action class at 30+
  examples (`training.preprocessing.stats` enforces and reports this - see
  "Dataset balance" below). Context modes are deliberately *not* forced to
  the same floor: `NORMAL` naturally dominates real usage, and inventing
  padding examples for `TRAVELLING`/`UNAVAILABLE` just to hit a number would
  reintroduce the "quantity over quality" problem this rework exists to fix.
- **Register variety per intent**: formal, casual, short commands,
  indirect/polite phrasing, and incomplete/trailing-off utterances, in
  English, Hindi (both Devanagari and Romanized), and Hinglish.
- **Hard negatives** (`build_hard_negative_examples()`): utterances whose
  surface keywords would mislead a keyword-matching or majority-class
  classifier but have one unambiguous correct label - e.g. "The meeting
  isn't urgent anymore" (NON_URGENT_CALL, not URGENT_CALL or
  SET_CONTEXT/MEETING), "I called because I wanted to know whether Aniket
  is sleeping" (GENERAL_CONVERSATION, not SET_CONTEXT/SLEEPING - the caller
  is asking about someone else's status, not declaring their own), and "An
  unknown caller is asking about my meeting" (UNKNOWN_CALLER, not
  GENERAL_CONVERSATION or SET_CONTEXT/MEETING). These are the direct
  countermeasure to the SET_CONTEXT/BUSY collapse pattern above.
- **SAVE_MEMORY coverage**: v0's training data contained zero examples of
  the `SAVE_MEMORY` action (it's in the taxonomy but was never
  demonstrated). v1 adds a dedicated block of examples where a caller
  volunteers a durable fact ("Just so you know, I moved to Pune last
  month") under GENERAL_CONVERSATION.

### Dataset balance

`python -m training.preprocessing.stats` reports per-intent, per-action,
per-context, and per-language distribution, plus train/val counts per
intent, and flags (`intents_below_30` / `actions_below_30`) any class under
the 30-example floor. Run it after any dataset change - see
`training/datasets/processed/STATS.json` for the latest report.

## Stratified train/val split

`training/preprocessing/build_training_set.py:stratified_split` replaced the
v0 flat-random split. It stratifies by intent: every class with at least 5
examples contributes at least 2 to validation (never exactly 1 - a
singleton validation example makes that class's accuracy meaningless: it's
either 0% or 100%), scaled by `val_fraction` for larger classes; classes
smaller than 5 go entirely to train, since they can't be split meaningfully.
The split is deterministic given `seed` (default 42, matching v0). Verify
with `training.preprocessing.stats`'s "Train/val intent distribution"
section - it flags any class with zero validation examples.

## Training improvements for v1

`training/training/train.py` and `training/training/config.py` gained,
relative to v0:

- **Class-weighted loss** (`class_weighting: true` in the config): balanced
  weights (`total / (num_classes * count[c])`, the same formula as
  sklearn's `class_weight='balanced'`) applied to cross-entropy, computed
  by `compute_class_weights` per head from that head's own training
  records. This directly removes the incentive that caused v0's collapse -
  under unweighted loss, always predicting the majority class is loss-
  minimizing on an imbalanced set; weighting removes that shortcut.
- **Per-epoch validation + best-checkpoint selection**: v0 only evaluated
  once, after the final epoch, and saved whatever that epoch happened to
  produce. v1 evaluates after every epoch and keeps the state dict with the
  best validation accuracy in memory (`copy.deepcopy`), restoring it before
  saving - so a model that starts overfitting or regressing late in
  training doesn't overwrite a better earlier checkpoint.
- **Early stopping** (`early_stopping_patience` in the config, 0 disables
  it): `train.EarlyStopper` stops a head's training after N consecutive
  epochs with no validation improvement. This is explicitly *not* "just
  run more epochs" - patience-based stopping combined with best-checkpoint
  selection means training runs long enough to find a good checkpoint and
  no longer, rather than picking a fixed epoch count and hoping.
- **Reproducibility**: `seed` (Python/NumPy/torch) was already present in
  v0 and is unchanged.
- **Everything else configurable per model version** via YAML
  (`base_model`, `batch_size`, `learning_rate`, `epochs`, `max_length`) -
  v0's `training/configs/model_config.yaml` is untouched and still
  reproduces the v0 run exactly; v1 lives in
  `training/configs/model_config_v1.yaml`.

`compute_class_weights` and `EarlyStopper` are pure Python (no torch
dependency) specifically so they're unit-testable without loading a model -
see `training/tests/test_train_helpers.py`.

## v1 results

Trained with `training/configs/model_config_v1.yaml`
(`distilbert-base-multilingual-cased`, class-weighted loss, early stopping
patience 4) on CPU, roughly 45 minutes total across all three heads. Every
head stopped early well before the 20-epoch cap, on the strength of the v1
countermeasures above (best epoch/total epochs trained: intent 6/10,
context 11/15, action 10/14):

| Metric | rule_based | v0 | v1 |
|---|---|---|---|
| Intent accuracy | 15.6% | 6.4% | **71.6%** |
| Context accuracy (n=20) | 25.0% | 15.0% | **50.0%** |
| Action accuracy | 31.2% | 8.3% | **70.6%** |
| Structured output validity | 100% | 100% | 100% |
| Ambiguous/UNKNOWN accuracy (n=5) | 100% | 0% | 20% |
| Mode collapse suspected | **yes** (77% -> UNKNOWN) | **yes** (100% -> SET_CONTEXT) | **no** (top intent 10.1% of predictions) |
| Per-language intent accuracy | hi 6.9% / en 17.0% / hinglish 22.2% | hi 10.3% / en 5.7% / hinglish 3.7% | hi 62.1% / en 67.9% / hinglish **88.9%** |

(Evaluated on the v2.0.0 val set - 109 examples, stratified from the 724
unified records built for v1. Both baselines score much lower here than
they did against v0's original 18-example val set: this set is
deliberately larger, more balanced, and includes the hard-negative
examples in `build_hard_negative_examples()` - a fair, harder bar, applied
identically to all three providers.)

v1 clears every part of the v0 post-mortem: it beats the rule-based
baseline by a wide margin on every metric except ambiguous/UNKNOWN
accuracy (still weak - see below), shows no majority-class collapse
(the most-predicted intent accounts for only 10.1% of predictions, vs.
v0's 100%), and its `intent_confusion_matrix` is diffuse - individual,
independent mistakes rather than one dominant failure mode. Hinglish,
oddly the hardest language for the rule-based baseline, is v1's
*strongest* language (88.9%) - consistent with Hinglish being close to
`distilbert-base-multilingual-cased`'s Latin-script training distribution
while still carrying Hindi vocabulary the model has real subword coverage
for.

**Remaining weaknesses**:
- **UNKNOWN accuracy is still weak (20%, n=5)** - recognizing "this input
  is genuinely unclassifiable" is inherently harder than picking the right
  real intent, and 5 examples is too small a sample to trust precisely;
  worth deliberately growing this category in a future dataset round.
- **Context accuracy (50%) lags intent/action (~70%)** - the context head
  trains on far fewer labeled examples (94 train / 20 val, vs. 615/109 for
  intent and action), because not every unified record carries a
  `context_mode`. Growing context-mode coverage (particularly the
  under-30-example modes like `TRAVELLING`/`UNAVAILABLE`/`CUSTOM` - see
  `training/datasets/processed/STATS.json`) is the most direct lever for
  v2.
- Full per-intent accuracy and the complete confusion matrix are in
  `training/evaluation/latest_report.json` (`providers.v1.per_intent_accuracy`,
  `providers.v1.intent_confusion_matrix`) - reproduced in the project
  history rather than duplicated here, since they'll go stale the moment
  the dataset changes again.

## v1.1 dataset (v2.1.0) - not yet trained

`training/generation/build_seed_dataset.py` was extended (not rewritten)
to target v1's two documented weaknesses above. **v2.0.0 - what v0 and v1
were actually trained on - was frozen first**, at
`training/datasets/versions/v2.0.0/`, and is untouched; the live
`training/datasets/{intents,contexts,...}/seed.jsonl` and
`training/datasets/processed/` now hold v2.1.0, which is also separately
snapshotted at `training/datasets/versions/v2.1.0/` for reproducibility.
`model_config_v1_1.yaml` points at that frozen v2.1.0 snapshot specifically
(not the live path), so this config keeps reproducing the same run even if
the dataset changes again later.

What was added, all appended (nothing existing was edited or removed):

- **+30 UNKNOWN examples** (31 -> 61) - genuinely ambiguous/gibberish/
  trailing-off utterances in en/hi/hinglish, distinct from the existing 31.
- **+71 context-mode examples across all 7 modes**, weighted toward the
  weakest ones - SLEEPING +10, BUSY +10, MEETING +10, TRAVELLING +12,
  UNAVAILABLE +12, CUSTOM +12, NORMAL +5. Context distribution went from a
  7-to-54 spread (a 7.7x imbalance) to 19-to-60 (a 3.2x imbalance).
- **+25 hard negatives** - the same "surface keyword says one thing, the
  correct label is another" pattern as the original 20 (e.g. "Not
  cancelling anything, just confirming the schedule" -> SCHEDULE_REQUEST,
  not CANCEL_REQUEST; "He's busy but this really can't wait" -> URGENT_CALL,
  not SET_CONTEXT/BUSY).

### v2.1.0 statistics (validated, from `training/datasets/processed/STATS.json`)

- **866 total examples** (850 unified for classification + 16 summaries),
  up from 740/724 in v2.0.0.
- **Train/val: 724 / 126**, stratified by intent (every class ≥4 val
  examples, none exactly 1).
- All 17 intents and all 13 actions still ≥30 examples (SET_CONTEXT is now
  115 due to the context expansion - expected, since every context example
  is also a SET_CONTEXT-intent example; no other intent moved by more than
  the deliberate UNKNOWN/hard-negative additions).
- Context distribution: NORMAL 60, BUSY 23, MEETING 23, SLEEPING 21,
  TRAVELLING 21, CUSTOM 20, UNAVAILABLE 19.
- Language: en 428, hi 256, hinglish 166.
- `python -m training.preprocessing.validate` and
  `python -m training.preprocessing.stats` both run clean against this
  dataset (see "Train it yourself" above for the exact commands) -
  confirmed in this session; **no training was run**.

## WOW Brain v2 - training on the 33K annotation dataset

`training/configs/model_config_v2.yaml` points at
`training/datasets/versions/v3.2.0-train-ready/` (33,000 examples: 26,140
train / 3,378 val / 3,482 test - see that directory's `STATS.json` for the
full dataset-preparation report, including duplicate-cluster and class-
imbalance stats). Architecture and hyperparameters are kept identical to
v1 (`distilbert-base-multilingual-cased`, max_length 64, batch_size 16, lr
3e-5, up to 20 epochs, class-weighted cross-entropy, early stopping
patience 4) - the dataset is the only real experimental variable in this
run, so a v1-vs-v2 comparison is meaningful.

Run it yourself:

```powershell
cd <path-to-your-clone-of-wow-ai>
& ".\backend\.venv\Scripts\python.exe" -m training.training.train --config training\configs\model_config_v2.yaml
```

This machine has no CUDA GPU (AMD integrated graphics; the installed torch
build is CPU-only regardless), so `training_device: auto` resolves to CPU -
same as v1. With ~26K training examples per head (vs. v1's 615), expect
this to take **very roughly 3-10 hours** on a CPU-only machine - that range
reflects genuine uncertainty in the estimate, not a measured number; the
first epoch's logged `epoch_seconds`/`samples_per_sec` (see "What the
training log will show" above) will show the real pace within minutes of
starting.

### Resuming an interrupted run

Every epoch now writes `{output_dir}/{head}/checkpoint.pt` (model +
optimizer + RNG + history state) and `checkpoint_best.pt` (best-so-far
weights) - added specifically because this run is long enough on CPU that
interruption is a real possibility. To resume after a stop (Ctrl+C, crash,
reboot), rerun the exact same command with `--resume` appended:

```powershell
& ".\backend\.venv\Scripts\python.exe" -m training.training.train --config training\configs\model_config_v2.yaml --resume
```

Each head resumes independently from its own last completed epoch (a head
that already finished is a no-op; a head still in progress continues from
where it left off) - training does not restart from epoch 1. Verified with
a fast synthetic dry run (`prajjwal1/bert-tiny`, a handful of examples)
before this was documented; not exercised on the real 33K run itself since
that run had not started when this was written.

### Known dataset gap found during pre-flight verification

`ANSWER_CALL` has **zero** examples anywhere in the 33K dataset (train,
val, or test) - the model cannot learn to predict it, unlike v1 which had
explicit `ANSWER_CALL` examples in its hand-authored data. This is a real
gap in the annotated 33K relative to v1's dataset, not a bug in training -
worth knowing before comparing v1 and v2 on that specific action.

## WOW Brain v3 - training on v3.3.0-answer-call (GPU)

`training/configs/model_config_v3.yaml` closes the `ANSWER_CALL` gap above:
it points at `training/datasets/versions/v3.3.0-answer-call/` (66,000
records - the 33K + 30,000 sampled ANSWER_CALL examples, 10K each of
hi/hinglish/en, + 3,000 hard negatives; see that directory's `STATS.json`
for the full dataset-preparation report). This is a fresh experiment, not
a continuation of v2 - v2's checkpoint (trained on the old 33K-only
dataset) is deliberately not resumed; v3 initializes from the same
pretrained base model v1/v2 did. Architecture and hyperparameters are
otherwise identical to v1/v2.

This preparation machine has no NVIDIA GPU (confirmed via `nvidia-smi`
absence and `torch.cuda.is_available() == False` on a CPU-only torch
build), so v3's first 14 epochs (see `training/models/wow-brain/v3/intent/checkpoint.pt`)
were actually trained on **CPU**, with `training_device: "cpu"` set
explicitly in `model_config_v3.yaml` for exactly that run (see "Training
device selection" below for why an explicit value, not `"auto"`, is used -
so a mismatch between what you asked for and what actually ran is never
silently possible).

Continuing training on a CUDA GPU (e.g. Kaggle's T4s) does **not** require
editing that checked-in default: `TrainingConfig.load` reads the
`TRAINING_DEVICE` environment variable first, which overrides the YAML
value with zero code/config changes -

```powershell
$env:TRAINING_DEVICE = "cuda"
& ".\backend\.venv\Scripts\python.exe" -m training.training.train --config training\configs\model_config_v3.yaml --resume
```

See [`docs/KAGGLE_TRAINING.md`](KAGGLE_TRAINING.md) for the full, step-by-step
cloud GPU workflow (environment setup, dataset/checkpoint placement, the
exact resume command, and how to pull trained checkpoints back down) - this
section stays focused on what v3 is and why its config looks the way it
does.

`batch_size: 16` matches v1/v2 - a proven-safe default, not verified
against real GPU VRAM before the CPU run above started. Once real GPU VRAM
is known (e.g. a T4's 16GB), this can likely be raised (e.g. 32-64) for
faster throughput - confirm on the actual hardware rather than assuming,
and treat it as a deliberate experiment change, not something to flip
mid-resume (changing `batch_size` mid-run changes the optimizer's effective
step size/schedule versus the epochs already completed at `batch_size: 16`).
Mixed precision (AMP/fp16) is **not implemented** in `train.py` - the
training loop is plain FP32 throughout; a real, straightforward future
enhancement for GPU throughput, not required to resume training as-is.

## Evaluation methodology

`training/evaluation/evaluate.py` scores the rule-based baseline and every
named model version passed via `--model-dir NAME=PATH` (repeatable) on the
same held-out `val.jsonl`, and reports for each:

- Intent / context / action accuracy
- Structured output validity (100% is required - every prediction must be
  a real taxonomy member or `None`, never garbage)
- Ambiguous/UNKNOWN accuracy (does the model correctly recognize when it
  shouldn't confidently classify something)
- Per-language intent accuracy
- **Per-intent accuracy** (`per_intent_accuracy`) - isolates classes the
  model is weak on, which an aggregate accuracy number can hide
- **Mode-collapse detection** (`most_predicted_intent`,
  `most_predicted_intent_share`, `mode_collapse_suspected`) - flags when
  over 50% of all predictions are the same intent, the exact v0 failure
  signature
- **Intent confusion matrix** (`intent_confusion_matrix`) - full
  expected-vs-predicted breakdown
- Concrete failure examples (text, expected vs predicted, per field)

Nothing here is tuned to make any model look good: every number is
computed directly from predictions against `val.jsonl`, and the same
val.jsonl (same seed, same split) is used for every model version compared,
so version-to-version deltas are meaningful. See
`training/evaluation/latest_report.json` for the most recent full report,
and the v0-vs-v1 comparison in the project history for how v1 was actually
judged against v0.

## Training device selection (CPU/CUDA/MPS)

`training/training/device.py:resolve_training_device` picks where a
training run executes, controlled by `training_device` in the config YAML
(`"auto"` default, or `"cpu"`/`"cuda"`/`"mps"` explicitly):

- **`"auto"`** (default): CUDA -> MPS -> CPU, first available wins.
- **`"cpu"`/`"cuda"`/`"mps"`**: used as requested; if the requested
  accelerator isn't actually available, training fails immediately with a
  clear `RuntimeError` rather than silently falling back to CPU and
  reporting numbers that look like they came from a GPU run.

Every run logs the resolved device up front:

```
Training device: cpu
CUDA available: False  MPS available: False
```

(or, on a CUDA machine: `Training device: cuda` plus the GPU name and
memory). This is written to the run's console output and to
`metadata.json`'s `device` field, so a model's provenance always shows what
hardware trained it. Per-epoch history also records `epoch_seconds` and
`samples_per_sec` for that reason - see a head's `history` list in
`metadata.json`.

The v0 and v1 runs in this repository both used **CPU** - this development
machine (AMD Ryzen 5 5500U, integrated graphics) has no CUDA-capable GPU
and no Apple Silicon, and the installed torch build is CPU-only
(`torch==2.13.0+cpu`, confirmed via `torch.cuda.is_available() == False`
before either run). `training_device: "auto"` in `model_config_v1.yaml`
means a GPU-equipped machine would use it automatically with zero config
changes, but none was available for either training run in this repo's
history.

One provenance note: the device-selection/logging code above
(`training/training/device.py`, and `main()`'s device-resolution and
per-epoch timing) was added *after* the v1 training run already in
progress had started - a running Python process doesn't pick up source
edits mid-run, so `training/models/wow-brain/v1/metadata.json` from that
specific run predates the `device`/`epoch_seconds`/`samples_per_sec`
fields and won't have them. The feature is real and covered by
`training/tests/test_device.py` / `backend/tests/test_ml_device.py`; it
applies starting with the next training run, not retroactively to v1's
existing artifacts.

### Training vs. inference device

These are two independent settings, deliberately never linked:

- **Training device** (`training_device` in a training config YAML,
  `training/training/device.py`): where a model gets *fine-tuned*. Defaults
  to `"auto"` - use a GPU if one shows up, since training is the
  expensive, one-off part.
- **Inference device** (`Settings.inference_device` in
  `backend/app/config.py`, `backend/app/ml/device.py`): where
  `LocalWOWModelProvider` runs *predictions* in the running backend.
  Defaults to `"cpu"` - **always**, regardless of what trained the model.
  WOW's target Phase 1 deployment is a personal server or phone-adjacent
  box, not a GPU box, so inference must not silently start requiring a GPU
  just because training happened to use one. Set
  `INFERENCE_DEVICE=cuda`/`mps`/`auto` explicitly if you're deploying
  somewhere that actually has one.

Neither module modifies any system-wide hardware/driver setting - both are
just picking a `torch.device` for that process's own tensors.

## GPU requirements for production training

Both v0 and v1 configs are chosen to be CPU-trainable in this environment.
For a materially larger dataset or a bigger base model, swap `base_model`
in a config YAML to a larger encoder and set `training_device: "cuda"` (or
leave `"auto"`) on a GPU-equipped machine - no other code changes required,
only that config value and possibly `batch_size`.
