"""End-to-end mechanics of the active-learning review queue: a low-
confidence prediction gets logged as NEEDS_REVIEW, sits there until the
user responds, and only then enters the ordinary privacy pipeline. This is
the InMemory-repository equivalent of what POST /feedback/{id}/respond
does against a real DB - see app/api/routes/feedback.py.
"""

from dataclasses import replace

from app.interfaces.feedback import (
    FeedbackCategory,
    FeedbackSource,
    FeedbackStatus,
    FeedbackSubmission,
)
from app.learning.confidence import ConfidencePolicy, ConfidenceThresholds
from app.learning.feedback_processor import FeedbackProcessor
from app.learning.feedback_repository import InMemoryFeedbackRepository
from app.learning.privacy_filter import RegexPrivacyFilter


def test_low_confidence_prediction_is_flagged_for_review():
    policy = ConfidencePolicy(ConfidenceThresholds(intent=0.6))
    assessment = policy.assess(intent_confidence=0.42)
    assert assessment.needs_review is True


async def test_low_confidence_prediction_can_be_logged_to_the_queue():
    repo = InMemoryFeedbackRepository()
    record = await repo.create(FeedbackSubmission(
        user_id="u1", text="I'm sleeping.",
        predicted_intent="SET_CONTEXT", predicted_context_mode="SLEEPING",
        intent_confidence=0.42, model_version="v1",
        status=FeedbackStatus.NEEDS_REVIEW,
    ))
    assert record.status == FeedbackStatus.NEEDS_REVIEW

    queue = await repo.list_by_status(FeedbackStatus.NEEDS_REVIEW, user_id="u1")
    assert len(queue) == 1
    assert queue[0].predicted_intent == "SET_CONTEXT"


async def test_processor_leaves_review_queue_items_untouched():
    repo = InMemoryFeedbackRepository()
    processor = FeedbackProcessor(repo, RegexPrivacyFilter())
    record = await repo.create(FeedbackSubmission(
        user_id="u1", text="I'm sleeping.", status=FeedbackStatus.NEEDS_REVIEW,
    ))
    result = await processor.process_one(record)
    assert result.status == FeedbackStatus.NEEDS_REVIEW  # not auto-processed


async def test_user_confirming_a_review_item_resolves_it_to_a_candidate():
    repo = InMemoryFeedbackRepository()
    processor = FeedbackProcessor(repo, RegexPrivacyFilter())
    queued = await repo.create(FeedbackSubmission(
        user_id="u1", text="I'm sleeping.",
        predicted_intent="SET_CONTEXT", predicted_context_mode="SLEEPING",
        intent_confidence=0.42, status=FeedbackStatus.NEEDS_REVIEW,
    ))

    # Equivalent to POST /feedback/{id}/respond {"correct": true, "consent_for_training": true}
    resolved = replace(
        queued, status=FeedbackStatus.RECEIVED, source=FeedbackSource.EXPLICIT,
        category=FeedbackCategory.CORRECT, consent_for_training=True,
    )
    await repo.update(resolved)

    final = await processor.process_one(resolved)
    assert final.status == FeedbackStatus.CANDIDATE
    assert final.confidence_weight == 1.0


async def test_user_correcting_a_review_item_carries_the_correction_through():
    repo = InMemoryFeedbackRepository()
    processor = FeedbackProcessor(repo, RegexPrivacyFilter())
    queued = await repo.create(FeedbackSubmission(
        user_id="u1", text="Not sleeping, in a meeting.",
        predicted_intent="SET_CONTEXT", predicted_context_mode="SLEEPING",
        intent_confidence=0.42, status=FeedbackStatus.NEEDS_REVIEW,
    ))

    resolved = replace(
        queued, status=FeedbackStatus.RECEIVED, source=FeedbackSource.EXPLICIT,
        category=FeedbackCategory.USER_CORRECTION, corrected_context_mode="MEETING",
        consent_for_training=True,
    )
    await repo.update(resolved)

    final = await processor.process_one(resolved)
    assert final.status == FeedbackStatus.CANDIDATE
    assert final.corrected_context_mode == "MEETING"
