from training.pipeline.annotation.schema import (
    AnnotationRecord,
    is_valid_action,
    is_valid_context,
    is_valid_intent,
)


def test_valid_intent_accepted():
    assert is_valid_intent("SET_CONTEXT")
    assert not is_valid_intent("NOT_A_REAL_INTENT")


def test_context_none_is_valid():
    assert is_valid_context(None)
    assert is_valid_context("BUSY")
    assert not is_valid_context("NOT_A_CONTEXT")


def test_valid_action_accepted():
    assert is_valid_action("END_CALL")
    assert not is_valid_action("DESTROY_MODEL")


def _base_record(**overrides) -> AnnotationRecord:
    defaults = dict(
        id="x1", text="hello", language="en", source_file="f.txt",
        source_line=1, source_order=1,
    )
    defaults.update(overrides)
    return AnnotationRecord(**defaults)


def test_pending_candidate_record_has_no_validation_errors():
    rec = _base_record()
    assert rec.validate() == []


def test_approved_record_requires_valid_labels():
    # "reviewed" (approve) means the store copies candidate_* into human_*
    # before validate() ever runs - mirror that here.
    rec = _base_record(
        review_status="approved", label_source="reviewed",
        candidate_intent="SET_CONTEXT", candidate_action="SET_CONTEXT", candidate_context="BUSY",
        human_intent="SET_CONTEXT", human_action="SET_CONTEXT", human_context="BUSY",
    )
    assert rec.validate() == []


def test_approved_record_with_missing_intent_is_rejected():
    rec = _base_record(review_status="approved", label_source="reviewed")
    errors = rec.validate()
    assert any("intent" in e for e in errors)


def test_corrected_record_uses_human_labels_not_candidate():
    rec = _base_record(
        review_status="corrected", label_source="human",
        candidate_intent="UNKNOWN", candidate_action="NO_ACTION",
        human_intent="CALL_PERSON", human_action="TRANSFER_CALL", human_context=None,
    )
    assert rec.active_intent() == "CALL_PERSON"
    assert rec.validate() == []


def test_confidence_out_of_range_rejected():
    rec = _base_record(confidence=9)
    errors = rec.validate()
    assert any("confidence" in e for e in errors)


def test_invalid_label_source_rejected():
    rec = _base_record(label_source="bogus")
    assert any("label_source" in e for e in rec.validate())
