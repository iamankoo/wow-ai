"""StageTimings + log_agent_turn - see app/observability/."""

import inspect
import logging

from app.observability.logging import log_agent_turn
from app.observability.timing import StageTimings


def test_measure_records_a_non_negative_duration():
    timings = StageTimings()
    with timings.measure("stage_a"):
        pass
    assert "stage_a" in timings.durations_ms
    assert timings.durations_ms["stage_a"] >= 0


def test_measure_records_each_stage_independently():
    timings = StageTimings()
    with timings.measure("a"):
        pass
    with timings.measure("b"):
        pass
    assert set(timings.durations_ms) == {"a", "b"}


def test_log_agent_turn_signature_has_no_text_or_transcript_field():
    """Structural guarantee: this function cannot be called with raw
    conversation content because no such parameter exists."""
    params = set(inspect.signature(log_agent_turn).parameters)
    assert not params & {"text", "reply", "transcript", "content", "message"}


def test_log_agent_turn_emits_one_structured_record(caplog):
    with caplog.at_level(logging.INFO, logger="wow_ai.agent"):
        log_agent_turn(
            user_id="u1",
            conversation_id="c1",
            intent="GENERAL_CONVERSATION",
            candidate_action=None,
            policy_decision="allow",
            policy_reason="no_action_requested",
            tool_names=[],
            tool_success=True,
            durations_ms={"context": 1.0, "brain": 2.0},
        )
    assert len(caplog.records) == 1
    record = caplog.records[0]
    assert record.user_id == "u1"
    assert record.conversation_id == "c1"
    assert record.durations_ms == {"context": 1.0, "brain": 2.0}
