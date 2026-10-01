"""A real, minimal "WOW handled a call" notification for a Plivo-routed
call (app/api/routes/telephony_plivo.py).

Scoped deliberately: the existing Android notification path
(NotificationHelper.kt's notifyCallHandled) only ever fires in-process,
from WowAutoAnswer.kt, right after a real GSM auto-answer - a Plivo call
never touches the phone's SIM/Telecom stack at all (it rings on Plivo's
own infrastructure), so that code path can't fire here, and there is no
push-notification infrastructure (e.g. Firebase Cloud Messaging) wired
into this project yet. Building real push delivery is real, separate
follow-up work - not done here.

What *is* real and useful today, for the first local test this module was
built for: a clearly-formatted structured log line at call end, so the
person running the backend (at their own PC, watching the terminal during
the test) sees a genuine, immediate confirmation of what happened -
caller, duration, transcript length, summary. This is deliberately not
dressed up as a phone push notification; the docstring and log message
both say plainly what this is and isn't.
"""

import logging

logger = logging.getLogger("app.notifications")


def notify_call_handled(
    *,
    caller_number: str | None,
    duration_seconds: float,
    turn_count: int,
    summary_text: str | None,
) -> None:
    """Logs a clear, human-readable "WOW handled a call" notification.
    Real and testable (see test_notifications.py's caplog assertions),
    intentionally not a phone push notification - see module docstring."""
    caller_label = caller_number or "an unknown number"
    logger.info(
        "WOW CALL HANDLED - caller=%s duration=%.1fs turns=%d summary=%s",
        caller_label,
        duration_seconds,
        turn_count,
        summary_text or "(none)",
    )
