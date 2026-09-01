import json

import pytest

from training.pipeline.annotation.store import (
    apply_action,
    build_records,
    connect,
    get_stats,
    init_store,
    next_pending,
)


def _write_jsonl(path, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")


@pytest.fixture
def dataset_paths(tmp_path):
    relevant = tmp_path / "relevant.jsonl"
    rb = tmp_path / "rb.jsonl"
    v1 = tmp_path / "v1.jsonl"
    _write_jsonl(relevant, [
        {"id": "r1", "text": "Set me to busy.", "language": "en", "source_file": "english_dataset_1.txt", "source_line": 1, "source_order": 1},
        {"id": "r2", "text": "Aniket abhi so raha hai.", "language": "hinglish", "source_file": "hinglish_dataset_1.txt", "source_line": 2, "source_order": 2},
        {"id": "r3", "text": "मुझे नहीं पता।", "language": "hi", "source_file": "hindi_dataset_1.txt", "source_line": 3, "source_order": 3},
    ])
    _write_jsonl(rb, [
        {"id": "r1", "candidate_intent": "SET_CONTEXT", "candidate_context": "BUSY", "candidate_action": "SET_CONTEXT",
         "label_source": "candidate_rule_based", "label_confidence": "rule_matched"},
        {"id": "r2", "candidate_intent": "UNKNOWN", "candidate_context": None, "candidate_action": "NO_ACTION",
         "label_source": "review", "label_confidence": None},
        {"id": "r3", "candidate_intent": "UNKNOWN", "candidate_context": None, "candidate_action": "NO_ACTION",
         "label_source": "review", "label_confidence": None},
    ])
    _write_jsonl(v1, [
        {"id": "r2", "candidate_intent_v1": "SET_CONTEXT", "candidate_intent_v1_confidence": 0.82,
         "candidate_context_v1": "SLEEPING", "candidate_context_v1_confidence": 0.7,
         "candidate_action_v1": "SET_CONTEXT", "candidate_action_v1_confidence": 0.75},
        {"id": "r3", "candidate_intent_v1": "GENERAL_CONVERSATION", "candidate_intent_v1_confidence": 0.31,
         "candidate_context_v1": "NORMAL", "candidate_context_v1_confidence": 0.4,
         "candidate_action_v1": "NO_ACTION", "candidate_action_v1_confidence": 0.35},
    ])
    return relevant, rb, v1


def test_build_records_prefers_rule_based_candidate_when_committed(dataset_paths):
    relevant, rb, v1 = dataset_paths
    records = build_records(relevant, rb, v1)
    r1 = next(r for r in records if r["id"] == "r1")
    assert r1["candidate_source"] == "rule_based"
    assert r1["candidate_intent"] == "SET_CONTEXT"


def test_build_records_falls_back_to_v1_when_rule_based_has_no_match(dataset_paths):
    relevant, rb, v1 = dataset_paths
    records = build_records(relevant, rb, v1)
    r2 = next(r for r in records if r["id"] == "r2")
    assert r2["candidate_source"] == "v1"
    assert r2["candidate_intent"] == "SET_CONTEXT"
    assert r2["candidate_confidence"] == 0.82


def test_init_store_inserts_all_records(tmp_path, dataset_paths):
    relevant, rb, v1 = dataset_paths
    db_path = tmp_path / "test.db"
    result = init_store(db_path=db_path, relevant_path=relevant, rb_path=rb, v1_path=v1)
    assert result["inserted"] == 3
    conn = connect(db_path)
    assert conn.execute("SELECT COUNT(*) FROM annotations").fetchone()[0] == 3
    conn.close()


def test_init_store_is_idempotent_and_never_overwrites_human_work(tmp_path, dataset_paths):
    relevant, rb, v1 = dataset_paths
    db_path = tmp_path / "test.db"
    init_store(db_path=db_path, relevant_path=relevant, rb_path=rb, v1_path=v1)
    conn = connect(db_path)
    apply_action(conn, "r1", "approve", annotator="alice")
    conn.close()

    # Re-run init - r1 must remain approved, untouched.
    init_store(db_path=db_path, relevant_path=relevant, rb_path=rb, v1_path=v1)
    conn = connect(db_path)
    row = conn.execute("SELECT * FROM annotations WHERE id='r1'").fetchone()
    assert row["review_status"] == "approved"
    conn.close()


def test_next_pending_respects_priority_order(tmp_path, dataset_paths):
    relevant, rb, v1 = dataset_paths
    db_path = tmp_path / "test.db"
    init_store(db_path=db_path, relevant_path=relevant, rb_path=rb, v1_path=v1)
    conn = connect(db_path)
    row = next_pending(conn)
    # r1 has a committed rule-based candidate -> tier 1, should come first.
    assert row["id"] == "r1"
    conn.close()


def test_apply_action_approve_writes_candidate_as_human_label(tmp_path, dataset_paths):
    relevant, rb, v1 = dataset_paths
    db_path = tmp_path / "test.db"
    init_store(db_path=db_path, relevant_path=relevant, rb_path=rb, v1_path=v1)
    conn = connect(db_path)
    result = apply_action(conn, "r1", "approve", annotator="alice", confidence=5)
    assert result["ok"]
    row = conn.execute("SELECT * FROM annotations WHERE id='r1'").fetchone()
    assert row["human_intent"] == "SET_CONTEXT"
    assert row["label_source"] == "reviewed"
    assert row["review_status"] == "approved"
    conn.close()


def test_apply_action_correct_captures_hard_negative_when_label_changes(tmp_path, dataset_paths):
    relevant, rb, v1 = dataset_paths
    db_path = tmp_path / "test.db"
    init_store(db_path=db_path, relevant_path=relevant, rb_path=rb, v1_path=v1)
    conn = connect(db_path)
    result = apply_action(
        conn, "r1", "correct", annotator="alice",
        intent="GENERAL_CONVERSATION", context=None, wow_action="NO_ACTION",
    )
    assert result["ok"]
    assert result["hard_negative"] is not None
    assert result["hard_negative"]["predicted_intent"] == "SET_CONTEXT"
    assert result["hard_negative"]["correct_intent"] == "GENERAL_CONVERSATION"
    conn.close()


def test_apply_action_correct_without_label_change_does_not_capture_hard_negative(tmp_path, dataset_paths):
    relevant, rb, v1 = dataset_paths
    db_path = tmp_path / "test.db"
    init_store(db_path=db_path, relevant_path=relevant, rb_path=rb, v1_path=v1)
    conn = connect(db_path)
    result = apply_action(
        conn, "r1", "correct", annotator="alice",
        intent="SET_CONTEXT", context="BUSY", wow_action="SET_CONTEXT",
    )
    assert result["ok"]
    assert result["hard_negative"] is None
    conn.close()


def test_apply_action_correct_can_explicitly_clear_context_to_none(tmp_path, dataset_paths):
    # r1's candidate_context is "BUSY" - correcting with context=None must
    # actually persist None, not silently fall back to the candidate value.
    relevant, rb, v1 = dataset_paths
    db_path = tmp_path / "test.db"
    init_store(db_path=db_path, relevant_path=relevant, rb_path=rb, v1_path=v1)
    conn = connect(db_path)
    result = apply_action(
        conn, "r1", "correct", annotator="alice",
        intent="GENERAL_CONVERSATION", context=None, wow_action="NO_ACTION",
    )
    assert result["ok"]
    row = conn.execute("SELECT human_context FROM annotations WHERE id='r1'").fetchone()
    assert row["human_context"] is None
    conn.close()


def test_apply_action_rejects_invalid_intent(tmp_path, dataset_paths):
    relevant, rb, v1 = dataset_paths
    db_path = tmp_path / "test.db"
    init_store(db_path=db_path, relevant_path=relevant, rb_path=rb, v1_path=v1)
    conn = connect(db_path)
    result = apply_action(conn, "r1", "correct", annotator="alice", intent="NOT_REAL", wow_action="NO_ACTION")
    assert not result["ok"]
    row = conn.execute("SELECT review_status FROM annotations WHERE id='r1'").fetchone()
    assert row["review_status"] == "pending"
    conn.close()


def test_apply_action_reject_clears_labels(tmp_path, dataset_paths):
    relevant, rb, v1 = dataset_paths
    db_path = tmp_path / "test.db"
    init_store(db_path=db_path, relevant_path=relevant, rb_path=rb, v1_path=v1)
    conn = connect(db_path)
    result = apply_action(conn, "r3", "reject", annotator="alice", notes="unusable")
    assert result["ok"]
    row = conn.execute("SELECT * FROM annotations WHERE id='r3'").fetchone()
    assert row["review_status"] == "rejected"
    assert row["label_source"] == "rejected"
    conn.close()


def test_apply_action_skip_leaves_record_pending(tmp_path, dataset_paths):
    relevant, rb, v1 = dataset_paths
    db_path = tmp_path / "test.db"
    init_store(db_path=db_path, relevant_path=relevant, rb_path=rb, v1_path=v1)
    conn = connect(db_path)
    apply_action(conn, "r2", "skip", annotator="alice")
    row = conn.execute("SELECT * FROM annotations WHERE id='r2'").fetchone()
    assert row["review_status"] == "pending"
    assert row["label_source"] == "candidate"
    conn.close()


def test_get_stats_tracks_progress(tmp_path, dataset_paths):
    relevant, rb, v1 = dataset_paths
    db_path = tmp_path / "test.db"
    init_store(db_path=db_path, relevant_path=relevant, rb_path=rb, v1_path=v1)
    conn = connect(db_path)
    apply_action(conn, "r1", "approve", annotator="alice")
    stats = get_stats(conn)
    assert stats["total"] == 3
    assert stats["by_review_status"]["approved"] == 1
    assert stats["by_review_status"]["pending"] == 2
    conn.close()
