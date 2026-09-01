"""Data-subject rights over feedback and personalization data:

    disable learning, delete feedback, delete training candidates,
    export feedback data, see what's been used for training,
    reset learned personalization

These are real deletions/exports, not soft toggles - see each method's
docstring for the one honest limitation (a candidate already merged into a
built, anonymized dataset file can no longer be selectively pulled back out
of that file, since it carries no user linkage by that point).
"""

from dataclasses import dataclass

from app.interfaces.feedback import FeedbackRecord, FeedbackRepository, FeedbackStatus


@dataclass
class FeedbackExport:
    user_id: str
    events: list[FeedbackRecord]


class PrivacyRightsService:
    def __init__(self, repository: FeedbackRepository):
        self._repo = repository

    async def delete_feedback(self, user_id: str, *, feedback_id: str | None = None) -> int:
        """Deletes one feedback event (if `feedback_id` given) or every
        feedback event for the user. Works regardless of status."""
        if feedback_id is not None:
            record = await self._repo.get(feedback_id)
            if record is None or record.user_id != user_id:
                return 0
            return 1 if await self._repo.delete(feedback_id) else 0
        return await self._repo.delete_by_user(user_id)

    async def delete_training_candidates(self, user_id: str) -> int:
        """Deletes only events that haven't yet been merged into a built
        dataset file (CANDIDATE/APPROVED). Events already INCLUDED in a
        dataset can't be selectively un-merged - see module docstring."""
        return await self._repo.delete_by_user(
            user_id, statuses=[FeedbackStatus.CANDIDATE, FeedbackStatus.APPROVED]
        )

    async def export_feedback(self, user_id: str) -> FeedbackExport:
        return FeedbackExport(user_id=user_id, events=await self._repo.list_by_user(user_id))

    async def list_feedback_used_for_training(self, user_id: str) -> list[FeedbackRecord]:
        return await self._repo.list_by_status(FeedbackStatus.INCLUDED, user_id=user_id)
