"""Safe, read-only pre-flight check for training WOW Brain v3 on a cloud GPU
(Kaggle or otherwise). Verifies everything that can be verified WITHOUT
starting a training run: CUDA/GPU visibility, PyTorch's CUDA build, base
model + tokenizer loading, the v3.3.0-answer-call dataset (manifest
checksums + counts), and that the v3 intent checkpoint loads and reports
the expected epoch/history state for `--resume`.

This script never calls `training.training.train.main` and never runs a
training/optimizer step. It is meant to be the last thing you run on a
Kaggle notebook/session before launching the real training command from
docs/KAGGLE_TRAINING.md.

Usage (from the repo root, e.g. /kaggle/working/wow-ai):
    python -m training.verify_kaggle_environment
    python -m training.verify_kaggle_environment --config training/configs/model_config_v3.yaml

Exit code is 0 only if every check passes. Any failure prints a clear
[FAIL] line and the script exits non-zero - it does not try to "fix"
anything or fall back silently.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

from training.training.config import DEFAULT_CONFIG_PATH, REPO_ROOT, TrainingConfig
from training.training.device import describe_device, resolve_training_device

V3_CONFIG_PATH = REPO_ROOT / "training" / "configs" / "model_config_v3.yaml"

_failures: list[str] = []


def _ok(msg: str) -> None:
    print(f"[ OK ] {msg}")


def _warn(msg: str) -> None:
    print(f"[WARN] {msg}")


def _fail(msg: str) -> None:
    print(f"[FAIL] {msg}")
    _failures.append(msg)


def check_torch_cuda(require_cuda: bool) -> None:
    print("\n== 1. PyTorch / CUDA ==")
    try:
        import torch
    except ImportError as e:
        _fail(f"Could not import torch: {e}")
        return

    _ok(f"torch {torch.__version__}")
    cuda_available = torch.cuda.is_available()
    if cuda_available:
        _ok(f"torch.cuda.is_available() = True (CUDA build: {torch.version.cuda})")
    elif require_cuda:
        _fail(
            "torch.cuda.is_available() = False - this torch build has no working "
            "CUDA support, or no GPU is attached to this session. On Kaggle: "
            "enable a GPU accelerator (Settings -> Accelerator -> GPU T4 x2) and "
            "make sure the session was restarted after enabling it."
        )
    else:
        _warn(
            "torch.cuda.is_available() = False (expected on a local CPU-only "
            "machine; this is only a hard failure with --require-cuda, i.e. "
            "when actually running this on Kaggle)."
        )

    if cuda_available:
        device_count = torch.cuda.device_count()
        _ok(f"{device_count} CUDA device(s) visible")
        for i in range(device_count):
            name = torch.cuda.get_device_name(i)
            mem_gb = torch.cuda.get_device_properties(i).total_memory / (1024**3)
            _ok(f"  cuda:{i} - {name} ({mem_gb:.1f} GB)")
        if device_count < 1:
            _fail("CUDA reported available but device_count is 0.")


def check_device_selection(require_cuda: bool) -> None:
    print("\n== 2. Device-selection logic (training/training/device.py) ==")
    requested = "cuda" if require_cuda else "auto"
    try:
        device = resolve_training_device(requested)
        info = describe_device(device)
        _ok(f"resolve_training_device({requested!r}) -> {device} | {info}")
        if require_cuda and device.type != "cuda":
            _fail(f"Requested cuda but resolved to {device.type} - should have raised instead.")
    except RuntimeError as e:
        if require_cuda:
            _fail(f"resolve_training_device('cuda') raised: {e}")
        else:
            _ok(f"resolve_training_device('cuda') correctly raised (no silent CPU fallback): {e}")


def check_dataset(dataset_dir: Path) -> None:
    print(f"\n== 3. Dataset ({dataset_dir}) ==")
    manifest_path = dataset_dir / "MANIFEST.json"
    if not manifest_path.exists():
        _fail(f"MANIFEST.json not found at {manifest_path}")
        return
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    _ok(f"MANIFEST.json loaded (generated_at={manifest.get('generated_at')})")

    counts = {}
    for entry in manifest.get("files", []):
        path = dataset_dir / entry["path"]
        if not path.exists():
            _fail(f"Missing dataset file listed in manifest: {path}")
            continue
        actual_size = path.stat().st_size
        if actual_size != entry["size_bytes"]:
            _fail(f"{entry['path']}: size mismatch (manifest {entry['size_bytes']}, actual {actual_size})")
            continue
        sha256 = hashlib.sha256(path.read_bytes()).hexdigest()
        if sha256 != entry["sha256"]:
            _fail(f"{entry['path']}: sha256 mismatch (manifest {entry['sha256']}, actual {sha256})")
            continue
        _ok(f"{entry['path']}: sha256 verified, {entry['line_count']} lines, {actual_size:,} bytes")
        counts[entry["path"]] = entry["line_count"]

    train_n = counts.get("train.jsonl")
    val_n = counts.get("val.jsonl")
    test_n = counts.get("test.jsonl")
    if train_n and val_n and test_n:
        total = train_n + val_n + test_n
        _ok(f"train={train_n:,} val={val_n:,} test={test_n:,} total={total:,}")


def check_checkpoint(output_dir: Path, head_name: str, expected_epochs: int) -> None:
    print(f"\n== 4. Resume checkpoint ({output_dir / head_name}) ==")
    import torch

    head_dir = output_dir / head_name
    ckpt_path = head_dir / "checkpoint.pt"
    best_path = head_dir / "checkpoint_best.pt"

    if not ckpt_path.exists():
        _warn(
            f"{ckpt_path} not found - a run without --resume would start this "
            f"head from the pretrained base model (epoch 1), not from prior "
            f"progress. If you intended to continue existing training, verify "
            f"the checkpoint was copied into place (see docs/KAGGLE_TRAINING.md)."
        )
        return

    ckpt = torch.load(ckpt_path, map_location="cpu", weights_only=False)
    next_epoch = ckpt.get("next_epoch")
    history = ckpt.get("history", [])
    completed = len(history)
    best_val = ckpt.get("stopper_best")
    best_epoch = ckpt.get("stopper_best_epoch")

    _ok(f"checkpoint.pt loads cleanly ({ckpt_path.stat().st_size / 1e9:.2f} GB)")
    _ok(f"completed epochs: {completed} | resume will start at epoch {next_epoch + 1} (1-indexed)")
    _ok(f"best val_accuracy so far: {best_val} @ epoch {best_epoch}")
    _ok(f"model_state_dict present: {'model_state_dict' in ckpt} | optimizer_state_dict present: {'optimizer_state_dict' in ckpt}")

    if next_epoch == 0 and completed == 0:
        _warn("next_epoch is 0 with empty history - this looks like an untouched/fresh checkpoint, not a resumed one.")
    if completed >= expected_epochs:
        _warn(
            f"This checkpoint already has {completed} epochs of history >= "
            f"the configured {expected_epochs} epochs - resuming will find "
            f"nothing left to train for this head (expected, not an error, "
            f"if training already finished)."
        )

    if best_path.exists():
        best_ckpt = torch.load(best_path, map_location="cpu", weights_only=False)
        _ok(
            f"checkpoint_best.pt loads cleanly - epoch {best_ckpt.get('epoch')}, "
            f"val_accuracy {best_ckpt.get('val_accuracy')}"
        )
    else:
        _warn(f"{best_path} not found (no best-checkpoint snapshot yet).")


def check_tokenizer_and_model(base_model: str) -> None:
    print(f"\n== 5. Base model + tokenizer ({base_model}) ==")
    try:
        from transformers import AutoModelForSequenceClassification, AutoTokenizer
    except ImportError as e:
        _fail(f"Could not import transformers: {e}")
        return

    try:
        tok = AutoTokenizer.from_pretrained(base_model)
        _ok(f"tokenizer loaded: {type(tok).__name__}, vocab_size={tok.vocab_size}")
    except Exception as e:  # noqa: BLE001 - report and continue
        _fail(f"Tokenizer load failed: {e}")
        return

    try:
        model = AutoModelForSequenceClassification.from_pretrained(base_model, num_labels=17)
        n_params = sum(p.numel() for p in model.parameters())
        _ok(f"model loaded: {type(model).__name__}, {n_params:,} parameters")
    except Exception as e:  # noqa: BLE001
        _fail(f"Model load failed: {e}")
        return

    enc = tok("Hello, testing the WOW Brain pipeline", return_tensors="pt")
    out = model(**enc)
    _ok(f"forward pass OK, logits shape={tuple(out.logits.shape)}")


def print_commands(config_path: Path) -> None:
    print("\n== 6. Commands (for reference - NOT executed by this script) ==")
    rel = config_path.relative_to(REPO_ROOT).as_posix() if config_path.is_relative_to(REPO_ROOT) else str(config_path)
    print(f"  Fresh/continue run:  TRAINING_DEVICE=cuda python -m training.training.train --config {rel}")
    print(f"  Resume run:          TRAINING_DEVICE=cuda python -m training.training.train --config {rel} --resume")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=V3_CONFIG_PATH)
    parser.add_argument(
        "--require-cuda", action="store_true",
        help="Fail (non-zero exit) if CUDA is not available. Pass this on Kaggle; "
             "omit it for a local CPU-only dry run of the non-GPU checks.",
    )
    args = parser.parse_args()

    config_path = args.config if args.config.is_absolute() else REPO_ROOT / args.config
    print(f"WOW AI - Kaggle/CUDA pre-flight check\nrepo root: {REPO_ROOT}\nconfig: {config_path}")

    if not config_path.exists():
        _fail(f"Config file not found: {config_path}")
        cfg = None
    else:
        cfg = TrainingConfig.load(config_path)
        _ok(f"config loaded - base_model={cfg.base_model} epochs={cfg.epochs} batch_size={cfg.batch_size}")

    check_torch_cuda(require_cuda=args.require_cuda)
    check_device_selection(require_cuda=args.require_cuda)

    if cfg is not None:
        check_dataset(cfg.dataset_dir)
        check_checkpoint(cfg.output_dir, "intent", cfg.epochs)
        check_tokenizer_and_model(cfg.base_model)
        print_commands(config_path)

    print("\n" + "=" * 60)
    if _failures:
        print(f"{len(_failures)} check(s) FAILED:")
        for f in _failures:
            print(f"  - {f}")
        print("\nDo NOT start training until every [FAIL] above is resolved.")
        return 1

    print("All checks passed. No training was started by this script.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
