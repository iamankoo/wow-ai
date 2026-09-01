"""Converts APPROVED feedback into training-candidate examples, shaped
exactly like training/datasets/schemas/intent_example.py:IntentExample so
they can be validated and merged with the hand-authored seed dataset using
the same tooling (training/preprocessing/validate.py).

Only ever reads APPROVED records - never CANDIDATE, never RECEIVED. That is
the literal "never automatically become training data" gate: nothing
reaches a file on disk until app/learning/feedback_processor.py:approve()
has been called by a named human reviewer.

Output goes to training/datasets/feedback_candidates/<batch_name>.jsonl -
deliberately a separate location from training/datasets/{intents,...}/
seed.jsonl, so provenance (hand-authored vs. feedback-derived) is always
inspectable and the two are never silently merged without an explicit
dataset-version step (see docs/SELF_LEARNING.md "Dataset versioning").
"""

import json
from dataclasses import dataclass, replace
from pathlib import Path

from app.brain.taxonomy import is_valid_action, is_valid_context, is_valid_intent
from app.interfaces.feedback import FeedbackCategory, FeedbackRecord, FeedbackRepository, FeedbackStatus


@dataclass
class CandidateBuildResult:
    batch_name: str
    output_path: Path
    included_count: int
    skipped_count: int
    skipped_reasons: dict[str, int]


def _resolve_labels(record: FeedbackRecord) -> tuple[str | None, str | None, str | None] | None:
    """Returns (intent, context_mode, action) ground-truth labels for this
    record, or None if it doesn't carry enough information to produce one.
    A confirmed-correct prediction uses the prediction as ground truth; a
    correction uses the corrected field(s), falling back to the prediction
    for any field that wasn't corrected."""
    if record.category == FeedbackCategory.CORRECT:
        return record.predicted_intent, record.predicted_context_mode, record.predicted_action

    has_any_correction = any((record.corrected_intent, record.corrected_context_mode, record.corrected_action))
    if not has_any_correction:
        return None

    intent = record.corrected_intent or record.predicted_intent
    context_mode = record.corrected_context_mode or record.predicted_context_mode
    action = record.corrected_action or record.predicted_action
    return intent, context_mode, action


class TrainingCandidateBuilder:
    def __init__(self, repository: FeedbackRepository, output_dir: Path):
        self._repo = repository
        self._output_dir = Path(output_dir)

    async def build(self, batch_name: str) -> CandidateBuildResult:
        approved = await self._repo.list_by_status(FeedbackStatus.APPROVED)

        examples: list[dict] = []
        skipped_reasons: dict[str, int] = {}
        included_records: list[FeedbackRecord] = []

        for record in approved:
            labels = _resolve_labels(record)
            if labels is None:
                skipped_reasons["no_ground_truth_label"] = skipped_reasons.get("no_ground_truth_label", 0) + 1
                continue
            intent, context_mode, action = labels

            if intent is None or not is_valid_intent(intent):
                skipped_reasons["invalid_intent"] = skipped_reasons.get("invalid_intent", 0) + 1
                continue
            if context_mode is not None and not is_valid_context(context_mode):
                skipped_reasons["invalid_context"] = skipped_reasons.get("invalid_context", 0) + 1
                continue
            if action is not None and not is_valid_action(action):
                skipped_reasons["invalid_action"] = skipped_reasons.get("invalid_action", 0) + 1
                continue
            if not record.redacted_text:
                skipped_reasons["not_redacted"] = skipped_reasons.get("not_redacted", 0) + 1
                continue

            examples.append({
                "text": record.redacted_text,
                "language": record.language or "en",
                "intent": intent,
                "context_mode": context_mode,
                "action": action,
                "notes": (
                    f"feedback_derived; source={record.source.value if record.source else 'unknown'}; "
                    f"category={record.category.value if record.category else 'unknown'}; "
                    f"confidence_weight={record.confidence_weight}"
                ),
            })
            included_records.append(record)

        self._output_dir.mkdir(parents=True, exist_ok=True)
        output_path = self._output_dir / f"{batch_name}.jsonl"
        with output_path.open("w", encoding="utf-8") as f:
            for example in examples:
                f.write(json.dumps(example, ensure_ascii=False) + "\n")

        for record in included_records:
            updated = replace(record, status=FeedbackStatus.INCLUDED, candidate_dataset_batch=batch_name)
            await self._repo.update(updated)

        return CandidateBuildResult(
            batch_name=batch_name,
            output_path=output_path,
            included_count=len(examples),
            skipped_count=sum(skipped_reasons.values()),
            skipped_reasons=skipped_reasons,
        )
