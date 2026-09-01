"""Dataset statistics tooling.

Reports per-intent, per-action, per-context, and per-language distribution
over the unified classification dataset, plus the train/validation split
breakdown once training/preprocessing/build_training_set.py has run.

This is the tool used to check dataset balance before training (see
docs/TRAINING.md "Dataset balance") - it does not modify any dataset file.

Usage:
    python -m training.preprocessing.stats
    python -m training.preprocessing.stats --output training/datasets/processed/STATS.json
"""

import argparse
import json
from collections import Counter
from pathlib import Path

from training.preprocessing.build_training_set import build_unified_records

DATASETS_DIR = Path(__file__).resolve().parents[1] / "datasets"
PROCESSED_DIR = DATASETS_DIR / "processed"


def _load_jsonl(path: Path) -> list[dict]:
    if not path.exists():
        return []
    with path.open(encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


def _distribution(records: list[dict], field: str) -> dict[str, int]:
    counts = Counter(r.get(field) for r in records if r.get(field) is not None)
    return dict(sorted(counts.items(), key=lambda kv: (-kv[1], kv[0])))


def compute_stats() -> dict:
    records = build_unified_records()
    train_records = _load_jsonl(PROCESSED_DIR / "train.jsonl")
    val_records = _load_jsonl(PROCESSED_DIR / "val.jsonl")

    intent_dist = _distribution(records, "intent")
    action_dist = _distribution(records, "action")
    context_dist = _distribution(records, "context_mode")
    language_dist = _distribution(records, "language")

    min_intent_count = min(intent_dist.values()) if intent_dist else 0
    min_action_count = min(action_dist.values()) if action_dist else 0

    return {
        "total_records": len(records),
        "train_records": len(train_records),
        "val_records": len(val_records),
        "intent_distribution": intent_dist,
        "action_distribution": action_dist,
        "context_distribution": context_dist,
        "language_distribution": language_dist,
        "num_intent_classes": len(intent_dist),
        "num_action_classes": len(action_dist),
        "num_context_classes": len(context_dist),
        "min_examples_per_intent": min_intent_count,
        "min_examples_per_action": min_action_count,
        "intents_below_30": [k for k, v in intent_dist.items() if v < 30],
        "actions_below_30": [k for k, v in action_dist.items() if v < 30],
        "train_intent_distribution": _distribution(train_records, "intent"),
        "val_intent_distribution": _distribution(val_records, "intent"),
    }


def _print_human_summary(stats: dict) -> None:
    print(f"Total unified records: {stats['total_records']}")
    print(f"  train={stats['train_records']}  val={stats['val_records']}")
    print()
    print(f"Intent classes: {stats['num_intent_classes']} "
          f"(min count = {stats['min_examples_per_intent']})")
    for k, v in stats["intent_distribution"].items():
        print(f"  {k:<24} {v}")
    if stats["intents_below_30"]:
        print(f"  WARNING: below 30 examples: {stats['intents_below_30']}")
    print()
    print(f"Action classes: {stats['num_action_classes']} "
          f"(min count = {stats['min_examples_per_action']})")
    for k, v in stats["action_distribution"].items():
        print(f"  {k:<24} {v}")
    if stats["actions_below_30"]:
        print(f"  WARNING: below 30 examples: {stats['actions_below_30']}")
    print()
    print(f"Context classes: {stats['num_context_classes']}")
    for k, v in stats["context_distribution"].items():
        print(f"  {k:<24} {v}")
    print()
    print("Language distribution:")
    for k, v in stats["language_distribution"].items():
        print(f"  {k:<10} {v}")
    print()
    print("Train/val intent distribution (stratification check):")
    all_intents = sorted(set(stats["train_intent_distribution"]) | set(stats["val_intent_distribution"]))
    for intent in all_intents:
        t = stats["train_intent_distribution"].get(intent, 0)
        v = stats["val_intent_distribution"].get(intent, 0)
        flag = "  <- no val examples!" if v == 0 and t > 0 else ""
        print(f"  {intent:<24} train={t:<4} val={v:<4}{flag}")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--output", type=Path, default=PROCESSED_DIR / "STATS.json",
    )
    args = parser.parse_args()

    stats = compute_stats()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(stats, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    _print_human_summary(stats)
    print(f"\nFull stats written to {args.output}")


if __name__ == "__main__":
    main()
