from datetime import datetime, timezone

from app.interfaces.feedback import FeedbackRecord, FeedbackStatus
from app.learning.failure_mining import FailureMiner


def _record(**kw) -> FeedbackRecord:
    defaults = dict(
        id="x", user_id="u1", raw_text="t", status=FeedbackStatus.APPROVED,
        created_at=datetime.now(timezone.utc),
    )
    defaults.update(kw)
    return FeedbackRecord(**defaults)


def test_mines_recurring_intent_confusion():
    records = [
        _record(predicted_intent="SET_CONTEXT", corrected_intent="GENERAL_CONVERSATION"),
        _record(predicted_intent="SET_CONTEXT", corrected_intent="GENERAL_CONVERSATION"),
        _record(predicted_intent="SET_CONTEXT", corrected_intent="GENERAL_CONVERSATION"),
        _record(predicted_intent="UNKNOWN_CALLER", corrected_intent="KNOWN_CALLER"),
    ]
    report = FailureMiner().mine(records)
    assert report.total_events_analyzed == 4
    assert report.intent_confusions[0].predicted == "SET_CONTEXT"
    assert report.intent_confusions[0].corrected == "GENERAL_CONVERSATION"
    assert report.intent_confusions[0].count == 3
    assert report.intent_confusions[1].count == 1


def test_ignores_records_where_prediction_matches_correction():
    records = [_record(predicted_intent="CALL_PERSON", corrected_intent="CALL_PERSON")]
    report = FailureMiner().mine(records)
    assert report.total_events_analyzed == 0
    assert report.intent_confusions == []


def test_ignores_records_with_no_correction_at_all():
    records = [_record(predicted_intent="CALL_PERSON", corrected_intent=None)]
    report = FailureMiner().mine(records)
    assert report.total_events_analyzed == 0


def test_context_and_action_confusions_are_tracked_separately():
    records = [
        _record(predicted_context_mode="SLEEPING", corrected_context_mode="MEETING"),
        _record(predicted_action="NO_ACTION", corrected_action="MARK_URGENT"),
    ]
    report = FailureMiner().mine(records)
    assert len(report.context_confusions) == 1
    assert report.context_confusions[0].predicted == "SLEEPING"
    assert len(report.action_confusions) == 1
    assert report.action_confusions[0].predicted == "NO_ACTION"


def test_one_record_can_contribute_to_multiple_fields():
    records = [_record(
        predicted_intent="URGENT_CALL", corrected_intent="NON_URGENT_CALL",
        predicted_action="MARK_URGENT", corrected_action="COLLECT_MESSAGE",
    )]
    report = FailureMiner().mine(records)
    assert report.total_events_analyzed == 1
    assert len(report.intent_confusions) == 1
    assert len(report.action_confusions) == 1
