import json

import pytest

from training.pipeline.annotation.build_answer_call_dataset import (
    convert_answer_call_records,
    convert_hard_negative_records,
    map_context_phrase,
    sample_answer_call_file,
    validate_schema,
)


def _write_jsonl(path, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")


def test_map_context_phrase_sleeping():
    assert map_context_phrase("I'm asleep") == "SLEEPING"


def test_map_context_phrase_travelling():
    assert map_context_phrase("I'm at the airport") == "TRAVELLING"
    assert map_context_phrase("I'm driving") == "TRAVELLING"


def test_map_context_phrase_unavailable():
    assert map_context_phrase("I'm at a hospital") == "UNAVAILABLE"


def test_map_context_phrase_meeting():
    assert map_context_phrase("I'm in a meeting") == "MEETING"


def test_map_context_phrase_custom_for_technical_issues():
    assert map_context_phrase("my internet is down") == "CUSTOM"


def test_map_context_phrase_defaults_to_busy():
    assert map_context_phrase("I'm cooking") == "BUSY"


@pytest.fixture
def answer_call_fixture(tmp_path):
    # 3 context buckets x 20 records each = 60 total, small enough to
    # exercise real per-bucket reservoir sampling with a small per_bucket.
    path = tmp_path / "answer_call_test.jsonl"
    rows = []
    for ctx in ("I'm asleep", "I'm driving", "I'm cooking"):
        for i in range(20):
            rows.append({"text": f"caller {i} is calling while {ctx}", "label": "ANSWER_CALL",
                         "language": "english", "category": "answer_call", "context": ctx})
    _write_jsonl(path, rows)
    return path


def test_sample_answer_call_file_respects_per_bucket_count(answer_call_fixture):
    ctx_to_mode = {"I'm asleep": "SLEEPING", "I'm driving": "TRAVELLING", "I'm cooking": "BUSY"}
    sampled = sample_answer_call_file(answer_call_fixture, "en", ctx_to_mode, per_bucket=5)
    assert len(sampled) == 15  # 3 buckets x 5


def test_sample_answer_call_file_is_deterministic(answer_call_fixture):
    ctx_to_mode = {"I'm asleep": "SLEEPING", "I'm driving": "TRAVELLING", "I'm cooking": "BUSY"}
    sample1 = sample_answer_call_file(answer_call_fixture, "en", ctx_to_mode, per_bucket=5)
    sample2 = sample_answer_call_file(answer_call_fixture, "en", ctx_to_mode, per_bucket=5)
    assert [s["source_line"] for s in sample1] == [s["source_line"] for s in sample2]


def test_sample_answer_call_file_does_not_just_take_the_first_n(answer_call_fixture):
    # With per_bucket >= bucket size, reservoir sampling degenerates to "all
    # of them" - use a smaller per_bucket than the 20-item bucket so the
    # selection is a genuine (seeded) subsample, and confirm it is NOT
    # simply lines 1-5 of each bucket.
    ctx_to_mode = {"I'm asleep": "SLEEPING", "I'm driving": "TRAVELLING", "I'm cooking": "BUSY"}
    sampled = sample_answer_call_file(answer_call_fixture, "en", ctx_to_mode, per_bucket=5)
    sleeping_lines = sorted(s["source_line"] for s in sampled if s["context_mode"] == "SLEEPING")
    assert sleeping_lines != [1, 2, 3, 4, 5]


def test_convert_answer_call_records_builds_expected_schema(answer_call_fixture):
    ctx_to_mode = {"I'm asleep": "SLEEPING", "I'm driving": "TRAVELLING", "I'm cooking": "BUSY"}
    sampled = sample_answer_call_file(answer_call_fixture, "en", ctx_to_mode, per_bucket=2)
    converted = convert_answer_call_records(sampled, "en", "answer_call_test.jsonl")
    assert len(converted) == 6
    r = converted[0]
    assert r["intent"] == "HANDLE_CALLS"
    assert r["action"] == "ANSWER_CALL"
    assert r["context_mode"] in ("SLEEPING", "TRAVELLING", "BUSY")
    assert r["language"] == "en"
    assert r["label_source"] == "candidate"
    assert r["approved_by"] == "answer_call_dataset_import"
    assert r["source_file"] == "answer_call_test.jsonl"
    assert r["source_line"] > 0


@pytest.fixture
def hard_negative_fixture(tmp_path):
    path = tmp_path / "hard_negatives_test.jsonl"
    rows = [
        {"text": "Call Aniket.", "label": "CALL_PERSON", "language": "hinglish", "category": "hard_negative"},
        {"text": "Please hang up now.", "label": "END_CALL", "language": "english", "category": "hard_negative"},
        {"text": "This is urgent, call me.", "label": "URGENT_CALL", "language": "english", "category": "hard_negative"},
        {"text": "Take a message for me.", "label": "COLLECT_MESSAGE", "language": "english", "category": "hard_negative"},
    ]
    _write_jsonl(path, rows)
    return path


def test_convert_hard_negative_records_preserves_intent_label(hard_negative_fixture):
    converted, issues = convert_hard_negative_records(hard_negative_fixture)
    call_person = next(r for r in converted if r["text"] == "Call Aniket.")
    assert call_person["intent"] == "CALL_PERSON"
    assert call_person["language"] == "hinglish"


def test_convert_hard_negative_records_preserves_action_label(hard_negative_fixture):
    converted, issues = convert_hard_negative_records(hard_negative_fixture)
    end_call = next(r for r in converted if "hang up" in r["text"])
    assert end_call["action"] == "END_CALL"


def test_convert_hard_negative_records_never_assigns_answer_call_action(hard_negative_fixture):
    converted, issues = convert_hard_negative_records(hard_negative_fixture)
    assert all(r["action"] != "ANSWER_CALL" for r in converted)


def test_convert_hard_negative_records_derives_the_missing_field(hard_negative_fixture):
    converted, issues = convert_hard_negative_records(hard_negative_fixture)
    for r in converted:
        assert r["intent"], f"missing intent for {r}"
        assert r["action"], f"missing action for {r}"


def test_validate_schema_flags_bad_intent():
    records = [{"id": "x", "text": "hi", "language": "en", "intent": "NOT_REAL",
                "context_mode": None, "action": "NO_ACTION", "source_file": "f", "source_line": 1}]
    report = validate_schema(records)
    assert report["bad_intent"] == 1


def test_validate_schema_passes_clean_record():
    records = [{"id": "x", "text": "hi", "language": "en", "intent": "HANDLE_CALLS",
                "context_mode": "BUSY", "action": "ANSWER_CALL", "source_file": "f", "source_line": 1}]
    report = validate_schema(records)
    assert all(v == 0 for v in report.values())
