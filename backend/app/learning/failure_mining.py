"""Failure mining: cluster corrections by (predicted -> corrected) pair per
field, so a handful of recurring confusions surface instead of a flat list
of individual complaints. This is meant to directly inform
training/generation/build_seed_dataset.py's hard-negative authoring - see
docs/SELF_LEARNING.md "Failure mining" - not to auto-generate examples.
"""

from collections import Counter
from dataclasses import dataclass, field

from app.interfaces.feedback import FeedbackRecord


@dataclass
class Confusion:
    predicted: str
    corrected: str
    count: int


@dataclass
class FailureReport:
    total_events_analyzed: int
    intent_confusions: list[Confusion] = field(default_factory=list)
    context_confusions: list[Confusion] = field(default_factory=list)
    action_confusions: list[Confusion] = field(default_factory=list)


class FailureMiner:
    def mine(self, records: list[FeedbackRecord]) -> FailureReport:
        intent_counts: Counter[tuple[str, str]] = Counter()
        context_counts: Counter[tuple[str, str]] = Counter()
        action_counts: Counter[tuple[str, str]] = Counter()
        analyzed = 0

        for r in records:
            has_correction = False
            if r.predicted_intent and r.corrected_intent and r.predicted_intent != r.corrected_intent:
                intent_counts[(r.predicted_intent, r.corrected_intent)] += 1
                has_correction = True
            if (
                r.predicted_context_mode and r.corrected_context_mode
                and r.predicted_context_mode != r.corrected_context_mode
            ):
                context_counts[(r.predicted_context_mode, r.corrected_context_mode)] += 1
                has_correction = True
            if r.predicted_action and r.corrected_action and r.predicted_action != r.corrected_action:
                action_counts[(r.predicted_action, r.corrected_action)] += 1
                has_correction = True
            if has_correction:
                analyzed += 1

        def to_confusions(counts: Counter[tuple[str, str]]) -> list[Confusion]:
            return [
                Confusion(predicted=pred, corrected=corr, count=n)
                for (pred, corr), n in sorted(counts.items(), key=lambda kv: -kv[1])
            ]

        return FailureReport(
            total_events_analyzed=analyzed,
            intent_confusions=to_confusions(intent_counts),
            context_confusions=to_confusions(context_counts),
            action_confusions=to_confusions(action_counts),
        )
