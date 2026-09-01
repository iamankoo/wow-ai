"""Batched v1-model candidate labeling over the full WOW 33K dataset.

This is a CANDIDATE-generation script only. It runs the already-trained v1
model (inference only - no gradient updates, no weight changes, no training)
over every example in wow_33k_relevant.jsonl and writes a softmax-confidence
candidate label per head to wow_33k_candidate_labels_v1.jsonl.

These candidates are advisory input to the human annotation workflow. They
are NEVER treated as ground truth by anything downstream.

Usage:
    python -m training.pipeline.annotation.v1_batch_label
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import torch
import torch.nn.functional as F
from transformers import AutoModelForSequenceClassification, AutoTokenizer

REPO_ROOT = Path(__file__).resolve().parents[3]
INPUT_PATH = REPO_ROOT / "training" / "datasets" / "v3_raw" / "wow_33k_relevant.jsonl"
OUTPUT_PATH = REPO_ROOT / "training" / "datasets" / "v3_raw" / "wow_33k_candidate_labels_v1.jsonl"
V1_MODEL_DIR = REPO_ROOT / "training" / "models" / "wow-brain" / "v1"
HEADS = ("intent", "context", "action")
BATCH_SIZE = 64
MAX_LENGTH = 64


class _Head:
    def __init__(self, name: str):
        head_dir = V1_MODEL_DIR / name
        self.tokenizer = AutoTokenizer.from_pretrained(head_dir)
        self.model = AutoModelForSequenceClassification.from_pretrained(head_dir)
        self.model.eval()
        cfg = self.model.config
        self.id2label = {int(k): v for k, v in cfg.id2label.items()}

    @torch.no_grad()
    def predict_batch(self, texts: list[str]) -> list[tuple[str, float]]:
        enc = self.tokenizer(texts, truncation=True, padding=True, max_length=MAX_LENGTH, return_tensors="pt")
        logits = self.model(**enc).logits
        probs = F.softmax(logits, dim=-1)
        conf, idx = probs.max(dim=-1)
        return [(self.id2label[i.item()], c.item()) for i, c in zip(idx, conf)]


def _read_records(path: Path):
    with path.open("r", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if line:
                yield json.loads(line)


def main() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="backslashreplace")

    t_start = time.monotonic()
    print("Loading v1 heads (intent, context, action) for inference-only candidate labeling...")
    heads = {name: _Head(name) for name in HEADS}
    print("Heads loaded. Reading input dataset...")

    records = list(_read_records(INPUT_PATH))
    total = len(records)
    print(f"Loaded {total} records from {INPUT_PATH}")

    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    written = 0
    with OUTPUT_PATH.open("w", encoding="utf-8") as out:
        for batch_start in range(0, total, BATCH_SIZE):
            batch = records[batch_start:batch_start + BATCH_SIZE]
            texts = [r["text"] for r in batch]
            per_head_results = {name: head.predict_batch(texts) for name, head in heads.items()}
            for i, rec in enumerate(batch):
                intent, intent_conf = per_head_results["intent"][i]
                context, context_conf = per_head_results["context"][i]
                action, action_conf = per_head_results["action"][i]
                out_rec = {
                    "id": rec["id"],
                    "candidate_intent_v1": intent,
                    "candidate_intent_v1_confidence": round(intent_conf, 4),
                    "candidate_context_v1": context,
                    "candidate_context_v1_confidence": round(context_conf, 4),
                    "candidate_action_v1": action,
                    "candidate_action_v1_confidence": round(action_conf, 4),
                }
                out.write(json.dumps(out_rec, ensure_ascii=False) + "\n")
                written += 1
            if batch_start % (BATCH_SIZE * 50) == 0:
                elapsed = time.monotonic() - t_start
                rate = written / elapsed if elapsed > 0 else 0
                eta = (total - written) / rate if rate > 0 else float("nan")
                print(f"progress={written}/{total} elapsed={elapsed:.1f}s rate={rate:.1f}/s eta={eta:.0f}s")

    elapsed = time.monotonic() - t_start
    print(f"Wrote {written} candidate labels to {OUTPUT_PATH}")
    print(f"elapsed={elapsed:.1f}s")
    print("DONE")


if __name__ == "__main__":
    main()
