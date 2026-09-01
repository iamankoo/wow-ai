"""Trains a WOW Brain model version: one lightweight text-classification head
per prediction target (intent, context, action), fine-tuned from the
open-weight base model named in the config. Which version gets trained
(v0, v1, ...) is entirely determined by which config file is passed - see
training/configs/model_config.yaml (v0) and model_config_v1.yaml (v1).

This is a genuine, reproducible training run - not a placeholder. It uses a
plain PyTorch loop (no `transformers.Trainer`/`accelerate` dependency) so it
has the minimum possible dependency footprint beyond torch+transformers,
which keeps it runnable on CPU-only machines like this one. Per epoch it
computes validation accuracy, keeps the best-performing checkpoint in memory
(not necessarily the last epoch's), and optionally applies class-weighted
cross-entropy and early stopping - see compute_class_weights/EarlyStopper
below and docs/TRAINING.md "Training improvements for v1".

Usage:
    python -m training.training.train
    python -m training.training.train --config training/configs/model_config_v1.yaml
"""

import argparse
import copy
import json
import random
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

from training.training.config import DEFAULT_CONFIG_PATH, HeadConfig, TrainingConfig, REPO_ROOT


def _load_jsonl(path: Path) -> list[dict]:
    with path.open(encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


def _read_dataset_version(dataset_dir: Path) -> str:
    """Prefers the versioned-dataset convention (training/datasets/versions/<version>/
    directories, identified by their own MANIFEST.json - see
    training/pipeline/versioning.py) where the directory name IS the
    version. Falls back to the older DATASET_METADATA.json convention used
    by v0/v1's dataset_dir="training/datasets/processed", so this still
    reports correctly for those configs."""
    if (dataset_dir / "MANIFEST.json").exists():
        return dataset_dir.name
    meta_path = REPO_ROOT / "training" / "datasets" / "DATASET_METADATA.json"
    if meta_path.exists():
        return json.loads(meta_path.read_text(encoding="utf-8")).get("dataset_version", "unknown")
    return "unknown"


def set_seed(seed: int) -> None:
    import numpy as np
    import torch

    random.seed(seed)
    np.random.seed(seed)
    torch.manual_seed(seed)


def compute_class_weights(
    records: list[dict], label_field: str, label2id: dict[str, int]
) -> list[float]:
    """Balanced class weights (`total / (num_classes * count[c])`), the same
    formula as sklearn's `class_weight='balanced'`. Pure Python, no torch
    dependency, so this is unit-testable without loading any model.

    This is the direct fix for the v0 mode-collapse failure: with an
    imbalanced dataset and unweighted cross-entropy, the loss-minimizing
    strategy is to always predict the majority class. Weighting each class
    inversely to its frequency removes that incentive.
    """
    counts = Counter(r[label_field] for r in records if r.get(label_field) is not None)
    total = sum(counts.values())
    num_classes = len(label2id)
    weights = [0.0] * num_classes
    for label, idx in label2id.items():
        count = counts.get(label, 0)
        weights[idx] = (total / (num_classes * count)) if count > 0 else 0.0
    return weights


class EarlyStopper:
    """Tracks the best value of a metric (higher is better) across epochs and
    reports whether training should stop after `patience` non-improving
    epochs in a row. `patience <= 0` disables early stopping entirely.
    """

    def __init__(self, patience: int):
        self.patience = patience
        self.best: float | None = None
        self.best_epoch: int | None = None
        self._bad_epochs = 0

    def step(self, epoch: int, value: float) -> bool:
        """Records this epoch's metric value. Returns True if it's a new best."""
        improved = self.best is None or value > self.best
        if improved:
            self.best = value
            self.best_epoch = epoch
            self._bad_epochs = 0
        else:
            self._bad_epochs += 1
        return improved

    @property
    def should_stop(self) -> bool:
        return self.patience > 0 and self._bad_epochs >= self.patience


def _evaluate(model, val_ds, device, batch_size: int = 32) -> float | None:
    """Batched evaluation. Was previously one example at a time (batch size
    1, no DataLoader) - a real, measured inefficiency: on the v3.2.0-
    train-ready dataset (3,378 val examples) that cost ~13 minutes per
    epoch on CPU by itself. This computes the exact same accuracy (just
    counting correct/total, order-independent) in batched forward passes
    instead - same result, meaningfully faster since it does not need one
    Python-level model call per example."""
    import torch
    from torch.utils.data import DataLoader

    if len(val_ds) == 0:
        return None
    model.eval()
    correct = 0
    loader = DataLoader(val_ds, batch_size=batch_size, shuffle=False)
    with torch.no_grad():
        for batch in loader:
            batch_labels = batch.pop("labels").to(device)
            batch = {k: v.to(device) for k, v in batch.items()}
            logits = model(**batch).logits
            preds = logits.argmax(dim=-1)
            correct += int((preds == batch_labels).sum().item())
    return correct / len(val_ds)


def train_head(
    head: HeadConfig, cfg: TrainingConfig, train_records: list[dict], val_records: list[dict], device,
    resume: bool = False,
) -> dict:
    """Trains one head. If resume=True and a checkpoint.pt already exists in
    this head's output directory, training continues from the epoch after
    the checkpoint rather than restarting - model weights, optimizer state,
    RNG state, early-stopping state, and per-epoch history are all restored
    so the resumed run is a genuine continuation, not a fresh run that
    happens to reuse the same output directory. A checkpoint is written
    after every epoch (overwriting the previous one - this keeps one
    "resume from here" point, not a full history of per-epoch snapshots),
    plus a separate checkpoint_best.pt whenever validation accuracy improves,
    so the best-so-far weights survive even if a later epoch is interrupted
    mid-write."""
    import time

    import numpy as np
    import torch
    import torch.nn.functional as F
    from torch.utils.data import DataLoader, Dataset
    from transformers import AutoModelForSequenceClassification, AutoTokenizer

    try:
        tokenizer = AutoTokenizer.from_pretrained(cfg.base_model)
    except ValueError:
        # Some checkpoints' tokenizer_config.json omits `tokenizer_class`,
        # which trips AutoTokenizer's fast-tokenizer resolution on this
        # transformers version. Fall back to the explicit BERT tokenizer,
        # which covers every base model this config currently targets.
        from transformers import BertTokenizer

        tokenizer = BertTokenizer.from_pretrained(cfg.base_model)

    labels = sorted({
        r[head.label_field]
        for r in train_records + val_records
        if r.get(head.label_field) is not None
    })
    if not labels:
        raise ValueError(f"No labeled records found for head '{head.name}' (field '{head.label_field}')")
    label2id = {label: i for i, label in enumerate(labels)}
    id2label = {i: label for label, i in label2id.items()}

    class ClassificationDataset(Dataset):
        def __init__(self, records: list[dict]):
            self.records = [r for r in records if r.get(head.label_field) is not None]

        def __len__(self) -> int:
            return len(self.records)

        def __getitem__(self, idx: int) -> dict:
            r = self.records[idx]
            enc = tokenizer(
                r["text"], truncation=True, padding="max_length",
                max_length=cfg.max_length, return_tensors="pt",
            )
            item = {k: v.squeeze(0) for k, v in enc.items()}
            item["labels"] = torch.tensor(label2id[r[head.label_field]], dtype=torch.long)
            return item

    train_ds = ClassificationDataset(train_records)
    val_ds = ClassificationDataset(val_records)

    if len(train_ds) == 0:
        raise ValueError(f"No training examples available for head '{head.name}'")

    try:
        model = AutoModelForSequenceClassification.from_pretrained(
            cfg.base_model, num_labels=len(labels)
        )
    except ValueError:
        # Mirrors the tokenizer fallback above: some older checkpoints'
        # config.json predates the `model_type` field AutoConfig requires.
        from transformers import BertForSequenceClassification

        model = BertForSequenceClassification.from_pretrained(
            cfg.base_model, num_labels=len(labels)
        )
    model.config.label2id = label2id
    model.config.id2label = id2label
    model.to(device)

    if cfg.class_weighting:
        class_weights = compute_class_weights(train_records, head.label_field, label2id)
    else:
        class_weights = [1.0] * len(labels)
    class_weights_tensor = torch.tensor(class_weights, dtype=torch.float, device=device)

    train_loader = DataLoader(train_ds, batch_size=cfg.batch_size, shuffle=True)
    optimizer = torch.optim.AdamW(model.parameters(), lr=cfg.learning_rate)

    head_dir = cfg.output_dir / head.name
    head_dir.mkdir(parents=True, exist_ok=True)
    checkpoint_path = head_dir / "checkpoint.pt"
    best_checkpoint_path = head_dir / "checkpoint_best.pt"

    stopper = EarlyStopper(cfg.early_stopping_patience)
    best_state: dict | None = None
    history = []
    start_epoch = 0

    if resume and checkpoint_path.exists():
        # weights_only=False: this checkpoint is one we wrote ourselves (not
        # a third-party download) and includes non-tensor state (RNG state,
        # history) that torch's default weights_only=True safe-unpickler
        # rejects - see docs/TRAINING.md "Resuming training".
        ckpt = torch.load(checkpoint_path, map_location=device, weights_only=False)
        model.load_state_dict(ckpt["model_state_dict"])
        optimizer.load_state_dict(ckpt["optimizer_state_dict"])
        start_epoch = ckpt["next_epoch"]
        history = ckpt["history"]
        stopper.best = ckpt["stopper_best"]
        stopper.best_epoch = ckpt["stopper_best_epoch"]
        stopper._bad_epochs = ckpt["stopper_bad_epochs"]
        random.setstate(ckpt["rng_state_python"])
        np.random.set_state(ckpt["rng_state_numpy"])
        torch.set_rng_state(ckpt["rng_state_torch"])
        if best_checkpoint_path.exists():
            best_state = torch.load(best_checkpoint_path, map_location=device, weights_only=False)["model_state_dict"]
        print(
            f"  [{head.name}] resuming from checkpoint: epoch {start_epoch + 1} "
            f"(best val_acc so far={stopper.best if stopper.best is not None else 'n/a'} "
            f"@ epoch {stopper.best_epoch})"
        )
        if start_epoch >= cfg.epochs:
            print(f"  [{head.name}] checkpoint already completed all {cfg.epochs} configured epochs - skipping training loop")

    # Progress logging inside the epoch, not just once at the end of it -
    # this is the direct fix for a training run that is genuinely still
    # working but LOOKS hung: with a 135M-param model on CPU, one epoch over
    # ~26K examples can take well over an hour (measured: ~5-7s/batch on a
    # 12-logical-core CPU x 1634 batches/epoch), and previously nothing was
    # printed until that entire epoch (train + validation) finished.
    #
    # Logging is TIME-based (at least once every LOG_INTERVAL_SECONDS), not
    # batch-count-based - a fixed "every N batches" schedule looks fine on
    # fast hardware but silently degrades back into long silent gaps on
    # exactly the slow-CPU case this fix targets (a fixed 20-logs/epoch
    # schedule was measured to still leave ~8 minutes of silence between
    # updates on this machine). Time-based logging bounds the silence
    # regardless of how slow a batch turns out to be.
    num_batches = len(train_loader)
    LOG_INTERVAL_SECONDS = 15

    for epoch in range(start_epoch, cfg.epochs):
        model.train()
        total_loss = 0.0
        num_examples = 0
        epoch_start = time.monotonic()
        last_log_time = epoch_start
        for batch_idx, batch in enumerate(train_loader, start=1):
            optimizer.zero_grad()
            batch_labels = batch.pop("labels").to(device)
            batch = {k: v.to(device) for k, v in batch.items()}
            logits = model(**batch).logits
            loss = F.cross_entropy(logits, batch_labels, weight=class_weights_tensor)
            loss.backward()
            optimizer.step()
            total_loss += loss.item()
            num_examples += batch_labels.size(0)
            now = time.monotonic()
            if now - last_log_time >= LOG_INTERVAL_SECONDS or batch_idx == num_batches:
                elapsed = now - epoch_start
                rate = num_examples / elapsed if elapsed > 0 else 0
                print(
                    f"    [{head.name}] epoch {epoch + 1}/{cfg.epochs} - batch {batch_idx}/{num_batches} "
                    f"- running_loss {total_loss / batch_idx:.4f} - {elapsed:.0f}s elapsed "
                    f"- {rate:.1f} examples/sec",
                    flush=True,
                )
                last_log_time = now
        epoch_seconds = time.monotonic() - epoch_start
        avg_loss = total_loss / max(1, len(train_loader))
        samples_per_sec = num_examples / epoch_seconds if epoch_seconds > 0 else None

        val_accuracy = _evaluate(model, val_ds, device)
        history.append({
            "epoch": epoch + 1,
            "train_loss": avg_loss,
            "val_accuracy": val_accuracy,
            "epoch_seconds": round(epoch_seconds, 2),
            "samples_per_sec": round(samples_per_sec, 1) if samples_per_sec else None,
        })
        print(
            f"  [{head.name}] epoch {epoch + 1}/{cfg.epochs} - loss {avg_loss:.4f}"
            + (f" - val_acc {val_accuracy:.4f}" if val_accuracy is not None else "")
            + f" - {epoch_seconds:.1f}s"
            + (f" ({samples_per_sec:.1f} samples/sec)" if samples_per_sec else ""),
            flush=True,
        )

        if val_accuracy is not None:
            improved = stopper.step(epoch + 1, val_accuracy)
            if improved:
                best_state = copy.deepcopy(model.state_dict())
                torch.save({"model_state_dict": best_state, "epoch": epoch + 1, "val_accuracy": val_accuracy}, best_checkpoint_path)
        elif epoch == cfg.epochs - 1:
            # No validation examples for this head - nothing to select a
            # "best" checkpoint against, so keep the final epoch's weights.
            best_state = copy.deepcopy(model.state_dict())

        torch.save({
            "next_epoch": epoch + 1,
            "model_state_dict": model.state_dict(),
            "optimizer_state_dict": optimizer.state_dict(),
            "history": history,
            "stopper_best": stopper.best,
            "stopper_best_epoch": stopper.best_epoch,
            "stopper_bad_epochs": stopper._bad_epochs,
            "rng_state_python": random.getstate(),
            "rng_state_numpy": np.random.get_state(),
            "rng_state_torch": torch.get_rng_state(),
        }, checkpoint_path)

        if stopper.should_stop:
            print(
                f"  [{head.name}] early stopping at epoch {epoch + 1} "
                f"(best val_acc={stopper.best:.4f} @ epoch {stopper.best_epoch})"
            )
            break

    if best_state is not None:
        model.load_state_dict(best_state)
    final_val_accuracy = _evaluate(model, val_ds, device)
    model.to("cpu")  # save_pretrained doesn't need the device, and CPU tensors serialize portably

    model.save_pretrained(head_dir)
    tokenizer.save_pretrained(head_dir)

    return {
        "head": head.name,
        "label_field": head.label_field,
        "labels": labels,
        "num_train_examples": len(train_ds),
        "num_val_examples": len(val_ds),
        "val_accuracy": final_val_accuracy,
        "best_epoch": stopper.best_epoch,
        "epochs_trained": len(history),
        "class_weighting": cfg.class_weighting,
        "history": history,
        "resumed": resume and start_epoch > 0,
    }


def main(config_path: Path = DEFAULT_CONFIG_PATH, resume: bool = False) -> dict:
    from training.training.device import describe_device, resolve_training_device

    cfg = TrainingConfig.load(config_path)
    set_seed(cfg.seed)

    device = resolve_training_device(cfg.training_device)
    device_info = describe_device(device)
    print(f"Training device: {device_info['device']}")
    print(f"CUDA available: {device_info['cuda_available']}  MPS available: {device_info['mps_available']}")
    if "gpu_name" in device_info:
        print(f"GPU: {device_info['gpu_name']} ({device_info['gpu_memory_gb']} GB)")

    train_path = cfg.dataset_dir / "train.jsonl"
    val_path = cfg.dataset_dir / "val.jsonl"
    if not train_path.exists() or not val_path.exists():
        raise FileNotFoundError(
            f"Processed train/val files not found under {cfg.dataset_dir}. "
            "Run `python -m training.preprocessing.build_training_set` first."
        )

    train_records = _load_jsonl(train_path)
    val_records = _load_jsonl(val_path)

    cfg.output_dir.mkdir(parents=True, exist_ok=True)

    head_results = []
    for head in cfg.heads:
        print(f"Training head: {head.name} (base_model={cfg.base_model}, batch_size={cfg.batch_size})")
        result = train_head(head, cfg, train_records, val_records, device, resume=resume)
        head_results.append(result)

    metadata = {
        "model_version": cfg.model_version,
        "base_model": cfg.base_model,
        "device": device_info,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "training_config": {
            "seed": cfg.seed,
            "max_length": cfg.max_length,
            "batch_size": cfg.batch_size,
            "learning_rate": cfg.learning_rate,
            "epochs": cfg.epochs,
            "early_stopping_patience": cfg.early_stopping_patience,
            "class_weighting": cfg.class_weighting,
        },
        "dataset_version": _read_dataset_version(cfg.dataset_dir),
        "heads": head_results,
    }
    (cfg.output_dir / "metadata.json").write_text(
        json.dumps(metadata, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    print(f"Saved WOW Brain {cfg.model_version} to {cfg.output_dir}")
    return metadata


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG_PATH)
    parser.add_argument(
        "--resume", action="store_true",
        help="Resume each head from its checkpoint.pt in output_dir if one exists, instead of starting over.",
    )
    args = parser.parse_args()
    main(args.config, resume=args.resume)
