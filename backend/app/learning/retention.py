"""Retention policy: how long a RECEIVED feedback event may sit unprocessed
before it expires out of eligibility for training use. This bounds how long
raw (pre-redaction) text is meaningfully "live" in the pipeline - it does
not delete anything by itself (see PrivacyRightsService for deletion); it
just makes FeedbackProcessor refuse to promote stale events past RECEIVED.
"""

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone


@dataclass
class RetentionPolicy:
    max_age_days: int = 90

    def is_expired(self, created_at: datetime, *, now: datetime | None = None) -> bool:
        now = now or datetime.now(timezone.utc)
        if created_at.tzinfo is None:
            created_at = created_at.replace(tzinfo=timezone.utc)
        return now - created_at > timedelta(days=self.max_age_days)
