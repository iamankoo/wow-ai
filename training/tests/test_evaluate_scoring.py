"""Tests for the pure scoring logic in training/evaluation/evaluate.py -
_score, _valid_structured_output, _is_ambiguous. These operate on plain
dicts and don't require a trained model or the val.jsonl file to exist.
"""

from pathlib import Path

from training.evaluation.evaluate import (
    _is_ambiguous,
    _parse_model_dir_arg,
    _score,
    _valid_structured_output,
)


def test_parse_model_dir_arg_with_explicit_name():
    name, path = _parse_model_dir_arg("v1=training/models/wow-brain/v1")
    assert name == "v1"
    assert path == Path("training/models/wow-brain/v1")


def test_parse_model_dir_arg_defaults_name_to_dir_basename():
    name, path = _parse_model_dir_arg("training/models/wow-brain/v0")
    assert name == "v0"
    assert path == Path("training/models/wow-brain/v0")


def _record(text, intent, context_mode=None, action=None, language="en"):
    return {"text": text, "language": language, "intent": intent,
            "context_mode": context_mode, "action": action}


def _pred(intent, context_mode=None, action=None):
    return {"intent": intent, "context_mode": context_mode, "action": action, "confidence": None}


def test_valid_structured_output_accepts_real_taxonomy_members():
    assert _valid_structured_output(_pred("SET_CONTEXT", "BUSY", "SET_CONTEXT"))


def test_valid_structured_output_accepts_none_fields():
    assert _valid_structured_output(_pred(None, None, None))


def test_valid_structured_output_rejects_garbage_intent():
    assert not _valid_structured_output(_pred("NOT_A_REAL_INTENT"))


def test_is_ambiguous_true_only_for_unknown_intent():
    assert _is_ambiguous(_record("x", "UNKNOWN"))
    assert not _is_ambiguous(_record("x", "GENERAL_CONVERSATION"))


def test_score_perfect_predictions():
    records = [_record("a", "CALL_PERSON", action="NO_ACTION"), _record("b", "END_CONVERSATION", action="END_CALL")]
    predictions = [_pred("CALL_PERSON", action="NO_ACTION"), _pred("END_CONVERSATION", action="END_CALL")]
    report = _score(records, predictions)
    assert report["intent_accuracy"] == 1.0
    assert report["action_accuracy"] == 1.0
    assert report["failure_count"] == 0


def test_score_detects_mode_collapse():
    records = [_record(f"t{i}", intent) for i, intent in enumerate(
        ["A", "B", "C", "D", "E", "F", "G", "H", "I", "J"]
    )]
    # Every prediction is "A" regardless of the true label - classic collapse.
    predictions = [_pred("A") for _ in records]
    report = _score(records, predictions)
    assert report["most_predicted_intent"] == "A"
    assert report["most_predicted_intent_share"] == 1.0
    assert report["mode_collapse_suspected"] is True
    assert report["intent_accuracy"] == 0.1  # only the "A" record is correct


def test_score_no_collapse_when_predictions_are_varied_and_correct():
    records = [_record(f"t{i}", intent) for i, intent in enumerate(["A", "B", "C", "D", "E"])]
    predictions = [_pred(r["intent"]) for r in records]
    report = _score(records, predictions)
    assert report["mode_collapse_suspected"] is False
    assert report["intent_accuracy"] == 1.0


def test_score_confusion_matrix_records_expected_vs_predicted():
    records = [_record("a", "URGENT_CALL"), _record("b", "URGENT_CALL"), _record("c", "NON_URGENT_CALL")]
    predictions = [_pred("URGENT_CALL"), _pred("NON_URGENT_CALL"), _pred("NON_URGENT_CALL")]
    report = _score(records, predictions)
    confusion = report["intent_confusion_matrix"]
    assert confusion["URGENT_CALL"]["URGENT_CALL"] == 1
    assert confusion["URGENT_CALL"]["NON_URGENT_CALL"] == 1
    assert confusion["NON_URGENT_CALL"]["NON_URGENT_CALL"] == 1


def test_score_per_intent_accuracy_isolates_a_weak_class():
    records = (
        [_record(f"good{i}", "A") for i in range(4)]
        + [_record(f"bad{i}", "B") for i in range(4)]
    )
    predictions = (
        [_pred("A") for _ in range(4)]  # all A's correct
        + [_pred("A") for _ in range(4)]  # all B's wrongly predicted as A
    )
    report = _score(records, predictions)
    assert report["per_intent_accuracy"]["A"] == 1.0
    assert report["per_intent_accuracy"]["B"] == 0.0


def test_score_context_and_action_accuracy_only_count_labeled_records():
    records = [
        _record("a", "CALL_PERSON", context_mode=None, action=None),
        _record("b", "SET_CONTEXT", context_mode="BUSY", action="SET_CONTEXT"),
    ]
    predictions = [_pred("CALL_PERSON"), _pred("SET_CONTEXT", "BUSY", "SET_CONTEXT")]
    report = _score(records, predictions)
    assert report["context_total_evaluated"] == 1
    assert report["action_total_evaluated"] == 1
    assert report["context_accuracy"] == 1.0
    assert report["action_accuracy"] == 1.0
