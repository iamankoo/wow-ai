"""Evaluates RuleBasedLanguageModelProvider vs one or more LocalWOWModelProvider
model versions on the held-out validation set produced by
training/preprocessing/build_training_set.py.

This does not hide poor results: every metric is computed straight from
predictions, and every mismatch is recorded as a failure example. If a local
model performs worse than the rule-based baseline (or an earlier model
version), the report says so.

Usage:
    python -m training.evaluation.evaluate
    python -m training.evaluation.evaluate --model-dir v0=training/models/wow-brain/v0
    python -m training.evaluation.evaluate \\
        --model-dir v0=training/models/wow-brain/v0 \\
        --model-dir v1=training/models/wow-brain/v1
"""

import argparse
import asyncio
import json
from datetime import datetime, timezone
from pathlib import Path

from training.training.config import DEFAULT_CONFIG_PATH, REPO_ROOT, TrainingConfig
from training.wow_taxonomy import Action, ContextMode, Intent

BACKEND_DIR = REPO_ROOT / "backend"
import sys  # noqa: E402

if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.interfaces.llm import LLMMessage  # noqa: E402
from app.providers.llm.rule_based import RuleBasedLanguageModelProvider  # noqa: E402


def _load_jsonl(path: Path) -> list[dict]:
    with path.open(encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


def _is_ambiguous(record: dict) -> bool:
    return record.get("intent") == Intent.UNKNOWN.value


async def _predict_rule_based(provider: RuleBasedLanguageModelProvider, text: str) -> dict:
    intent, context_mode, action = provider.classify_wow_taxonomy(text)
    return {
        "intent": intent.value,
        "context_mode": context_mode.value if context_mode else None,
        "action": action.value if action else None,
        "confidence": None,
    }


async def _predict_local_wow(provider, text: str) -> dict:
    response = await provider.generate([LLMMessage(role="user", content=text)])
    confidence = response.metadata.get("confidence", {})
    return {
        "intent": response.intent,
        "context_mode": response.slots.get("context_mode"),
        "action": response.slots.get("action"),
        "confidence": confidence,
    }


def _valid_structured_output(pred: dict) -> bool:
    """Whether a prediction's fields are all members of the taxonomy (or None
    where that's legitimate) - i.e. the model didn't emit garbage."""
    if pred["intent"] is not None and pred["intent"] not in Intent._value2member_map_:
        return False
    if pred["context_mode"] is not None and pred["context_mode"] not in ContextMode._value2member_map_:
        return False
    if pred["action"] is not None and pred["action"] not in Action._value2member_map_:
        return False
    return True


def _score(records: list[dict], predictions: list[dict]) -> dict:
    n = len(records)
    intent_correct = 0
    context_correct = 0
    context_total = 0
    action_correct = 0
    action_total = 0
    valid_structured = 0
    ambiguous_correct = 0
    ambiguous_total = 0
    per_language: dict[str, dict[str, int]] = {}
    per_intent: dict[str, dict[str, int]] = {}
    confusion: dict[str, dict[str, int]] = {}
    predicted_intent_counts: dict[str, int] = {}
    failures: list[dict] = []

    for record, pred in zip(records, predictions):
        lang = record["language"]
        per_language.setdefault(lang, {"total": 0, "intent_correct": 0})
        per_language[lang]["total"] += 1

        expected_intent = record["intent"]
        predicted_intent = pred["intent"] or "NONE"
        per_intent.setdefault(expected_intent, {"total": 0, "correct": 0})
        per_intent[expected_intent]["total"] += 1
        predicted_intent_counts[predicted_intent] = predicted_intent_counts.get(predicted_intent, 0) + 1
        confusion.setdefault(expected_intent, {})
        confusion[expected_intent][predicted_intent] = confusion[expected_intent].get(predicted_intent, 0) + 1

        is_intent_correct = predicted_intent == expected_intent
        if is_intent_correct:
            intent_correct += 1
            per_language[lang]["intent_correct"] += 1
            per_intent[expected_intent]["correct"] += 1

        if record.get("context_mode") is not None:
            context_total += 1
            if pred["context_mode"] == record["context_mode"]:
                context_correct += 1

        if record.get("action") is not None:
            action_total += 1
            if pred["action"] == record["action"]:
                action_correct += 1

        if _valid_structured_output(pred):
            valid_structured += 1

        if _is_ambiguous(record):
            ambiguous_total += 1
            if is_intent_correct:
                ambiguous_correct += 1

        if not is_intent_correct:
            failures.append({
                "text": record["text"],
                "language": lang,
                "expected_intent": record["intent"],
                "predicted_intent": pred["intent"],
                "expected_context": record.get("context_mode"),
                "predicted_context": pred["context_mode"],
                "expected_action": record.get("action"),
                "predicted_action": pred["action"],
            })

    most_predicted_intent, most_predicted_count = (
        max(predicted_intent_counts.items(), key=lambda kv: kv[1])
        if predicted_intent_counts else (None, 0)
    )

    return {
        "total_examples": n,
        "intent_accuracy": intent_correct / n if n else None,
        "context_accuracy": context_correct / context_total if context_total else None,
        "context_total_evaluated": context_total,
        "action_accuracy": action_correct / action_total if action_total else None,
        "action_total_evaluated": action_total,
        "structured_output_validity": valid_structured / n if n else None,
        "ambiguous_unknown_accuracy": ambiguous_correct / ambiguous_total if ambiguous_total else None,
        "ambiguous_total_evaluated": ambiguous_total,
        "per_language_intent_accuracy": {
            lang: stats["intent_correct"] / stats["total"]
            for lang, stats in per_language.items()
        },
        "per_intent_accuracy": {
            intent: stats["correct"] / stats["total"]
            for intent, stats in sorted(per_intent.items())
        },
        "most_predicted_intent": most_predicted_intent,
        "most_predicted_intent_share": most_predicted_count / n if n else None,
        "mode_collapse_suspected": bool(n) and (most_predicted_count / n) > 0.5,
        "intent_confusion_matrix": confusion,
        "failure_count": len(failures),
        "failures": failures,
    }


async def _score_local_provider(model_dir: Path, val_records: list[dict]) -> tuple[dict | None, str | None, dict]:
    try:
        from app.providers.llm.local_wow import LocalWOWModelProvider

        provider = LocalWOWModelProvider(model_dir)
        predictions = [await _predict_local_wow(provider, r["text"]) for r in val_records]
        report = _score(val_records, predictions)
        error = None
    except Exception as e:  # noqa: BLE001 - deliberately broad: report, don't crash
        report = None
        error = f"{type(e).__name__}: {e}"

    metadata = {}
    metadata_path = model_dir / "metadata.json"
    if metadata_path.exists():
        metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    return report, error, metadata


async def run_evaluation(model_dirs: list[tuple[str, Path]]) -> dict:
    """model_dirs: ordered list of (provider_name, model_dir) pairs, e.g.
    [("v0", .../v0), ("v1", .../v1)]. Every provider is scored on the same
    held-out validation set alongside the rule_based baseline."""
    cfg = TrainingConfig.load(DEFAULT_CONFIG_PATH)
    val_records = _load_jsonl(cfg.dataset_dir / "val.jsonl")
    train_records = _load_jsonl(cfg.dataset_dir / "train.jsonl")

    rule_provider = RuleBasedLanguageModelProvider()
    rule_predictions = [await _predict_rule_based(rule_provider, r["text"]) for r in val_records]
    rule_report = _score(val_records, rule_predictions)

    providers: dict[str, dict] = {"rule_based": rule_report}
    model_versions: dict[str, str | None] = {}
    for name, model_dir in model_dirs:
        report, error, metadata = await _score_local_provider(model_dir, val_records)
        providers[name] = report if report is not None else {"error": error}
        model_versions[name] = metadata.get("model_version")

    report = {
        "evaluated_at": datetime.now(timezone.utc).isoformat(),
        "dataset_version": _dataset_version(),
        "model_versions": model_versions,
        "total_examples": len(train_records) + len(val_records),
        "train_examples": len(train_records),
        "validation_examples": len(val_records),
        "providers": providers,
    }
    return report


def _dataset_version() -> str:
    meta_path = REPO_ROOT / "training" / "datasets" / "DATASET_METADATA.json"
    if meta_path.exists():
        return json.loads(meta_path.read_text(encoding="utf-8")).get("dataset_version", "unknown")
    return "unknown"


def _print_human_summary(report: dict) -> None:
    print(f"Dataset version: {report['dataset_version']}")
    print(f"Model versions:  {report['model_versions']}")
    print(f"Total examples:  {report['total_examples']} (train={report['train_examples']}, val={report['validation_examples']})")
    print()
    for name, r in report["providers"].items():
        print(f"== {name} ==")
        if "error" in r:
            print(f"  UNAVAILABLE: {r['error']}")
            continue
        print(f"  intent accuracy:              {r['intent_accuracy']:.2%}")
        if r["context_accuracy"] is not None:
            print(f"  context accuracy (n={r['context_total_evaluated']}):    {r['context_accuracy']:.2%}")
        if r["action_accuracy"] is not None:
            print(f"  action accuracy (n={r['action_total_evaluated']}):     {r['action_accuracy']:.2%}")
        print(f"  structured output validity:   {r['structured_output_validity']:.2%}")
        if r["ambiguous_total_evaluated"]:
            print(f"  ambiguous/unknown accuracy (n={r['ambiguous_total_evaluated']}): {r['ambiguous_unknown_accuracy']:.2%}")
        print(f"  per-language intent accuracy: {r['per_language_intent_accuracy']}")
        if r["mode_collapse_suspected"]:
            print(
                f"  MODE COLLAPSE SUSPECTED: {r['most_predicted_intent_share']:.1%} of all "
                f"predictions were '{r['most_predicted_intent']}'"
            )
        else:
            print(
                f"  most-predicted intent: '{r['most_predicted_intent']}' "
                f"({r['most_predicted_intent_share']:.1%} of predictions - no collapse)"
            )
        print(f"  failures: {r['failure_count']} / {r['total_examples']}")
        for f in r["failures"][:5]:
            print(f"    - [{f['language']}] {f['text']!r} -> expected {f['expected_intent']}, got {f['predicted_intent']}")
        print()

    rb = report["providers"]["rule_based"]
    for name, r in report["providers"].items():
        if name == "rule_based" or "error" in r:
            continue
        if r["intent_accuracy"] < rb["intent_accuracy"]:
            print(
                f"RESULT: {name} ({r['intent_accuracy']:.1%}) underperforms the "
                f"rule_based baseline ({rb['intent_accuracy']:.1%}) on intent accuracy."
            )
        else:
            print(
                f"RESULT: {name} ({r['intent_accuracy']:.1%}) matches or exceeds the "
                f"rule_based baseline ({rb['intent_accuracy']:.1%}) on intent accuracy."
            )

    model_names = [n for n in report["providers"] if n != "rule_based" and "error" not in report["providers"][n]]
    for prev, curr in zip(model_names, model_names[1:]):
        p, c = report["providers"][prev], report["providers"][curr]
        delta = c["intent_accuracy"] - p["intent_accuracy"]
        print(
            f"RESULT: {curr} vs {prev} intent accuracy delta: {delta:+.1%} "
            f"({p['intent_accuracy']:.1%} -> {c['intent_accuracy']:.1%})"
        )


def _parse_model_dir_arg(raw: str) -> tuple[str, Path]:
    if "=" in raw:
        name, path = raw.split("=", 1)
        return name, Path(path)
    return Path(raw).name, Path(raw)


def main() -> None:
    # The dataset intentionally includes Devanagari text (see docs/TRAINING.md),
    # which the default Windows console encoding (cp1252) can't print. Widen
    # stdout to UTF-8 so failure examples print instead of crashing the run
    # after the (already-written) JSON report - this only affects console
    # display, never the report file itself.
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="backslashreplace")

    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--model-dir", action="append", dest="model_dirs", default=None,
        help="NAME=PATH (repeatable), e.g. --model-dir v0=training/models/wow-brain/v0 "
             "--model-dir v1=training/models/wow-brain/v1. If omitted, defaults to v0.",
    )
    parser.add_argument(
        "--output", type=Path,
        default=REPO_ROOT / "training" / "evaluation" / "latest_report.json",
    )
    args = parser.parse_args()

    raw_dirs = args.model_dirs or ["v0=training/models/wow-brain/v0"]
    model_dirs = [_parse_model_dir_arg(raw) for raw in raw_dirs]

    report = asyncio.run(run_evaluation(model_dirs))

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    _print_human_summary(report)
    print(f"\nFull report written to {args.output}")


if __name__ == "__main__":
    main()
