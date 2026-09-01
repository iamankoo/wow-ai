import json

import pytest

from app.interfaces.feedback import (
    FeedbackCategory,
    FeedbackSource,
    FeedbackStatus,
    FeedbackSubmission,
)
from app.learning.candidate_builder import TrainingCandidateBuilder
from app.learning.feedback_repository import InMemoryFeedbackRepository


@pytest.fixture
def repo() -> InMemoryFeedbackRepository:
    return InMemoryFeedbackRepository()


async def _approved(repo, **kw) -> str:
    record = await repo.create(FeedbackSubmission(user_id="u1", text="raw text", **kw))
    record.redacted_text = kw.get("text", "raw text")
    record.status = FeedbackStatus.APPROVED
    await repo.update(record)
    return record.id


async def test_confirmed_correct_prediction_becomes_a_candidate(repo, tmp_path):
    await _approved(
        repo, predicted_intent="URGENT_CALL", predicted_context_mode=None, predicted_action="MARK_URGENT",
        source=FeedbackSource.EXPLICIT, category=FeedbackCategory.CORRECT,
    )
    builder = TrainingCandidateBuilder(repo, tmp_path)
    result = await builder.build("batch1")

    assert result.included_count == 1
    lines = result.output_path.read_text(encoding="utf-8").splitlines()
    example = json.loads(lines[0])
    assert example["intent"] == "URGENT_CALL"
    assert example["action"] == "MARK_URGENT"


async def test_correction_overrides_only_the_corrected_field(repo, tmp_path):
    await _approved(
        repo, predicted_intent="SET_CONTEXT", predicted_context_mode="SLEEPING", predicted_action="SET_CONTEXT",
        corrected_context_mode="MEETING",
        source=FeedbackSource.EXPLICIT, category=FeedbackCategory.WRONG_CONTEXT,
    )
    builder = TrainingCandidateBuilder(repo, tmp_path)
    result = await builder.build("batch1")

    example = json.loads(result.output_path.read_text(encoding="utf-8").splitlines()[0])
    assert example["intent"] == "SET_CONTEXT"  # unchanged, not corrected
    assert example["context_mode"] == "MEETING"  # corrected


async def test_negative_feedback_with_no_correction_is_skipped(repo, tmp_path):
    await _approved(
        repo, predicted_intent="GENERAL_CONVERSATION",
        source=FeedbackSource.EXPLICIT, category=FeedbackCategory.INCORRECT,
    )
    builder = TrainingCandidateBuilder(repo, tmp_path)
    result = await builder.build("batch1")

    assert result.included_count == 0
    assert result.skipped_reasons.get("no_ground_truth_label") == 1


async def test_invalid_corrected_intent_is_skipped(repo, tmp_path):
    await _approved(
        repo, predicted_intent="CALL_PERSON", corrected_intent="NOT_A_REAL_INTENT",
        source=FeedbackSource.EXPLICIT, category=FeedbackCategory.WRONG_INTENT,
    )
    builder = TrainingCandidateBuilder(repo, tmp_path)
    result = await builder.build("batch1")

    assert result.included_count == 0
    assert result.skipped_reasons.get("invalid_intent") == 1


async def test_only_approved_records_are_considered(repo, tmp_path):
    await repo.create(FeedbackSubmission(
        user_id="u1", text="pending", predicted_intent="CALL_PERSON",
        source=FeedbackSource.EXPLICIT, category=FeedbackCategory.CORRECT,
        status=FeedbackStatus.CANDIDATE,  # not approved
    ))
    builder = TrainingCandidateBuilder(repo, tmp_path)
    result = await builder.build("batch1")
    assert result.included_count == 0


async def test_included_records_are_marked_included_with_batch_name(repo, tmp_path):
    feedback_id = await _approved(
        repo, predicted_intent="CALL_PERSON",
        source=FeedbackSource.EXPLICIT, category=FeedbackCategory.CORRECT,
    )
    builder = TrainingCandidateBuilder(repo, tmp_path)
    await builder.build("batch-2024-01")

    updated = await repo.get(feedback_id)
    assert updated.status == FeedbackStatus.INCLUDED
    assert updated.candidate_dataset_batch == "batch-2024-01"
