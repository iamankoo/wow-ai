"""Tests for training/preprocessing/validate.py's dataset validation logic."""

import json

from training.preprocessing.validate import validate_file


def _write_jsonl(path, records):
    with path.open("w", encoding="utf-8") as f:
        for r in records:
            f.write(json.dumps(r) + "\n")


def test_validate_file_accepts_well_formed_intents(tmp_path):
    path = tmp_path / "seed.jsonl"
    _write_jsonl(path, [
        {"text": "Call Rahul for me.", "language": "en", "intent": "CALL_PERSON"},
        {"text": "Priya ko call karo.", "language": "hi", "intent": "CALL_PERSON"},
    ])
    count, errors = validate_file(path, "intents")
    assert count == 2
    assert errors == []


def test_validate_file_flags_duplicate_text_and_intent(tmp_path):
    path = tmp_path / "seed.jsonl"
    _write_jsonl(path, [
        {"text": "Call Rahul for me.", "language": "en", "intent": "CALL_PERSON"},
        {"text": "call rahul for me.", "language": "en", "intent": "CALL_PERSON"},
    ])
    _, errors = validate_file(path, "intents")
    assert any("duplicate" in e for e in errors)


def test_validate_file_flags_inconsistent_intent_for_same_text(tmp_path):
    path = tmp_path / "seed.jsonl"
    _write_jsonl(path, [
        {"text": "Busy.", "language": "en", "intent": "SET_CONTEXT", "context_mode": "BUSY"},
        {"text": "busy.", "language": "en", "intent": "UNKNOWN"},
    ])
    _, errors = validate_file(path, "intents")
    assert any("inconsistent expected output" in e for e in errors)


def test_validate_file_flags_invalid_intent_enum_value(tmp_path):
    path = tmp_path / "seed.jsonl"
    _write_jsonl(path, [
        {"text": "hello", "language": "en", "intent": "NOT_A_REAL_INTENT"},
    ])
    count, errors = validate_file(path, "intents")
    assert count == 0
    assert len(errors) == 1
    assert "schema validation failed" in errors[0]


def test_validate_file_flags_malformed_json_line(tmp_path):
    path = tmp_path / "seed.jsonl"
    path.write_text('{"text": "ok", "language": "en", "intent": "UNKNOWN"}\n{not json}\n', encoding="utf-8")
    count, errors = validate_file(path, "intents")
    assert count == 1
    assert any("malformed JSON" in e for e in errors)


def test_validate_file_skips_blank_lines(tmp_path):
    path = tmp_path / "seed.jsonl"
    path.write_text('{"text": "ok", "language": "en", "intent": "UNKNOWN"}\n\n   \n', encoding="utf-8")
    count, errors = validate_file(path, "intents")
    assert count == 1
    assert errors == []
