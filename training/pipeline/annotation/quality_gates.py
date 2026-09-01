"""TRAIN_READY quality gates for the annotated dataset.

These gates check STRUCTURAL correctness and completeness of the
reviewed portion of the dataset - they never require artificial class
balance. An intent with 40 examples and one with 400 can both pass;
imbalance is reported (see balance_report below), not penalized.

"Usable" records are resolved via schema.resolve_active_label(), which
looks at label_source rather than assuming human_* columns are populated -
an automated bulk approval (label_source="candidate",
review_status="approved", approved_by="automated_high_confidence") is
usable too, but its provenance is tracked and reported separately so a
report reader can always see how much of the usable set was actually
human-reviewed vs. machine-approved.

Nothing here trains a model. This module only decides whether an export is
fit to be used as training input later, when the user chooses to train.
"""

from __future__ import annotations

import sqlite3
from collections import Counter
from dataclasses import dataclass, field

from training.pipeline.annotation.schema import (
    is_valid_action,
    is_valid_context,
    is_valid_intent,
    resolve_active_label,
)

USABLE_STATUSES = ("approved", "corrected")


@dataclass
class QualityGateResult:
    train_ready: bool
    usable_count: int
    usable_human_count: int
    usable_automated_count: int
    total_count: int
    pending_count: int
    rejected_count: int
    blocking_issues: list[str]
    warnings: list[str]


def evaluate_quality_gates(conn: sqlite3.Connection, min_usable: int = 500) -> QualityGateResult:
    rows = conn.execute("SELECT * FROM annotations").fetchall()
    total = len(rows)
    usable = [r for r in rows if r["review_status"] in USABLE_STATUSES]
    pending = [r for r in rows if r["review_status"] == "pending"]
    rejected = [r for r in rows if r["review_status"] == "rejected"]
    usable_automated = [r for r in usable if r["approved_by"]]
    usable_human = [r for r in usable if not r["approved_by"]]

    blocking: list[str] = []
    warnings: list[str] = []

    seen_ids: set = set()
    seen_text_lang: dict = {}
    for r in usable:
        if r["id"] in seen_ids:
            blocking.append(f"duplicate id in usable set: {r['id']}")
        seen_ids.add(r["id"])

        intent, context, action = resolve_active_label(r)
        if not is_valid_intent(intent):
            blocking.append(f"record {r['id']}: missing/invalid intent {intent!r}")
        if not is_valid_action(action):
            blocking.append(f"record {r['id']}: missing/invalid action {action!r}")
        if not is_valid_context(context):
            blocking.append(f"record {r['id']}: invalid context {context!r}")

        key = (r["text"].strip().lower(), r["language"])
        if key in seen_text_lang and seen_text_lang[key] != (intent, context, action):
            blocking.append(
                f"contradictory labels for near-identical text: {r['id']} vs {seen_text_lang[key]}"
            )
        seen_text_lang[key] = (intent, context, action)

    if len(usable) < min_usable:
        warnings.append(f"only {len(usable)} usable examples, below the suggested minimum of {min_usable}")

    if pending:
        warnings.append(f"{len(pending)} examples still pending review (not blocking - export can be partial)")

    if usable and len(usable_automated) / len(usable) > 0.5:
        warnings.append(
            f"{len(usable_automated)}/{len(usable)} usable examples were automatically approved "
            "(not human-reviewed) - this dataset is not human-verified, only machine-accelerated."
        )

    train_ready = len(blocking) == 0 and len(usable) >= min_usable

    return QualityGateResult(
        train_ready=train_ready,
        usable_count=len(usable),
        usable_human_count=len(usable_human),
        usable_automated_count=len(usable_automated),
        total_count=total,
        pending_count=len(pending),
        rejected_count=len(rejected),
        blocking_issues=blocking,
        warnings=warnings,
    )


def balance_report(conn: sqlite3.Connection) -> dict:
    rows = conn.execute(
        "SELECT * FROM annotations WHERE review_status IN (?, ?)", USABLE_STATUSES
    ).fetchall()
    intent_counts: Counter = Counter()
    action_counts: Counter = Counter()
    context_counts: Counter = Counter()
    lang_intent: Counter = Counter()
    lang_action: Counter = Counter()
    for r in rows:
        intent, context, action = resolve_active_label(r)
        intent_counts[intent] += 1
        action_counts[action] += 1
        if context:
            context_counts[context] += 1
        lang_intent[(r["language"], intent)] += 1
        lang_action[(r["language"], action)] += 1
    return {
        "intent_distribution": dict(intent_counts.most_common()),
        "action_distribution": dict(action_counts.most_common()),
        "context_distribution": dict(context_counts.most_common()),
        "language_x_intent": {f"{lang}|{intent}": c for (lang, intent), c in lang_intent.items()},
        "language_x_action": {f"{lang}|{action}": c for (lang, action), c in lang_action.items()},
    }
