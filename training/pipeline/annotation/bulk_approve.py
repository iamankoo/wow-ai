"""Bulk automated approval of high-confidence candidate labels.

This is an ACCELERATION mechanism, not a human-review substitute. Records
touched by this module get review_status="approved" but label_source stays
"candidate" - never "human" - and a separate approved_by="automated_high_confidence"
field marks exactly which records were machine-approved so nothing downstream
can mistake this for human verification. The 1-5 `confidence` rating column
is a human subjective rating and is intentionally left untouched (None) by
this module - the real signal, the model/rule confidence score, is already
preserved unmodified in candidate_confidence/v1_intent_conf/etc.

Eligibility policy (deliberately strict, and NOT a blanket trust of the
rule-based classifier's confidence score):

  - v1_high_confidence: the record's only candidate signal is v1 (rule-based
    did not commit a match) AND v1's own softmax confidence is >= V1_STRICT_THRESHOLD
    on every label it predicts (intent and action always; context too, if
    the candidate has a context at all).

  - cross_verified: rule-based DID commit a match AND v1 independently
    predicts the exact same intent, action, and context AND v1's intent
    confidence clears a much lower sanity floor (V1_AGREEMENT_FLOOR).
    Rule-based's own "confidence" is a boolean match flag (always 1.0), not
    a calibrated probability - the taxonomy analysis phase found rule-based
    and v1 agree only ~13-19% of the time even when rule-based commits, so
    a rule-based match is trusted here only when v1 independently agrees,
    not on its own reported confidence.

Any record not meeting one of these two conditions is left pending for
human review - including every rule-based-only match that v1 does not
corroborate, and every v1 prediction below the strict threshold.
"""

from __future__ import annotations

import sqlite3
from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime, timezone

V1_STRICT_THRESHOLD = 0.90
V1_AGREEMENT_FLOOR = 0.50

APPROVED_BY_TAG = "automated_high_confidence"


def _context_equal(a, b) -> bool:
    return (a or None) == (b or None)


def eligibility_reason(row: sqlite3.Row) -> str:
    """Returns 'v1_high_confidence', 'cross_verified', or 'not_eligible'."""
    rb_committed = bool(row["rb_committed"])
    v1_intent = row["v1_intent"]

    if row["candidate_source"] == "v1" and not rb_committed:
        conf_ok = (
            row["v1_intent_conf"] is not None and row["v1_intent_conf"] >= V1_STRICT_THRESHOLD
            and row["v1_action_conf"] is not None and row["v1_action_conf"] >= V1_STRICT_THRESHOLD
        )
        context_ok = row["candidate_context"] is None or (
            row["v1_context_conf"] is not None and row["v1_context_conf"] >= V1_STRICT_THRESHOLD
        )
        if conf_ok and context_ok:
            return "v1_high_confidence"

    if rb_committed and v1_intent is not None:
        agree = (
            row["rb_intent"] == v1_intent
            and row["rb_action"] == row["v1_action"]
            and _context_equal(row["rb_context"], row["v1_context"])
        )
        floor_ok = row["v1_intent_conf"] is not None and row["v1_intent_conf"] >= V1_AGREEMENT_FLOOR
        if agree and floor_ok:
            return "cross_verified"

    return "not_eligible"


def _confidence_bucket(conf) -> str:
    if conf is None:
        return "no_signal"
    if conf >= 0.90:
        return "0.90-1.00"
    if conf >= 0.75:
        return "0.75-0.90"
    if conf >= 0.60:
        return "0.60-0.75"
    if conf >= 0.30:
        return "0.30-0.60"
    return "0.00-0.30"


@dataclass
class BulkApprovalPreview:
    total_records: int
    eligible_count: int
    remaining_for_review: int
    eligible_by_reason: dict
    already_reviewed: int
    confidence_distribution: dict
    intent_distribution: dict
    context_distribution: dict
    action_distribution: dict
    language_distribution: dict
    thresholds: dict = field(default_factory=lambda: {
        "v1_strict_threshold": V1_STRICT_THRESHOLD,
        "v1_agreement_floor": V1_AGREEMENT_FLOOR,
    })


def preview_bulk_approval(conn: sqlite3.Connection) -> BulkApprovalPreview:
    rows = conn.execute(
        "SELECT * FROM annotations WHERE review_status='pending' AND label_source='candidate'"
    ).fetchall()
    already_reviewed = conn.execute(
        "SELECT COUNT(*) FROM annotations WHERE NOT (review_status='pending' AND label_source='candidate')"
    ).fetchone()[0]
    total = conn.execute("SELECT COUNT(*) FROM annotations").fetchone()[0]

    reason_counts: Counter = Counter()
    eligible_rows = []
    for r in rows:
        reason = eligibility_reason(r)
        reason_counts[reason] += 1
        if reason != "not_eligible":
            eligible_rows.append(r)

    conf_dist: Counter = Counter()
    intent_dist: Counter = Counter()
    context_dist: Counter = Counter()
    action_dist: Counter = Counter()
    lang_dist: Counter = Counter()
    for r in eligible_rows:
        conf = r["candidate_confidence"]
        conf_dist[_confidence_bucket(conf)] += 1
        intent_dist[r["candidate_intent"]] += 1
        action_dist[r["candidate_action"]] += 1
        context_dist[r["candidate_context"] or "None"] += 1
        lang_dist[r["language"]] += 1

    eligible_count = len(eligible_rows)
    return BulkApprovalPreview(
        total_records=total,
        eligible_count=eligible_count,
        remaining_for_review=total - already_reviewed - eligible_count,
        eligible_by_reason={k: v for k, v in reason_counts.items() if k != "not_eligible"},
        already_reviewed=already_reviewed,
        confidence_distribution=dict(conf_dist.most_common()),
        intent_distribution=dict(intent_dist.most_common()),
        context_distribution=dict(context_dist.most_common()),
        action_distribution=dict(action_dist.most_common()),
        language_distribution=dict(lang_dist.most_common()),
    )


def execute_bulk_approval(conn: sqlite3.Connection) -> dict:
    """Applies the same eligibility policy used by preview_bulk_approval and
    marks each eligible record approved. Only ever touches rows that are
    still review_status='pending' AND label_source='candidate' - a record a
    human has already approved/corrected/rejected is never revisited."""
    rows = conn.execute(
        "SELECT * FROM annotations WHERE review_status='pending' AND label_source='candidate'"
    ).fetchall()
    now = datetime.now(timezone.utc).isoformat()

    approved_ids = []
    reason_counts: Counter = Counter()
    with conn:
        for r in rows:
            reason = eligibility_reason(r)
            if reason == "not_eligible":
                continue
            conn.execute(
                """UPDATE annotations SET
                    review_status='approved',
                    label_source='candidate',
                    approved_by=?,
                    annotated_at=?
                WHERE id=?""",
                (APPROVED_BY_TAG, now, r["id"]),
            )
            approved_ids.append(r["id"])
            reason_counts[reason] += 1

    return {
        "approved_count": len(approved_ids),
        "approved_by_reason": dict(reason_counts),
        "approved_by": APPROVED_BY_TAG,
    }


def execute_bulk_approve_all_pending(
    conn: sqlite3.Connection,
    approved_by: str,
    confidence: int | None = None,
) -> dict:
    """Approves EVERY still-pending candidate record exactly as its
    candidate_* columns already read - no confidence threshold, no
    eligibility check. This is a broad, explicitly human-authorized
    acceleration decision, distinct from execute_bulk_approval()'s strict
    statistical policy, and must only be called after a human has seen the
    dataset's actual state (e.g. via preview_bulk_approval() or
    store.get_stats()) and explicitly authorized approving everything.

    label_source is always left as "candidate" - never "human" - and no
    human_* column is ever written, so nothing here can be mistaken for a
    per-record human review later. `confidence`, if given, is stored as-is
    and is understood as the caller's own rating of their bulk-approval
    decision, not a claim about the underlying model's prediction
    confidence - there is no silent default, callers must pass it (or
    None) explicitly. candidate_intent/candidate_context/candidate_action
    and candidate_confidence/candidate_source are never touched - the
    original candidate prediction and its provenance are preserved
    unmodified."""
    if confidence is not None and not (1 <= confidence <= 5):
        raise ValueError(f"confidence must be 1-5, got {confidence}")

    rows = conn.execute(
        "SELECT id FROM annotations WHERE review_status='pending' AND label_source='candidate'"
    ).fetchall()
    now = datetime.now(timezone.utc).isoformat()
    with conn:
        conn.executemany(
            """UPDATE annotations SET
                review_status='approved',
                label_source='candidate',
                approved_by=?,
                confidence=?,
                annotated_at=?
            WHERE id=?""",
            [(approved_by, confidence, now, r["id"]) for r in rows],
        )

    return {
        "approved_count": len(rows),
        "approved_by": approved_by,
        "confidence": confidence,
    }


def post_approval_report(conn: sqlite3.Connection) -> dict:
    """Full dataset-state report after any approval operation (bulk or
    per-record). Distributions are computed via resolve_active_label() so
    they are correct regardless of whether a record's label came from a
    human, an automated threshold pass, or an explicitly authorized
    approve-everything pass."""
    from training.pipeline.annotation.schema import resolve_active_label

    total = conn.execute("SELECT COUNT(*) FROM annotations").fetchone()[0]
    approved_rows = conn.execute("SELECT * FROM annotations WHERE review_status='approved'").fetchall()
    corrected_count = conn.execute("SELECT COUNT(*) FROM annotations WHERE review_status='corrected'").fetchone()[0]
    rejected_count = conn.execute("SELECT COUNT(*) FROM annotations WHERE review_status='rejected'").fetchone()[0]
    pending_count = conn.execute("SELECT COUNT(*) FROM annotations WHERE review_status='pending'").fetchone()[0]

    previously_manual = [r for r in approved_rows if r["approved_by"] is None]
    by_approved_by: Counter = Counter()
    for r in approved_rows:
        by_approved_by[r["approved_by"] or "manual_per_record_review"] += 1

    intent_dist: Counter = Counter()
    context_dist: Counter = Counter()
    action_dist: Counter = Counter()
    lang_dist: Counter = Counter()
    source_dist: Counter = Counter()
    conf_bucket_dist: Counter = Counter()
    conf_bucket_by_source: dict = {"rule_based": Counter(), "v1": Counter(), "none": Counter()}
    for r in approved_rows:
        intent, context, action = resolve_active_label(r)
        intent_dist[intent] += 1
        if context:
            context_dist[context] += 1
        action_dist[action] += 1
        lang_dist[r["language"]] += 1
        source_dist[r["candidate_source"]] += 1
        bucket = _confidence_bucket(r["candidate_confidence"])
        conf_bucket_dist[bucket] += 1
        conf_bucket_by_source.setdefault(r["candidate_source"], Counter())[bucket] += 1

    return {
        "total_records": total,
        "approved_records_total": len(approved_rows),
        "approved_by_breakdown": dict(by_approved_by),
        "previously_manually_reviewed_records": len(previously_manual),
        "corrected_records": corrected_count,
        "rejected_records": rejected_count,
        "remaining_pending_records": pending_count,
        "intent_distribution": dict(intent_dist.most_common()),
        "context_distribution": dict(context_dist.most_common()),
        "action_distribution": dict(action_dist.most_common()),
        "language_distribution": dict(lang_dist.most_common()),
        "candidate_source_distribution": dict(source_dist.most_common()),
        "original_model_confidence_distribution": dict(conf_bucket_dist.most_common()),
        "original_model_confidence_distribution_by_source": {
            src: dict(counter.most_common()) for src, counter in conf_bucket_by_source.items() if counter
        },
    }
