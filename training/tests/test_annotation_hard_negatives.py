from training.pipeline.annotation.hard_negatives import (
    append_hard_negative,
    load_hard_negatives,
    summarize,
)


def test_append_and_load_roundtrip(tmp_path):
    path = tmp_path / "hn.jsonl"
    append_hard_negative({"id": "a", "predicted_intent": "X", "correct_intent": "Y"}, path=path)
    append_hard_negative({"id": "b", "predicted_intent": "X", "correct_intent": "Y"}, path=path)
    loaded = load_hard_negatives(path)
    assert len(loaded) == 2
    assert loaded[0]["id"] == "a"


def test_load_hard_negatives_missing_file_returns_empty(tmp_path):
    assert load_hard_negatives(tmp_path / "missing.jsonl") == []


def test_summarize_groups_by_confusion_pair(tmp_path):
    path = tmp_path / "hn.jsonl"
    append_hard_negative({"id": "a", "predicted_intent": "URGENT_CALL", "correct_intent": "NON_URGENT_CALL"}, path=path)
    append_hard_negative({"id": "b", "predicted_intent": "URGENT_CALL", "correct_intent": "NON_URGENT_CALL"}, path=path)
    append_hard_negative({"id": "c", "predicted_intent": "SET_CONTEXT", "correct_intent": "GENERAL_CONVERSATION"}, path=path)
    summary = summarize(path)
    assert summary["total_captured"] == 3
    assert summary["by_confusion_pair"]["URGENT_CALL_confused_as_NON_URGENT_CALL"] == 2
