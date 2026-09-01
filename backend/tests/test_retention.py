from datetime import datetime, timedelta, timezone

from app.learning.retention import RetentionPolicy


def test_recent_event_is_not_expired():
    policy = RetentionPolicy(max_age_days=90)
    now = datetime.now(timezone.utc)
    assert policy.is_expired(now - timedelta(days=1), now=now) is False


def test_old_event_is_expired():
    policy = RetentionPolicy(max_age_days=90)
    now = datetime.now(timezone.utc)
    assert policy.is_expired(now - timedelta(days=91), now=now) is True


def test_boundary_is_not_expired():
    policy = RetentionPolicy(max_age_days=90)
    now = datetime.now(timezone.utc)
    assert policy.is_expired(now - timedelta(days=90), now=now) is False


def test_handles_naive_datetimes_as_utc():
    policy = RetentionPolicy(max_age_days=90)
    now = datetime.now(timezone.utc)
    naive_old = (now - timedelta(days=100)).replace(tzinfo=None)
    assert policy.is_expired(naive_old, now=now) is True
