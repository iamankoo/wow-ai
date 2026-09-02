"""CallRetentionPolicy.is_expired - pure logic, no database required. See
app/learning/call_retention.py for the DB-backed cleanup_expired_calls,
tested in test_integration_db.py (needs a real session for the deletes)."""

from datetime import datetime, timedelta, timezone

from app.learning.call_retention import CallRetentionPolicy


def test_default_retention_is_fifteen_days():
    assert CallRetentionPolicy().max_age_days == 15


def test_recent_call_is_not_expired():
    policy = CallRetentionPolicy(max_age_days=15)
    now = datetime.now(timezone.utc)
    ended_at = now - timedelta(days=5)
    assert policy.is_expired(ended_at, now=now) is False


def test_old_call_is_expired():
    policy = CallRetentionPolicy(max_age_days=15)
    now = datetime.now(timezone.utc)
    ended_at = now - timedelta(days=20)
    assert policy.is_expired(ended_at, now=now) is True


def test_naive_datetime_is_treated_as_utc():
    policy = CallRetentionPolicy(max_age_days=15)
    now = datetime.now(timezone.utc)
    naive_ended_at = (now - timedelta(days=20)).replace(tzinfo=None)
    assert policy.is_expired(naive_ended_at, now=now) is True
