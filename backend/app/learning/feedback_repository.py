"""Persistence for FeedbackEvent, behind the FeedbackRepository interface -
same split as app/brain/state_repository.py: a Sql* implementation for
real use, an InMemory* implementation so the learning pipeline's tests
never need a database.
"""

import uuid
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.interfaces.feedback import (
    FeedbackRecord,
    FeedbackRepository,
    FeedbackStatus,
    FeedbackSubmission,
)
from app.models.feedback import FeedbackEvent


def _to_record(row: FeedbackEvent) -> FeedbackRecord:
    return FeedbackRecord(
        id=str(row.id),
        user_id=str(row.user_id),
        conversation_id=str(row.conversation_id) if row.conversation_id else None,
        raw_text=row.raw_text,
        redacted_text=row.redacted_text,
        language=row.language,
        predicted_intent=row.predicted_intent,
        predicted_context_mode=row.predicted_context_mode,
        predicted_action=row.predicted_action,
        intent_confidence=row.intent_confidence,
        context_confidence=row.context_confidence,
        action_confidence=row.action_confidence,
        model_version=row.model_version,
        source=row.source,
        category=row.category,
        implicit_signal_type=row.implicit_signal_type,
        confidence_weight=row.confidence_weight,
        corrected_intent=row.corrected_intent,
        corrected_context_mode=row.corrected_context_mode,
        corrected_action=row.corrected_action,
        corrected_caller_name=row.corrected_caller_name,
        consent_for_training=row.consent_for_training,
        status=row.status,
        rejection_reason=row.rejection_reason,
        candidate_dataset_batch=row.candidate_dataset_batch,
        created_at=row.created_at,
    )


def _apply_submission(row: FeedbackEvent, submission: FeedbackSubmission) -> None:
    row.user_id = uuid.UUID(str(submission.user_id))
    row.conversation_id = uuid.UUID(str(submission.conversation_id)) if submission.conversation_id else None
    row.raw_text = submission.text
    row.language = submission.language
    row.predicted_intent = submission.predicted_intent
    row.predicted_context_mode = submission.predicted_context_mode
    row.predicted_action = submission.predicted_action
    row.intent_confidence = submission.intent_confidence
    row.context_confidence = submission.context_confidence
    row.action_confidence = submission.action_confidence
    row.model_version = submission.model_version
    row.source = submission.source
    row.category = submission.category
    row.implicit_signal_type = submission.implicit_signal_type
    row.corrected_intent = submission.corrected_intent
    row.corrected_context_mode = submission.corrected_context_mode
    row.corrected_action = submission.corrected_action
    row.corrected_caller_name = submission.corrected_caller_name
    row.consent_for_training = submission.consent_for_training
    row.status = submission.status


class SqlFeedbackRepository(FeedbackRepository):
    def __init__(self, session: AsyncSession):
        self._session = session

    async def create(self, submission: FeedbackSubmission) -> FeedbackRecord:
        row = FeedbackEvent(raw_text=submission.text, user_id=uuid.UUID(str(submission.user_id)))
        _apply_submission(row, submission)
        self._session.add(row)
        await self._session.flush()
        return _to_record(row)

    async def get(self, feedback_id: str) -> FeedbackRecord | None:
        row = await self._session.get(FeedbackEvent, uuid.UUID(str(feedback_id)))
        return _to_record(row) if row else None

    async def list_by_status(self, status: FeedbackStatus, *, user_id: str | None = None) -> list[FeedbackRecord]:
        stmt = select(FeedbackEvent).where(FeedbackEvent.status == status)
        if user_id is not None:
            stmt = stmt.where(FeedbackEvent.user_id == uuid.UUID(str(user_id)))
        result = await self._session.execute(stmt)
        return [_to_record(r) for r in result.scalars().all()]

    async def list_by_user(self, user_id: str) -> list[FeedbackRecord]:
        stmt = select(FeedbackEvent).where(FeedbackEvent.user_id == uuid.UUID(str(user_id)))
        result = await self._session.execute(stmt)
        return [_to_record(r) for r in result.scalars().all()]

    async def update(self, record: FeedbackRecord) -> None:
        row = await self._session.get(FeedbackEvent, uuid.UUID(str(record.id)))
        if row is None:
            raise ValueError(f"No feedback event with id {record.id}")
        row.redacted_text = record.redacted_text
        row.status = record.status
        row.rejection_reason = record.rejection_reason
        row.candidate_dataset_batch = record.candidate_dataset_batch
        row.confidence_weight = record.confidence_weight
        row.corrected_intent = record.corrected_intent
        row.corrected_context_mode = record.corrected_context_mode
        row.corrected_action = record.corrected_action
        row.corrected_caller_name = record.corrected_caller_name
        row.source = record.source
        row.category = record.category
        row.implicit_signal_type = record.implicit_signal_type
        row.consent_for_training = record.consent_for_training
        await self._session.flush()

    async def delete(self, feedback_id: str) -> bool:
        row = await self._session.get(FeedbackEvent, uuid.UUID(str(feedback_id)))
        if row is None:
            return False
        await self._session.delete(row)
        await self._session.flush()
        return True

    async def delete_by_user(self, user_id: str, *, statuses: list[FeedbackStatus] | None = None) -> int:
        stmt = select(FeedbackEvent).where(FeedbackEvent.user_id == uuid.UUID(str(user_id)))
        if statuses is not None:
            stmt = stmt.where(FeedbackEvent.status.in_(statuses))
        result = await self._session.execute(stmt)
        rows = list(result.scalars().all())
        for row in rows:
            await self._session.delete(row)
        await self._session.flush()
        return len(rows)


class InMemoryFeedbackRepository(FeedbackRepository):
    """Test/dev double - no database required."""

    def __init__(self):
        self._store: dict[str, FeedbackRecord] = {}

    async def create(self, submission: FeedbackSubmission) -> FeedbackRecord:
        record = FeedbackRecord(
            id=str(uuid.uuid4()),
            user_id=submission.user_id,
            conversation_id=submission.conversation_id,
            raw_text=submission.text,
            language=submission.language,
            predicted_intent=submission.predicted_intent,
            predicted_context_mode=submission.predicted_context_mode,
            predicted_action=submission.predicted_action,
            intent_confidence=submission.intent_confidence,
            context_confidence=submission.context_confidence,
            action_confidence=submission.action_confidence,
            model_version=submission.model_version,
            source=submission.source,
            category=submission.category,
            implicit_signal_type=submission.implicit_signal_type,
            corrected_intent=submission.corrected_intent,
            corrected_context_mode=submission.corrected_context_mode,
            corrected_action=submission.corrected_action,
            corrected_caller_name=submission.corrected_caller_name,
            consent_for_training=submission.consent_for_training,
            status=submission.status,
            created_at=datetime.now(timezone.utc),
        )
        self._store[record.id] = record
        return record

    async def get(self, feedback_id: str) -> FeedbackRecord | None:
        return self._store.get(feedback_id)

    async def list_by_status(self, status: FeedbackStatus, *, user_id: str | None = None) -> list[FeedbackRecord]:
        return [
            r for r in self._store.values()
            if r.status == status and (user_id is None or r.user_id == user_id)
        ]

    async def list_by_user(self, user_id: str) -> list[FeedbackRecord]:
        return [r for r in self._store.values() if r.user_id == user_id]

    async def update(self, record: FeedbackRecord) -> None:
        if record.id not in self._store:
            raise ValueError(f"No feedback event with id {record.id}")
        self._store[record.id] = record

    async def delete(self, feedback_id: str) -> bool:
        return self._store.pop(feedback_id, None) is not None

    async def delete_by_user(self, user_id: str, *, statuses: list[FeedbackStatus] | None = None) -> int:
        to_delete = [
            fid for fid, r in self._store.items()
            if r.user_id == user_id and (statuses is None or r.status in statuses)
        ]
        for fid in to_delete:
            del self._store[fid]
        return len(to_delete)
