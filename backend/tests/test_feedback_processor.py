from datetime import datetime, timedelta, timezone

import pytest

from app.interfaces.feedback import (
    FeedbackCategory,
    FeedbackSource,
    FeedbackStatus,
    FeedbackSubmission,
    ImplicitSignalType,
)
from app.learning.feedback_processor import FeedbackProcessor
from app.learning.feedback_repository import InMemoryFeedbackRepository
from app.learning.privacy_filter import RegexPrivacyFilter
from app.learning.retention import RetentionPolicy


@pytest.fixture
def repo() -> InMemoryFeedbackRepository:
    return InMemoryFeedbackRepository()


@pytest.fixture
def processor(repo) -> FeedbackProcessor:
    return FeedbackProcessor(repo, RegexPrivacyFilter())


async def test_feedback_without_consent_is_rejected(repo, processor):
    record = await repo.create(FeedbackSubmission(
        user_id="u1", text="I'm actually in a meeting.",
        source=FeedbackSource.EXPLICIT, category=FeedbackCategory.USER_CORRECTION,
        consent_for_training=False,
    ))
    result = await processor.process_one(record)
    assert result.status == FeedbackStatus.REJECTED
    assert result.rejection_reason == "consent_not_given"


async def test_feedback_with_consent_becomes_a_candidate(repo, processor):
    record = await repo.create(FeedbackSubmission(
        user_id="u1", text="I'm actually in a meeting.",
        source=FeedbackSource.EXPLICIT, category=FeedbackCategory.USER_CORRECTION,
        consent_for_training=True,
    ))
    result = await processor.process_one(record)
    assert result.status == FeedbackStatus.CANDIDATE
    assert result.redacted_text == "I'm actually in a meeting."


async def test_expired_feedback_is_rejected_even_with_consent(repo):
    processor = FeedbackProcessor(repo, RegexPrivacyFilter(), RetentionPolicy(max_age_days=1))
    record = await repo.create(FeedbackSubmission(
        user_id="u1", text="old feedback",
        source=FeedbackSource.EXPLICIT, category=FeedbackCategory.CORRECT,
        consent_for_training=True,
    ))
    # Simulate an old, unprocessed event.
    stale = record
    stale.created_at = datetime.now(timezone.utc) - timedelta(days=5)
    result = await processor.process_one(stale)
    assert result.status == FeedbackStatus.REJECTED
    assert result.rejection_reason == "retention_expired"


async def test_pii_is_redacted_before_becoming_a_candidate(repo, processor):
    record = await repo.create(FeedbackSubmission(
        user_id="u1", text="Call me back at +91 98765 43210 to confirm.",
        source=FeedbackSource.EXPLICIT, category=FeedbackCategory.CORRECT,
        consent_for_training=True,
    ))
    result = await processor.process_one(record)
    assert result.status == FeedbackStatus.CANDIDATE
    assert "98765" not in result.redacted_text


async def test_explicit_correction_carries_full_confidence_weight(repo, processor):
    record = await repo.create(FeedbackSubmission(
        user_id="u1", text="text", source=FeedbackSource.EXPLICIT,
        category=FeedbackCategory.USER_CORRECTION, consent_for_training=True,
    ))
    result = await processor.process_one(record)
    assert result.confidence_weight == 1.0


async def test_implicit_weak_signal_carries_reduced_confidence_weight(repo, processor):
    record = await repo.create(FeedbackSubmission(
        user_id="u1", text="text", source=FeedbackSource.IMPLICIT,
        implicit_signal_type=ImplicitSignalType.TOOK_OVER_CALL, consent_for_training=True,
    ))
    result = await processor.process_one(record)
    assert result.confidence_weight == 0.4


async def test_non_received_records_are_untouched(repo, processor):
    record = await repo.create(FeedbackSubmission(
        user_id="u1", text="text", consent_for_training=True,
        status=FeedbackStatus.NEEDS_REVIEW,
    ))
    result = await processor.process_one(record)
    assert result.status == FeedbackStatus.NEEDS_REVIEW


async def test_approve_requires_a_named_reviewer(repo, processor):
    record = await repo.create(FeedbackSubmission(
        user_id="u1", text="text", source=FeedbackSource.EXPLICIT,
        category=FeedbackCategory.CORRECT, consent_for_training=True,
    ))
    candidate = await processor.process_one(record)
    with pytest.raises(ValueError, match="reviewed_by"):
        await processor.approve(candidate.id, reviewed_by="")


async def test_approve_only_works_on_candidates(repo, processor):
    record = await repo.create(FeedbackSubmission(
        user_id="u1", text="text", consent_for_training=False,
    ))
    rejected = await processor.process_one(record)  # -> REJECTED (no category = no consent path irrelevant here)
    with pytest.raises(ValueError, match="not CANDIDATE"):
        await processor.approve(rejected.id, reviewed_by="admin")


async def test_approve_transitions_candidate_to_approved(repo, processor):
    record = await repo.create(FeedbackSubmission(
        user_id="u1", text="text", source=FeedbackSource.EXPLICIT,
        category=FeedbackCategory.CORRECT, consent_for_training=True,
    ))
    candidate = await processor.process_one(record)
    approved = await processor.approve(candidate.id, reviewed_by="aniket")
    assert approved.status == FeedbackStatus.APPROVED


async def test_process_pending_processes_every_received_record_for_a_user(repo, processor):
    await repo.create(FeedbackSubmission(user_id="u1", text="a", consent_for_training=True,
                                          source=FeedbackSource.EXPLICIT, category=FeedbackCategory.CORRECT))
    await repo.create(FeedbackSubmission(user_id="u1", text="b", consent_for_training=False))
    results = await processor.process_pending(user_id="u1")
    assert len(results) == 2
    statuses = {r.status for r in results}
    assert statuses == {FeedbackStatus.CANDIDATE, FeedbackStatus.REJECTED}
