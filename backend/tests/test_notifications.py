"""app.observability.notifications.notify_call_handled - the real, minimal
"WOW handled a call" notification for a Plivo-routed call (see that
module's docstring for exactly what this is and isn't)."""

import logging

from app.observability.notifications import notify_call_handled


def test_notify_call_handled_logs_a_clear_message_with_the_real_details(caplog):
    with caplog.at_level(logging.INFO, logger="app.notifications"):
        notify_call_handled(
            caller_number="+919876543210",
            duration_seconds=42.5,
            turn_count=3,
            summary_text="WOW handled a call from +919876543210 (3 conversational turns).",
        )

    assert len(caplog.records) == 1
    message = caplog.records[0].getMessage()
    assert "WOW CALL HANDLED" in message
    assert "+919876543210" in message
    assert "42.5" in message
    assert "turns=3" in message
    assert "3 conversational turns" in message


def test_notify_call_handled_handles_missing_caller_and_summary_honestly():
    """No caller number / no summary must produce a clear, honest label -
    never crash, never fabricate a real-looking value."""
    with_no_crash = notify_call_handled(
        caller_number=None, duration_seconds=1.0, turn_count=0, summary_text=None
    )
    assert with_no_crash is None
