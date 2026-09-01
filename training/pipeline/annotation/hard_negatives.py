"""Automatic hard-negative capture: every time a human corrects a candidate
label to something different, that (predicted, correct) pair is exactly the
kind of confusable example future training rounds most need. This module
appends such corrections to a JSONL file for later curation - it never
trains anything and never treats the correction as a finished hard-negative
training example (a human still needs to review the capture file before it
feeds a training run).
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

HARD_NEGATIVES_DIR = Path(__file__).resolve().parents[2] / "datasets" / "hard_negatives"
HARD_NEGATIVES_PATH = HARD_NEGATIVES_DIR / "wow_33k_annotation_hard_negatives.jsonl"


def append_hard_negative(record: dict, path: Path = HARD_NEGATIVES_PATH) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(record, ensure_ascii=False) + "\n")


def load_hard_negatives(path: Path = HARD_NEGATIVES_PATH) -> list[dict]:
    if not path.exists():
        return []
    with path.open(encoding="utf-8") as fh:
        return [json.loads(line) for line in fh if line.strip()]


def summarize(path: Path = HARD_NEGATIVES_PATH) -> dict:
    records = load_hard_negatives(path)
    by_pair: dict[str, int] = {}
    for r in records:
        pair = f"{r.get('predicted_intent')}_confused_as_{r.get('correct_intent')}"
        by_pair[pair] = by_pair.get(pair, 0) + 1
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "total_captured": len(records),
        "by_confusion_pair": dict(sorted(by_pair.items(), key=lambda kv: -kv[1])),
    }
