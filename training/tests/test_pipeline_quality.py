from training.pipeline.quality import score_batch, score_example
from training.pipeline.schema import RawExample


def test_clean_valid_example_passes():
    ex = RawExample(text="Call Rahul for me.", language="en", intent="CALL_PERSON", action="NO_ACTION")
    scored = score_example(ex)
    assert scored.flags.status == "pass"
    assert scored.flags.score == 1.0
    assert scored.flags.reasons == []


def test_invalid_intent_is_rejected():
    ex = RawExample(text="Call Rahul.", language="en", intent="NOT_REAL")
    scored = score_example(ex)
    assert scored.flags.status == "reject"
    assert scored.flags.valid_labels is False


def test_pii_is_redacted_and_flagged_for_review():
    ex = RawExample(text="Call me at 9876543210.", language="en", intent="CALL_PERSON", action="NO_ACTION")
    scored = score_example(ex)
    assert scored.flags.has_pii is True
    assert "9876543210" not in scored.redacted_text
    assert scored.flags.status == "review"


def test_exact_duplicate_flag_forces_reject():
    ex = RawExample(text="Call Rahul.", language="en", intent="CALL_PERSON")
    scored = score_example(ex, is_exact_duplicate=True)
    assert scored.flags.status == "reject"


def test_too_short_text_is_rejected():
    ex = RawExample(text="x", language="en", intent="UNKNOWN")
    scored = score_example(ex)
    assert scored.flags.length_ok is False
    assert scored.flags.status == "reject"


def test_language_mismatch_flags_review_not_reject():
    ex = RawExample(text="मैं सो रहा हूँ।", language="en", intent="SET_CONTEXT", context_mode="SLEEPING")
    scored = score_example(ex)
    assert scored.flags.language_consistent is False
    assert scored.flags.status == "review"


def test_score_batch_detects_duplicates_across_the_batch():
    examples = [
        RawExample(text="Call Rahul.", language="en", intent="CALL_PERSON"),
        RawExample(text="call rahul", language="en", intent="CALL_PERSON"),
    ]
    results = score_batch(examples)
    assert results[0].flags.status == "pass"
    assert results[1].flags.status == "reject"
    assert results[1].flags.is_exact_duplicate is True
