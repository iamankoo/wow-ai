# Training WOW Brain v3 on Kaggle (cloud GPU)

This document is the complete, step-by-step procedure for **continuing**
WOW Brain v3's intent-head training on a Kaggle GPU notebook (2x NVIDIA
Tesla T4). It is preparation and reference material only - it does not
start any training run, and none of the commands below have been executed
against Kaggle by anyone but you.

**Read this first:**

- v3's intent head already has **14 completed epochs** of real training
  history (CPU-trained locally; best validation accuracy **94.54%** at
  epoch 10; see `training/models/wow-brain/v3/intent/checkpoint.pt`). The
  whole point of this workflow is to **resume** that checkpoint on a GPU,
  not start a new model from epoch 1.
- Nothing in this document should ever be run with `checkpoint.pt` absent
  from `--resume`'s expected path, or without first running the pre-flight
  script in step 8. If in doubt, stop and re-check rather than launch.

## 0. What ships in the Git repo vs. what you bring separately

`training/models/` and `training/datasets/versions/` are intentionally
**not** committed to Git (see `.gitignore`) - the 1.6GB checkpoint and the
66,000-record dataset are exactly the kind of large, regenerable/personal
artifacts that don't belong in ordinary Git history. The repository ships
the *code* that produces and consumes them:

| Ships in Git | Brought separately (Kaggle Dataset upload) |
|---|---|
| `training/training/train.py`, `config.py`, `device.py` | `training/models/wow-brain/v3/` (the checkpoint) |
| `training/configs/model_config_v3.yaml` | `training/datasets/versions/v3.3.0-answer-call/` (the 66K dataset) |
| `training/evaluation/`, `training/inference/` | |
| `training/verify_kaggle_environment.py` | |

## 1. Get WOW AI source onto Kaggle

Two options - pick whichever fits your Kaggle setup:

**A. Kaggle Notebook + GitHub clone (simplest, recommended):**

```bash
!git clone https://github.com/iamankoo/wow-ai.git /kaggle/working/wow-ai
%cd /kaggle/working/wow-ai
```

This works once the repo is pushed to GitHub (see the main README /
project root for the push steps this preparation performed). Use this if
the repo is public, or private with a Kaggle-accessible token.

**B. Upload as a Kaggle Dataset:** zip the repo (excluding `.git/`,
`backend/.venv/`, `training/models/`, `training/datasets/versions/`) and
upload it as a Kaggle Dataset, then attach it to the notebook and copy it
into `/kaggle/working/wow-ai`. Use this if you'd rather not make the repo
public or wire up a GitHub token inside the notebook.

Either way, you end up with the WOW AI source tree at
`/kaggle/working/wow-ai` - that becomes `REPO_ROOT` for every path in
`training/training/config.py`.

## 2. Provide the 66K dataset

The dataset itself is not in Git. Package it as its own Kaggle Dataset:

1. Locally, zip exactly the finalized version directory:
   `training/datasets/versions/v3.3.0-answer-call/` (contains
   `train.jsonl`, `val.jsonl`, `test.jsonl`, `MANIFEST.json`, `STATS.json` -
   see counts below).
2. Upload that zip as a new **private** Kaggle Dataset (Kaggle UI ->
   "New Dataset"). Suggested slug: `wow-ai-v3-3-0-answer-call` (not
   assumed to already exist - create it yourself; nothing in this repo or
   this document hardcodes a slug that isn't real).
3. Attach that dataset to your training notebook (Add Data -> your dataset).
   It will mount read-only at `/kaggle/input/<your-dataset-slug>/`.

**Verified dataset counts** (from `MANIFEST.json`/`STATS.json`, checksummed
against the actual files - not assumed):

| Split | Records |
|---|---|
| train.jsonl | 52,514 |
| val.jsonl | 6,701 |
| test.jsonl | 6,785 |
| **Total** | **66,000** |

| Category | Count |
|---|---|
| ANSWER_CALL action examples | 30,000 (10,000 each: en / hi / hinglish) |
| Hard negatives | 3,000 |
| Existing (pre-v3.3.0) examples | 33,000 |

## 3. Provide the v3 Intent checkpoint

Also not in Git - package it separately:

1. Locally, zip `training/models/wow-brain/v3/` (contains `intent/checkpoint.pt`,
   `intent/checkpoint_best.pt`, and the head's tokenizer/config export files).
   This is the ~1.6GB checkpoint - do this once, not on every notebook run.
2. Upload as another private Kaggle Dataset, e.g. `wow-ai-v3-intent-checkpoint`.
3. Attach it to the notebook the same way. It mounts read-only at
   `/kaggle/input/<checkpoint-dataset-slug>/`.

**Kaggle input datasets are read-only** - training must not write directly
into `/kaggle/input/...`. Step 5 below copies the checkpoint into the
writable working checkout before training, which is exactly where
`train.py` looks for it (see step 6's path explanation).

## 4. Designed Kaggle filesystem layout

```
/kaggle/input/
├── <wow-ai-source>/                       (only if using option B in step 1)
├── wow-ai-v3-3-0-answer-call/             (read-only, from step 2)
│   ├── train.jsonl
│   ├── val.jsonl
│   ├── test.jsonl
│   ├── MANIFEST.json
│   └── STATS.json
└── wow-ai-v3-intent-checkpoint/           (read-only, from step 3)
    └── v3/
        └── intent/
            ├── checkpoint.pt
            ├── checkpoint_best.pt
            ├── config.json
            ├── model.safetensors
            ├── tokenizer.json
            └── tokenizer_config.json

/kaggle/working/wow-ai/                     (writable checkout, from step 1)
├── backend/
├── docs/
├── training/
│   ├── configs/model_config_v3.yaml
│   ├── datasets/versions/v3.3.0-answer-call/   <- copied in, step 5
│   ├── models/wow-brain/v3/                    <- copied in, step 5 (writable)
│   ├── training/train.py
│   └── verify_kaggle_environment.py
└── ...
```

The exact dataset/checkpoint slugs above (`wow-ai-v3-3-0-answer-call`,
`wow-ai-v3-intent-checkpoint`) are **suggestions for you to create** - they
don't exist yet and nothing in this repo assumes they do. Substitute
whatever slugs Kaggle actually assigns your uploads in the commands below.

## 5. Wire the inputs into the working checkout

`training/training/config.py` resolves `dataset_dir` and `output_dir` as
`REPO_ROOT / "training/datasets/versions/v3.3.0-answer-call"` and
`REPO_ROOT / "training/models/wow-brain/v3"` respectively - both **relative
paths inside the repo checkout**, not absolute/machine-specific ones. So
the simplest way to make Kaggle's mounted inputs visible to an unmodified
`model_config_v3.yaml` is to copy them into those exact relative locations
inside `/kaggle/working/wow-ai`:

```bash
%cd /kaggle/working/wow-ai

# Dataset: read-only source is fine, a copy keeps things simple and fast (local disk).
mkdir -p training/datasets/versions/v3.3.0-answer-call
cp /kaggle/input/wow-ai-v3-3-0-answer-call/*.json* training/datasets/versions/v3.3.0-answer-call/

# Checkpoint: MUST be a writable copy, not a symlink into read-only
# /kaggle/input - the training loop overwrites checkpoint.pt every epoch.
mkdir -p training/models/wow-brain/v3
cp -r /kaggle/input/wow-ai-v3-intent-checkpoint/v3/* training/models/wow-brain/v3/
```

## 6. Install dependencies

```bash
%cd /kaggle/working/wow-ai
pip install -r backend/requirements.txt -r backend/requirements-local-model.txt
```

Kaggle's base image already ships a CUDA-enabled PyTorch build matched to
its driver - do **not** `pip install torch` over it unless you have a
specific reason to pin a different version; reinstalling torch can replace
Kaggle's pre-linked CUDA build with a CPU-only wheel.

## 7. Verify CUDA, the GPU(s), and PyTorch's CUDA build

```bash
!nvidia-smi
```

Expect two `Tesla T4` entries. Then:

```python
import torch
print(torch.__version__, torch.version.cuda, torch.cuda.is_available())
print(torch.cuda.device_count(), [torch.cuda.get_device_name(i) for i in range(torch.cuda.device_count())])
```

Expect `torch.cuda.is_available() == True` and `device_count == 2`.

## 8. Run the pre-flight verification script (no training)

This is the single command that verifies everything above end-to-end -
CUDA, device-selection logic, dataset checksums/counts, checkpoint
load + resume metadata, and tokenizer/model loading - and refuses to
proceed if anything is wrong. It performs **zero** training steps.

```bash
%cd /kaggle/working/wow-ai
python -m training.verify_kaggle_environment --require-cuda
```

Read its output carefully. It must end with:

```
All checks passed. No training was started by this script.
```

In particular, confirm section "4. Resume checkpoint" reports:

```
completed epochs: 14 | resume will start at epoch 15 (1-indexed)
best val_accuracy so far: 0.9453812863751679 @ epoch 10
```

**If you see `completed epochs: 0` here, STOP.** That means the checkpoint
copy in step 5 didn't happen (or didn't land at
`training/models/wow-brain/v3/intent/checkpoint.pt`) and training would
start over from a fresh pretrained model - re-verify step 5 before going
any further.

## 9. Launch the training command (resume, GPU)

Only after step 8 passes cleanly:

```bash
%cd /kaggle/working/wow-ai
TRAINING_DEVICE=cuda python -m training.training.train \
    --config training/configs/model_config_v3.yaml \
    --resume
```

`TRAINING_DEVICE=cuda` overrides `model_config_v3.yaml`'s checked-in
`training_device: "cpu"` (that value documents how the first 14 epochs
were actually trained locally - see `docs/TRAINING.md`) without editing
any file. `--resume` is what makes this a continuation: `train.py` loads
`checkpoint.pt`, restores model/optimizer/RNG/early-stopping state, and
continues from `next_epoch` - it does **not** reinitialize the model. Each
of the three heads (`intent`, `context`, `action`) resumes independently
from its own checkpoint if one exists.

This is the exact command to run manually on Kaggle. It is documented
here, not executed by this preparation.

## 10. Resuming again after an interruption

Kaggle sessions have a wall-clock/idle limit. If training stops (session
timeout, manual interrupt, crash), rerun the **identical** command from
step 9 - `train.py` writes `checkpoint.pt` after every completed epoch
specifically so an interruption never loses more than the epoch in
progress:

```bash
TRAINING_DEVICE=cuda python -m training.training.train \
    --config training/configs/model_config_v3.yaml \
    --resume
```

Re-run `python -m training.verify_kaggle_environment --require-cuda`
first if you're unsure how far a prior session got - its "completed
epochs" line tells you exactly where a resume will pick up.

## 11. Where checkpoints are saved

Every epoch, for each head, `train.py` writes to
`{output_dir}/{head}/` (i.e. `training/models/wow-brain/v3/{head}/` inside
the working checkout):

- `checkpoint.pt` - full resumable state (model + optimizer + RNG +
  history). Overwritten every epoch.
- `checkpoint_best.pt` - weights only, from the best validation-accuracy
  epoch so far. Overwritten only when a new best is found.

`/kaggle/working/` is **ephemeral** - it does not persist once the session
ends unless you explicitly save it as Kaggle Notebook Output or a new
Kaggle Dataset version. Do this before your session limit is reached, not
after.

## 12. Downloading checkpoints back from Kaggle

Two supported ways:

**A. Kaggle Notebook Output (simplest):** in a Kaggle Notebook, any file
under `/kaggle/working/` at the end of a committed run is automatically
attached as notebook output and downloadable from the Kaggle UI
("Output" tab) or via the Kaggle API:

```bash
kaggle kernels output <your-username>/<your-notebook-slug> -p ./downloaded
```

**B. Periodic Kaggle Dataset version (for long/interrupted runs):**
mid-run (or at natural checkpoints), create/update a private Kaggle
Dataset from `training/models/wow-brain/v3/` so progress survives even if
the notebook session itself is lost:

```bash
kaggle datasets version -p training/models/wow-brain/v3 -m "epoch N checkpoint"
```

Then download it locally with `kaggle datasets download`.

After downloading, place the checkpoint back at
`training/models/wow-brain/v3/intent/checkpoint.pt` in your local clone if
you want to resume locally, evaluate it with
`training/evaluation/evaluate.py`, or run `training/inference/predict.py`
against it.

## 13. How to avoid accidentally starting from epoch 1

- Always run `python -m training.verify_kaggle_environment --require-cuda`
  (step 8) before the training command, and read its "completed epochs"
  line.
- Always pass `--resume`. Without it, `train.py` starts every head fresh
  from the pretrained base model regardless of what's in `checkpoint.pt`.
- Never delete or skip copying `checkpoint.pt` into
  `training/models/wow-brain/v3/intent/` before training - `--resume` is a
  no-op (with a printed note, not silent) if that file isn't present, and
  training then proceeds as a fresh run.
- Treat `/kaggle/input/...` as read-only, always. Never point `output_dir`
  at a read-only mount - `train.py` needs to write there every epoch, and
  a failed write is a much worse failure mode than starting a normal,
  loud error.
- Don't edit `model_config_v3.yaml`'s `epochs: 20` down below 15 while
  resuming a checkpoint that already has 14 completed epochs - `train.py`
  would report the head as already fully trained and exit its loop
  immediately, without it being obvious why.

## Reference: exact commands summary

```bash
# 1. Get source
git clone https://github.com/iamankoo/wow-ai.git /kaggle/working/wow-ai
cd /kaggle/working/wow-ai

# 2-5. Wire in dataset + checkpoint (see step 5 for the exact copy commands)

# 6. Install deps
pip install -r backend/requirements.txt -r backend/requirements-local-model.txt

# 7-8. Verify (no training)
nvidia-smi
python -m training.verify_kaggle_environment --require-cuda

# 9. Train (resume) - THE ACTUAL TRAINING COMMAND, run manually, not by this preparation
TRAINING_DEVICE=cuda python -m training.training.train --config training/configs/model_config_v3.yaml --resume

# 10. Resume again after any interruption - identical command
TRAINING_DEVICE=cuda python -m training.training.train --config training/configs/model_config_v3.yaml --resume
```
