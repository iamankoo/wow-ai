import json

import pytest

from training.pipeline.annotation.quality_gates import balance_report, evaluate_quality_gates
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
        {"id": f"r{i}", "text": f"text {i}", "language": "en", "source_file": "english_dataset_1.txt", "source_line": i, "source_order": i}
        for i in range(1, 6)
    ])
    _write_jsonl(rb, [
        {"id": f"r{i}", "candidate_intent": "SET_CONTEXT", "candidate_context": "BUSY", "candidate_action": "SET_CONTEXT",
         "label_source": "candidate_rule_based", "label_confidence": "rule_matched"}
        for i in range(1, 6)
    ])
    _write_jsonl(v1, [])
    db_path = tmp_path / "test.db"
    init_store(db_path=db_path, relevant_path=relevant, rb_path=rb, v1_path=v1)
    conn = connect(db_path)
    yield conn
    conn.close()


def test_quality_gate_not_train_ready_with_no_usable_examples(store):
    result = evaluate_quality_gates(store, min_usable=1)
    assert not result.train_ready
    assert result.usable_count == 0


def test_quality_gate_train_ready_once_min_usable_approved(store):
    for i in range(1, 6):
        apply_action(store, f"r{i}", "approve", annotator="alice")
    result = evaluate_quality_gates(store, min_usable=5)
    assert result.train_ready
    assert result.usable_count == 5
    assert result.blocking_issues == []


def test_quality_gate_flags_pending_as_warning_not_blocking(store):
    apply_action(store, "r1", "approve", annotator="alice")
    result = evaluate_quality_gates(store, min_usable=1)
    assert result.train_ready
    assert any("pending" in w for w in result.warnings)


def test_balance_report_counts_intents_without_rebalancing(store):
    apply_action(store, "r1", "approve", annotator="alice")
    apply_action(store, "r2", "approve", annotator="alice")
    apply_action(store, "r3", "correct", annotator="alice", intent="GENERAL_CONVERSATION", context=None, wow_action="NO_ACTION")
    report = balance_report(store)
    assert report["intent_distribution"]["SET_CONTEXT"] == 2
    assert report["intent_distribution"]["GENERAL_CONVERSATION"] == 1
