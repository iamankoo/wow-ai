import json

import pytest

from training.pipeline.annotation.bulk_approve import (
    eligibility_reason,
    execute_bulk_approval,
    execute_bulk_approve_all_pending,
    post_approval_report,
    preview_bulk_approval,
)
from training.pipeline.annotation.quality_gates import evaluate_quality_gates
from training.pipeline.annotation.store import apply_action, connect, init_store


def _write_jsonl(path, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")


@pytest.fixture
def store(tmp_path):
    relevant = tmp_path / "relevant.jsonl"
    rb = tmp_path / "rb.jsonl"
    v1 = tmp_path / "v1.jsonl"

    _write_jsonl(relevant, [
        {"id": "r1_cross_verified", "text": "Set me to busy.", "language": "en", "source_file": "english_dataset_1.txt", "source_line": 1, "source_order": 1},
        {"id": "r2_rb_only_disagrees", "text": "Set me to busy please.", "language": "en", "source_file": "english_dataset_1.txt", "source_line": 2, "source_order": 2},
        {"id": "r3_v1_high_conf", "text": "Aniket abhi so raha hai.", "language": "hinglish", "source_file": "hinglish_dataset_1.txt", "source_line": 3, "source_order": 3},
        {"id": "r4_v1_mid_conf", "text": "kal call kar lena", "language": "hinglish", "source_file": "hinglish_dataset_1.txt", "source_line": 4, "source_order": 4},
        {"id": "r5_v1_partial_conf", "text": "mujhe nahi pata", "language": "hi", "source_file": "hindi_dataset_1.txt", "source_line": 5, "source_order": 5},
        {"id": "r6_already_human", "text": "Call Rahul now.", "language": "en", "source_file": "english_dataset_1.txt", "source_line": 6, "source_order": 6},
    ])
    _write_jsonl(rb, [
        {"id": "r1_cross_verified", "candidate_intent": "SET_CONTEXT", "candidate_context": "BUSY", "candidate_action": "SET_CONTEXT",
         "label_source": "candidate_rule_based", "label_confidence": "rule_matched"},
        {"id": "r2_rb_only_disagrees", "candidate_intent": "SET_CONTEXT", "candidate_context": "BUSY", "candidate_action": "SET_CONTEXT",
         "label_source": "candidate_rule_based", "label_confidence": "rule_matched"},
        {"id": "r3_v1_high_conf", "candidate_intent": "UNKNOWN", "candidate_context": None, "candidate_action": "NO_ACTION",
         "label_source": "review", "label_confidence": None},
        {"id": "r4_v1_mid_conf", "candidate_intent": "UNKNOWN", "candidate_context": None, "candidate_action": "NO_ACTION",
         "label_source": "review", "label_confidence": None},
        {"id": "r5_v1_partial_conf", "candidate_intent": "UNKNOWN", "candidate_context": None, "candidate_action": "NO_ACTION",
         "label_source": "review", "label_confidence": None},
        {"id": "r6_already_human", "candidate_intent": "CALL_PERSON", "candidate_context": None, "candidate_action": "ANSWER_CALL",
         "label_source": "candidate_rule_based", "label_confidence": "rule_matched"},
    ])
    _write_jsonl(v1, [
        {"id": "r1_cross_verified", "candidate_intent_v1": "SET_CONTEXT", "candidate_intent_v1_confidence": 0.6,
         "candidate_context_v1": "BUSY", "candidate_context_v1_confidence": 0.6,
         "candidate_action_v1": "SET_CONTEXT", "candidate_action_v1_confidence": 0.6},
        {"id": "r2_rb_only_disagrees", "candidate_intent_v1": "GENERAL_CONVERSATION", "candidate_intent_v1_confidence": 0.55,
         "candidate_context_v1": None, "candidate_context_v1_confidence": 0.5,
         "candidate_action_v1": "NO_ACTION", "candidate_action_v1_confidence": 0.55},
        {"id": "r3_v1_high_conf", "candidate_intent_v1": "SET_CONTEXT", "candidate_intent_v1_confidence": 0.95,
         "candidate_context_v1": None, "candidate_context_v1_confidence": None,
         "candidate_action_v1": "SET_CONTEXT", "candidate_action_v1_confidence": 0.93},
        {"id": "r4_v1_mid_conf", "candidate_intent_v1": "SCHEDULE_REQUEST", "candidate_intent_v1_confidence": 0.5,
         "candidate_context_v1": None, "candidate_context_v1_confidence": 0.5,
         "candidate_action_v1": "NO_ACTION", "candidate_action_v1_confidence": 0.5},
        {"id": "r5_v1_partial_conf", "candidate_intent_v1": "GENERAL_CONVERSATION", "candidate_intent_v1_confidence": 0.95,
         "candidate_context_v1": None, "candidate_context_v1_confidence": 0.5,
         "candidate_action_v1": "NO_ACTION", "candidate_action_v1_confidence": 0.6},
        {"id": "r6_already_human", "candidate_intent_v1": "CALL_PERSON", "candidate_intent_v1_confidence": 0.9,
         "candidate_context_v1": None, "candidate_context_v1_confidence": 0.5,
         "candidate_action_v1": "ANSWER_CALL", "candidate_action_v1_confidence": 0.9},
    ])

    db_path = tmp_path / "test.db"
    init_store(db_path=db_path, relevant_path=relevant, rb_path=rb, v1_path=v1)
    conn = connect(db_path)
    # r6 was already reviewed by a human before the bulk pass runs.
    apply_action(conn, "r6_already_human", "approve", annotator="alice")
    yield conn
    conn.close()


# r3's note: candidate_context is None (rule-based never committed a
# context, so the merged candidate_context is None), so context confidence
# is not required for it - only intent and action confidence.

def test_r1_is_cross_verified(store):
    row = store.execute("SELECT * FROM annotations WHERE id='r1_cross_verified'").fetchone()
    assert eligibility_reason(row) == "cross_verified"


def test_r2_rule_based_alone_is_not_eligible(store):
    row = store.execute("SELECT * FROM annotations WHERE id='r2_rb_only_disagrees'").fetchone()
    assert eligibility_reason(row) == "not_eligible"


def test_r3_high_confidence_v1_only_is_eligible(store):
    row = store.execute("SELECT * FROM annotations WHERE id='r3_v1_high_conf'").fetchone()
    assert eligibility_reason(row) == "v1_high_confidence"


def test_r4_mid_confidence_v1_only_is_not_eligible(store):
    row = store.execute("SELECT * FROM annotations WHERE id='r4_v1_mid_conf'").fetchone()
    assert eligibility_reason(row) == "not_eligible"


def test_r5_partial_high_confidence_is_not_eligible(store):
    # intent conf is high but action conf (0.6) is below threshold - both must clear the bar.
    row = store.execute("SELECT * FROM annotations WHERE id='r5_v1_partial_conf'").fetchone()
    assert eligibility_reason(row) == "not_eligible"


def test_preview_counts_are_consistent(store):
    preview = preview_bulk_approval(store)
    assert preview.total_records == 6
    assert preview.already_reviewed == 1  # r6
    assert preview.eligible_count == 2  # r1, r3
    assert preview.eligible_by_reason == {"cross_verified": 1, "v1_high_confidence": 1}
    assert preview.remaining_for_review == 3  # r2, r4, r5


def test_preview_never_touches_the_database(store):
    preview_bulk_approval(store)
    row = store.execute("SELECT review_status FROM annotations WHERE id='r1_cross_verified'").fetchone()
    assert row["review_status"] == "pending"


def test_execute_approves_only_eligible_records(store):
    result = execute_bulk_approval(store)
    assert result["approved_count"] == 2
    assert result["approved_by"] == "automated_high_confidence"

    r1 = store.execute("SELECT * FROM annotations WHERE id='r1_cross_verified'").fetchone()
    assert r1["review_status"] == "approved"
    assert r1["label_source"] == "candidate"
    assert r1["approved_by"] == "automated_high_confidence"
    assert r1["human_intent"] is None  # never fabricate a human label

    r2 = store.execute("SELECT * FROM annotations WHERE id='r2_rb_only_disagrees'").fetchone()
    assert r2["review_status"] == "pending"


def test_execute_does_not_touch_already_reviewed_records(store):
    execute_bulk_approval(store)
    r6 = store.execute("SELECT * FROM annotations WHERE id='r6_already_human'").fetchone()
    assert r6["approved_by"] is None
    assert r6["label_source"] == "reviewed"


def test_execute_never_writes_a_fabricated_confidence_rating(store):
    execute_bulk_approval(store)
    r1 = store.execute("SELECT confidence FROM annotations WHERE id='r1_cross_verified'").fetchone()
    assert r1["confidence"] is None


def test_execute_preserves_original_candidate_predictions(store):
    before = dict(store.execute("SELECT candidate_intent, candidate_confidence, candidate_source FROM annotations WHERE id='r1_cross_verified'").fetchone())
    execute_bulk_approval(store)
    after = dict(store.execute("SELECT candidate_intent, candidate_confidence, candidate_source FROM annotations WHERE id='r1_cross_verified'").fetchone())
    assert before == after


def test_quality_gate_resolves_automated_approvals_correctly(store):
    execute_bulk_approval(store)
    gate = evaluate_quality_gates(store, min_usable=1)
    assert gate.usable_count == 3  # r1, r3 (automated) + r6 (human)
    assert gate.usable_automated_count == 2
    assert gate.usable_human_count == 1
    assert gate.blocking_issues == []
    assert any("automatically approved" in w for w in gate.warnings)


def test_execute_is_idempotent_on_rerun(store):
    first = execute_bulk_approval(store)
    second = execute_bulk_approval(store)
    assert first["approved_count"] == 2
    assert second["approved_count"] == 0


# ---------------------------------------------------------------------------
# execute_bulk_approve_all_pending - approve everything, unconditionally.
# ---------------------------------------------------------------------------

def test_bulk_approve_all_approves_every_pending_record(store):
    result = execute_bulk_approve_all_pending(store, approved_by="Aniket_bulk_approval", confidence=5)
    # 6 total, 1 (r6) already reviewed -> 5 pending should all be approved.
    assert result["approved_count"] == 5
    assert result["approved_by"] == "Aniket_bulk_approval"
    assert result["confidence"] == 5


def test_bulk_approve_all_does_not_touch_already_reviewed(store):
    execute_bulk_approve_all_pending(store, approved_by="Aniket_bulk_approval", confidence=5)
    r6 = store.execute("SELECT * FROM annotations WHERE id='r6_already_human'").fetchone()
    assert r6["approved_by"] is None
    assert r6["label_source"] == "reviewed"
    assert r6["confidence"] is None


def test_bulk_approve_all_never_sets_label_source_human(store):
    execute_bulk_approve_all_pending(store, approved_by="Aniket_bulk_approval", confidence=5)
    rows = store.execute("SELECT label_source FROM annotations WHERE approved_by='Aniket_bulk_approval'").fetchall()
    assert all(r["label_source"] == "candidate" for r in rows)


def test_bulk_approve_all_never_writes_human_columns(store):
    execute_bulk_approve_all_pending(store, approved_by="Aniket_bulk_approval", confidence=5)
    r2 = store.execute("SELECT human_intent, human_context, human_action FROM annotations WHERE id='r2_rb_only_disagrees'").fetchone()
    assert r2["human_intent"] is None
    assert r2["human_context"] is None
    assert r2["human_action"] is None


def test_bulk_approve_all_preserves_candidate_predictions_and_source(store):
    before = dict(store.execute(
        "SELECT candidate_intent, candidate_context, candidate_action, candidate_confidence, candidate_source "
        "FROM annotations WHERE id='r2_rb_only_disagrees'"
    ).fetchone())
    execute_bulk_approve_all_pending(store, approved_by="Aniket_bulk_approval", confidence=5)
    after = dict(store.execute(
        "SELECT candidate_intent, candidate_context, candidate_action, candidate_confidence, candidate_source "
        "FROM annotations WHERE id='r2_rb_only_disagrees'"
    ).fetchone())
    assert before == after


def test_bulk_approve_all_confidence_can_be_none(store):
    execute_bulk_approve_all_pending(store, approved_by="Aniket_bulk_approval", confidence=None)
    r2 = store.execute("SELECT confidence FROM annotations WHERE id='r2_rb_only_disagrees'").fetchone()
    assert r2["confidence"] is None


def test_bulk_approve_all_rejects_out_of_range_confidence(store):
    with pytest.raises(ValueError):
        execute_bulk_approve_all_pending(store, approved_by="Aniket_bulk_approval", confidence=9)


def test_bulk_approve_all_is_idempotent(store):
    first = execute_bulk_approve_all_pending(store, approved_by="Aniket_bulk_approval", confidence=5)
    second = execute_bulk_approve_all_pending(store, approved_by="Aniket_bulk_approval", confidence=5)
    assert first["approved_count"] == 5
    assert second["approved_count"] == 0


def test_post_approval_report_counts(store):
    execute_bulk_approve_all_pending(store, approved_by="Aniket_bulk_approval", confidence=5)
    report = post_approval_report(store)
    assert report["total_records"] == 6
    assert report["approved_records_total"] == 6  # 5 bulk + 1 prior manual
    assert report["previously_manually_reviewed_records"] == 1
    assert report["approved_by_breakdown"] == {"Aniket_bulk_approval": 5, "manual_per_record_review": 1}
    assert report["remaining_pending_records"] == 0
    assert report["rejected_records"] == 0


def test_post_approval_report_resolves_labels_for_bulk_approved_records(store):
    execute_bulk_approve_all_pending(store, approved_by="Aniket_bulk_approval", confidence=5)
    report = post_approval_report(store)
    # r2's candidate intent is SET_CONTEXT (rule-based, uncorroborated) - must show up
    # in the distribution even though it was never touched by execute_bulk_approval().
    assert report["intent_distribution"]["SET_CONTEXT"] >= 1


def test_post_approval_report_source_and_confidence_distributions(store):
    execute_bulk_approve_all_pending(store, approved_by="Aniket_bulk_approval", confidence=5)
    report = post_approval_report(store)
    assert set(report["candidate_source_distribution"].keys()) <= {"rule_based", "v1", "none"}
    assert sum(report["original_model_confidence_distribution"].values()) == report["approved_records_total"]
