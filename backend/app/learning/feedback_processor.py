"""The privacy pipeline: RECEIVED -> (REJECTED | CANDIDATE).

    Raw event -> consent check -> retention check -> PII detect/redact
        -> CANDIDATE (never further, without a human)

This is the mandatory gate between "a user said something" and "this text
could ever become training data." Nothing here writes to a dataset file -
that only happens after a human calls approve() (CANDIDATE -> APPROVED) and
then TrainingCandidateBuilder runs (APPROVED -> INCLUDED). See
docs/SELF_LEARNING.md "Privacy pipeline" for the full contract.

Personalization vs. model training (docs/SELF_LEARNING.md section 5): this
processor is exclusively for signals destined for the *global* model
training loop. A caller-side preference like "treat family calls as
high-priority" is personalization, not training data - it belongs in
MemoryStore/ContextProfile directly, never in FeedbackEvent.
"""

from dataclasses import replace

from app.interfaces.feedback import FeedbackRecord, FeedbackRepository, FeedbackStatus
from app.interfaces.feedback import PrivacyFilter
from app.learning.confidence import confidence_weight
from app.learning.retention import RetentionPolicy


class FeedbackProcessor:
    def __init__(
        self,
        repository: FeedbackRepository,
        privacy_filter: PrivacyFilter,
        retention_policy: RetentionPolicy | None = None,
    ):
        self._repo = repository
        self._filter = privacy_filter
        self._retention = retention_policy or RetentionPolicy()

    async def process_one(self, record: FeedbackRecord) -> FeedbackRecord:
        """Runs the full pipeline for one RECEIVED record, persists the
        result, and returns the updated record. No-op (returns unchanged)
        for a record that isn't in RECEIVED status."""
        if record.status != FeedbackStatus.RECEIVED:
            return record

        if not record.consent_for_training:
            updated = replace(record, status=FeedbackStatus.REJECTED, rejection_reason="consent_not_given")
            await self._repo.update(updated)
            return updated

        if self._retention.is_expired(record.created_at):
            updated = replace(record, status=FeedbackStatus.REJECTED, rejection_reason="retention_expired")
            await self._repo.update(updated)
            return updated

        weight = confidence_weight(record.source, record.category, record.implicit_signal_type)

        redaction = self._filter.redact(record.raw_text)
        updated = replace(
            record,
            status=FeedbackStatus.CANDIDATE,
            redacted_text=redaction.redacted_text,
            confidence_weight=weight,
        )
        await self._repo.update(updated)
        return updated

    async def process_pending(self, *, user_id: str | None = None) -> list[FeedbackRecord]:
        pending = await self._repo.list_by_status(FeedbackStatus.RECEIVED, user_id=user_id)
        return [await self.process_one(r) for r in pending]

    async def approve(self, feedback_id: str, *, reviewed_by: str) -> FeedbackRecord:
        """The explicit-authorization gate: a CANDIDATE record only ever
        becomes eligible for dataset inclusion when a human (identified by
        `reviewed_by`, for the audit trail) calls this. Never automatic."""
        if not reviewed_by:
            raise ValueError("reviewed_by is required - approval must be attributable to a person.")
        record = await self._repo.get(feedback_id)
        if record is None:
            raise ValueError(f"No feedback event with id {feedback_id}")
        if record.status != FeedbackStatus.CANDIDATE:
            raise ValueError(
                f"Feedback event {feedback_id} is in status {record.status.value}, not CANDIDATE - "
                "only candidates that passed the privacy pipeline can be approved."
            )
        updated = replace(record, status=FeedbackStatus.APPROVED)
        await self._repo.update(updated)
        return updated

    async def reject(self, feedback_id: str, *, reason: str) -> FeedbackRecord:
        record = await self._repo.get(feedback_id)
        if record is None:
            raise ValueError(f"No feedback event with id {feedback_id}")
        updated = replace(record, status=FeedbackStatus.REJECTED, rejection_reason=reason)
        await self._repo.update(updated)
        return updated
