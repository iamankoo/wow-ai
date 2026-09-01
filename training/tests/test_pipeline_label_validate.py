from training.pipeline.label_validate import (
    CONFUSABLE_PAIRS,
    validate_hard_negative,
    validate_labels,
)
from training.pipeline.schema import RawExample


def test_valid_example_passes():
    ex = RawExample(text="Call Rahul.", language="en", intent="CALL_PERSON", action="NO_ACTION")
    result = validate_labels(ex)
    assert result.valid
    assert result.errors == []


def test_invalid_intent_is_rejected():
    ex = RawExample(text="x", language="en", intent="NOT_A_REAL_INTENT")
    result = validate_labels(ex)
    assert not result.valid
    assert any("invalid intent" in e for e in result.errors)


def test_invalid_context_mode_is_rejected():
    ex = RawExample(text="x", language="en", intent="SET_CONTEXT", context_mode="MOON")
    result = validate_labels(ex)
    assert not result.valid


def test_invalid_language_is_rejected():
    ex = RawExample(text="x", language="fr", intent="UNKNOWN")
    result = validate_labels(ex)
    assert not result.valid


def test_blank_text_is_rejected():
    ex = RawExample(text="   ", language="en", intent="UNKNOWN")
    result = validate_labels(ex)
    assert not result.valid


def test_hard_negative_requires_confusable_pair_and_notes():
    ex = RawExample(text="x", language="en", intent="URGENT_CALL", hard_negative=True)
    result = validate_hard_negative(ex)
    assert not result.valid
    assert any("confusable_pair" in e for e in result.errors)


def test_hard_negative_with_unrecognized_pair_is_rejected():
    ex = RawExample(
        text="x", language="en", intent="URGENT_CALL", hard_negative=True,
        confusable_pair="MADE_UP_PAIR", notes="explanation",
    )
    result = validate_hard_negative(ex)
    assert not result.valid


def test_valid_hard_negative_passes():
    ex = RawExample(
        text="The meeting isn't urgent anymore.", language="en", intent="NON_URGENT_CALL",
        hard_negative=True, confusable_pair=CONFUSABLE_PAIRS[0], notes="explanation",
    )
    result = validate_hard_negative(ex)
    assert result.valid


def test_non_hard_negative_examples_are_not_checked():
    ex = RawExample(text="x", language="en", intent="UNKNOWN")
    assert validate_hard_negative(ex).valid
