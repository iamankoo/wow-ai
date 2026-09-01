"""Merges the classification-relevant dataset categories (intents, contexts,
conversations, call_scenarios) into one unified record shape suitable for
training the intent/context/action classifiers, and splits it into
train/validation sets.

Unified record shape:
    {"text": str, "language": str, "intent": str, "context_mode": str|None,
     "action": str|None}

Usage:
    python -m training.preprocessing.build_training_set
Writes training/datasets/processed/{train,val}.jsonl and
training/datasets/processed/SPLIT_METADATA.json.
"""

import json
import random
from collections import defaultdict
from pathlib import Path

DATASETS_DIR = Path(__file__).resolve().parents[1] / "datasets"
PROCESSED_DIR = DATASETS_DIR / "processed"

SEED = 42
VAL_FRACTION = 0.15
MIN_VAL_PER_CLASS = 2
MIN_CLASS_SIZE_FOR_SPLIT = 5


def _load_jsonl(path: Path) -> list[dict]:
    with path.open(encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


def _unify_intent_record(r: dict) -> dict:
    return {
        "text": r["text"],
        "language": r["language"],
        "intent": r["intent"],
        "context_mode": r.get("context_mode"),
        "action": r.get("action"),
    }


def _unify_scenario_record(r: dict) -> dict:
    return {
        "text": r["caller_description"],
        "language": r["language"],
        "intent": r["expected_intent"],
        "context_mode": None,
        "action": r["expected_action"],
    }


def _unify_conversation_record(r: dict) -> dict:
    return {
        "text": r["caller_message"],
        "language": r["language"],
        "intent": r["expected_intent"],
        "context_mode": r["context_mode"],
        "action": r["expected_action"],
    }


def build_unified_records() -> list[dict]:
    records: list[dict] = []
    for r in _load_jsonl(DATASETS_DIR / "intents" / "seed.jsonl"):
        records.append(_unify_intent_record(r))
    for r in _load_jsonl(DATASETS_DIR / "contexts" / "seed.jsonl"):
        records.append(_unify_intent_record(r))
    for r in _load_jsonl(DATASETS_DIR / "call_scenarios" / "seed.jsonl"):
        records.append(_unify_scenario_record(r))
    for r in _load_jsonl(DATASETS_DIR / "conversations" / "seed.jsonl"):
        records.append(_unify_conversation_record(r))

    # Records without an action are not usable for the action-classifier
    # head, but are still fine for intent/context training - keep action=None.
    return records


def stratified_split(
    records: list[dict],
    val_fraction: float = VAL_FRACTION,
    seed: int = SEED,
    stratify_field: str = "intent",
    min_val_per_class: int = MIN_VAL_PER_CLASS,
    min_class_size_for_split: int = MIN_CLASS_SIZE_FOR_SPLIT,
) -> tuple[list[dict], list[dict]]:
    """Splits records into train/val, stratified per class of `stratify_field`.

    Every class with at least `min_class_size_for_split` examples contributes
    at least `min_val_per_class` examples to validation (never exactly one -
    a singleton validation example makes per-class accuracy meaningless).
    Classes smaller than that go entirely to train, since they can't be split
    meaningfully. This keeps every class represented in both splits wherever
    the data actually allows it, instead of the flat-random split (which can
    starve rare classes of validation coverage entirely by chance).
    """
    rng = random.Random(seed)
    by_class: dict[str, list[dict]] = defaultdict(list)
    for r in records:
        by_class[r[stratify_field]].append(r)

    train: list[dict] = []
    val: list[dict] = []
    for key in sorted(by_class):
        items = by_class[key][:]
        rng.shuffle(items)
        count = len(items)
        if count < min_class_size_for_split:
            train.extend(items)
            continue
        n_val = round(count * val_fraction)
        if n_val < min_val_per_class:
            n_val = min_val_per_class
        n_val = min(n_val, count - 1)
        val.extend(items[:n_val])
        train.extend(items[n_val:])

    rng.shuffle(train)
    rng.shuffle(val)
    return train, val


def main() -> None:
    records = build_unified_records()
    train, val = stratified_split(records)

    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
    for name, subset in (("train", train), ("val", val)):
        with (PROCESSED_DIR / f"{name}.jsonl").open("w", encoding="utf-8") as f:
            for r in subset:
                f.write(json.dumps(r, ensure_ascii=False) + "\n")

    metadata = {
        "seed": SEED,
        "val_fraction": VAL_FRACTION,
        "split_strategy": "stratified_by_intent",
        "min_val_per_class": MIN_VAL_PER_CLASS,
        "min_class_size_for_split": MIN_CLASS_SIZE_FOR_SPLIT,
        "total_records": len(records),
        "train_records": len(train),
        "val_records": len(val),
    }
    (PROCESSED_DIR / "SPLIT_METADATA.json").write_text(
        json.dumps(metadata, indent=2) + "\n", encoding="utf-8"
    )
    print(f"Unified {len(records)} records -> train={len(train)} val={len(val)} (seed={SEED})")


if __name__ == "__main__":
    main()
