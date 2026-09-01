"""Feedback / self-learning API - see docs/SELF_LEARNING.md.

Every route here operates on FeedbackEvent via the FeedbackRepository/
FeedbackProcessor abstractions (never raw SQL), so the same logic this API
exercises is what training/tests/... and backend/tests/... test directly
without a database.
"""

from dataclasses import replace

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db
from app.interfaces.feedback import (
    FeedbackCategory,
    FeedbackSource,
    FeedbackStatus,
    FeedbackSubmission,
)
from app.learning import personalization
from app.learning.feedback_processor import FeedbackProcessor
from app.learning.feedback_repository import SqlFeedbackRepository
from app.learning.privacy_filter import RegexPrivacyFilter
from app.learning.privacy_rights import PrivacyRightsService
from app.schemas.feedback import (
    ConsentUpdateRequest,
    FeedbackApproveRequest,
    FeedbackRead,
    FeedbackRespondRequest,
    FeedbackSubmitRequest,
)

router = APIRouter(prefix="/feedback", tags=["feedback"])


def _processor(session: AsyncSession) -> FeedbackProcessor:
    return FeedbackProcessor(SqlFeedbackRepository(session), RegexPrivacyFilter())


def _to_read(record) -> FeedbackRead:
    return FeedbackRead(
        id=record.id,
        status=record.status,
        predicted_intent=record.predicted_intent,
        corrected_intent=record.corrected_intent,
        consent_for_training=record.consent_for_training,
        confidence_weight=record.confidence_weight,
    )


@router.post("", response_model=FeedbackRead, status_code=201)
async def submit_feedback(
    payload: FeedbackSubmitRequest, session: AsyncSession = Depends(get_db)
) -> FeedbackRead:
    repo = SqlFeedbackRepository(session)
    record = await repo.create(FeedbackSubmission(
        user_id=payload.user_id,
        text=payload.text,
        predicted_intent=payload.predicted_intent,
        predicted_context_mode=payload.predicted_context_mode,
        predicted_action=payload.predicted_action,
        intent_confidence=payload.intent_confidence,
        context_confidence=payload.context_confidence,
        action_confidence=payload.action_confidence,
        model_version=payload.model_version,
        conversation_id=payload.conversation_id,
        language=payload.language,
        source=payload.source,
        category=payload.category,
        implicit_signal_type=payload.implicit_signal_type,
        corrected_intent=payload.corrected_intent,
        corrected_context_mode=payload.corrected_context_mode,
        corrected_action=payload.corrected_action,
        corrected_caller_name=payload.corrected_caller_name,
        consent_for_training=payload.consent_for_training,
        status=FeedbackStatus.RECEIVED,
    ))
    updated = await _processor(session).process_one(record)
    await session.commit()
    return _to_read(updated)


@router.get("/review-queue", response_model=list[FeedbackRead])
async def list_review_queue(user_id: str, session: AsyncSession = Depends(get_db)) -> list[FeedbackRead]:
    repo = SqlFeedbackRepository(session)
    records = await repo.list_by_status(FeedbackStatus.NEEDS_REVIEW, user_id=user_id)
    return [_to_read(r) for r in records]


@router.post("/{feedback_id}/respond", response_model=FeedbackRead)
async def respond_to_review_item(
    feedback_id: str, payload: FeedbackRespondRequest, session: AsyncSession = Depends(get_db)
) -> FeedbackRead:
    """Resolves a NEEDS_REVIEW (active-learning) item into explicit
    feedback, then runs it through the same privacy pipeline as any other
    submission."""
    repo = SqlFeedbackRepository(session)
    record = await repo.get(feedback_id)
    if record is None:
        raise HTTPException(404, f"No feedback event {feedback_id}")
    if record.status != FeedbackStatus.NEEDS_REVIEW:
        raise HTTPException(409, f"Feedback event {feedback_id} is not awaiting review (status={record.status.value})")

    category = FeedbackCategory.CORRECT if payload.correct else FeedbackCategory.USER_CORRECTION
    updated = replace(
        record,
        status=FeedbackStatus.RECEIVED,
        source=FeedbackSource.EXPLICIT,
        category=category,
        corrected_intent=payload.corrected_intent,
        corrected_context_mode=payload.corrected_context_mode,
        corrected_action=payload.corrected_action,
        consent_for_training=payload.consent_for_training,
    )
    await repo.update(updated)
    final = await _processor(session).process_one(updated)
    await session.commit()
    return _to_read(final)


@router.post("/{feedback_id}/approve", response_model=FeedbackRead)
async def approve_feedback(
    feedback_id: str, payload: FeedbackApproveRequest, session: AsyncSession = Depends(get_db)
) -> FeedbackRead:
    try:
        record = await _processor(session).approve(feedback_id, reviewed_by=payload.reviewed_by)
    except ValueError as e:
        raise HTTPException(400, str(e)) from e
    await session.commit()
    return _to_read(record)


@router.delete("")
async def delete_feedback(
    user_id: str, feedback_id: str | None = None, session: AsyncSession = Depends(get_db)
) -> dict:
    deleted = await PrivacyRightsService(SqlFeedbackRepository(session)).delete_feedback(
        user_id, feedback_id=feedback_id
    )
    await session.commit()
    return {"deleted": deleted}


@router.delete("/candidates")
async def delete_training_candidates(user_id: str, session: AsyncSession = Depends(get_db)) -> dict:
    deleted = await PrivacyRightsService(SqlFeedbackRepository(session)).delete_training_candidates(user_id)
    await session.commit()
    return {"deleted": deleted}


@router.get("/export", response_model=list[FeedbackRead])
async def export_feedback(user_id: str, session: AsyncSession = Depends(get_db)) -> list[FeedbackRead]:
    export = await PrivacyRightsService(SqlFeedbackRepository(session)).export_feedback(user_id)
    return [_to_read(r) for r in export.events]


@router.get("/used-for-training", response_model=list[FeedbackRead])
async def list_used_for_training(user_id: str, session: AsyncSession = Depends(get_db)) -> list[FeedbackRead]:
    records = await PrivacyRightsService(SqlFeedbackRepository(session)).list_feedback_used_for_training(user_id)
    return [_to_read(r) for r in records]


@router.put("/consent")
async def update_training_consent(
    user_id: str, payload: ConsentUpdateRequest, session: AsyncSession = Depends(get_db)
) -> dict:
    try:
        await personalization.set_training_data_consent(session, user_id, payload.consent)
    except ValueError as e:
        raise HTTPException(404, str(e)) from e
    await session.commit()
    return {"user_id": user_id, "training_data_consent": payload.consent}


@router.post("/reset-personalization")
async def reset_personalization(user_id: str, session: AsyncSession = Depends(get_db)) -> dict:
    deleted = await personalization.reset_personalization(session, user_id)
    await session.commit()
    return {"memories_deleted": deleted}
