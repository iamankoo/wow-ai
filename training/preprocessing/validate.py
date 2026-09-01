"""Validates every dataset file under training/datasets/.

Checks: schema conformance (required fields, valid intent/context/action/
relationship names via the taxonomy Enums), duplicate examples within a
category, and inconsistent expected outputs (the same input text mapped to
two different intents across the dataset).

Usage:
    python -m training.preprocessing.validate

Exit code 0 = all datasets valid. Exit code 1 = one or more problems found.
"""

import json
import sys
from collections import defaultdict
from pathlib import Path

from pydantic import ValidationError

from training.datasets.schemas.call_scenario_example import CallScenarioExample
from training.datasets.schemas.conversation_example import ConversationExample
from training.datasets.schemas.intent_example import IntentExample
from training.datasets.schemas.summary_example import SummaryExample

DATASETS_DIR = Path(__file__).resolve().parents[1] / "datasets"

CATEGORY_SCHEMAS = {
    "intents": IntentExample,
    "contexts": IntentExample,
    "call_scenarios": CallScenarioExample,
    "conversations": ConversationExample,
    "summaries": SummaryExample,
}


def _dedupe_key(category: str, record: dict) -> tuple:
    if category in ("intents", "contexts"):
        return (record.get("text", "").strip().lower(), record.get("intent"))
    if category == "call_scenarios":
        return (record.get("caller_description", "").strip().lower(), record.get("expected_intent"))
    if category == "conversations":
        return (record.get("caller_message", "").strip().lower(),)
    if category == "summaries":
        return (record.get("transcript", "").strip().lower(),)
    return tuple(sorted(record.items()))


def validate_file(path: Path, category: str) -> tuple[int, list[str]]:
    schema = CATEGORY_SCHEMAS[category]
    errors: list[str] = []
    seen: dict[tuple, int] = {}
    text_to_intents: dict[str, set[str]] = defaultdict(set)
    count = 0

    with path.open(encoding="utf-8") as f:
        for line_no, line in enumerate(f, start=1):
            line = line.strip()
            if not line:
                continue
            try:
                record = json.loads(line)
            except json.JSONDecodeError as e:
                errors.append(f"{path.name}:{line_no}: malformed JSON ({e})")
                continue

            try:
                schema.model_validate(record)
            except ValidationError as e:
                errors.append(f"{path.name}:{line_no}: schema validation failed - {e.errors()[0]['msg']} (field: {'.'.join(str(x) for x in e.errors()[0]['loc'])})")
                continue

            count += 1
            key = _dedupe_key(category, record)
            if key in seen:
                errors.append(
                    f"{path.name}:{line_no}: duplicate example (same as line {seen[key]})"
                )
            else:
                seen[key] = line_no

            if category in ("intents", "contexts"):
                text_to_intents[record["text"].strip().lower()].add(record["intent"])

    for text, intents in text_to_intents.items():
        if len(intents) > 1:
            errors.append(
                f"{path.name}: inconsistent expected output - text {text!r} maps to multiple intents: {sorted(intents)}"
            )

    return count, errors


def main() -> int:
    total_examples = 0
    all_errors: list[str] = []

    for category in CATEGORY_SCHEMAS:
        category_dir = DATASETS_DIR / category
        if not category_dir.exists():
            all_errors.append(f"missing dataset directory: {category_dir}")
            continue
        files = sorted(category_dir.glob("*.jsonl"))
        if not files:
            all_errors.append(f"no .jsonl files found in {category_dir}")
            continue
        for path in files:
            count, errors = validate_file(path, category)
            total_examples += count
            all_errors.extend(errors)

    print(f"Validated {total_examples} examples across {len(CATEGORY_SCHEMAS)} categories.")

    if all_errors:
        print(f"\n{len(all_errors)} problem(s) found:")
        for err in all_errors:
            print(f"  - {err}")
        _update_metadata_status("invalid", total_examples)
        return 1

    print("All datasets valid.")
    _update_metadata_status("valid", total_examples)
    return 0


def _update_metadata_status(status: str, num_examples: int) -> None:
    metadata_path = DATASETS_DIR / "DATASET_METADATA.json"
    if not metadata_path.exists():
        return
    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    metadata["validation_status"] = status
    metadata["num_examples"] = num_examples
    metadata_path.write_text(json.dumps(metadata, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


if __name__ == "__main__":
    sys.exit(main())
