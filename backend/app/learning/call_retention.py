"""Call/transcript retention (see docs "Privacy" / "Call recording -
retention"): how long a COMPLETED call's history stays in the database
before scheduled cleanup removes it. Distinct from
`app/learning/retention.py`'s `RetentionPolicy`, which governs
feedback-event eligibility for *training*, not call data itself.

Only ever touches COMPLETED calls - an ACTIVE/RINGING/MISSED/VOICEMAIL
call is never cleaned up regardless of age, since "expired" only makes
sense once a call has actually finished.
"""

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.agent_state import AgentState
from app.models.call import Call, CallStatus
from app.models.conversation import Conversation
from app.models.summary import Summary
from app.models.transcript import TranscriptSegment


@dataclass
class CallRetentionPolicy:
    max_age_days: int = 15

    def is_expired(self, ended_at: datetime, *, now: datetime | None = None) -> bool:
        now = now or datetime.now(timezone.utc)
        if ended_at.tzinfo is None:
            ended_at = ended_at.replace(tzinfo=timezone.utc)
        return now - ended_at > timedelta(days=self.max_age_days)


async def cleanup_expired_calls(
    session: AsyncSession,
    policy: CallRetentionPolicy | None = None,
    *,
    now: datetime | None = None,
) -> int:
    """Deletes every COMPLETED call whose `ended_at` is older than the
    retention window, along with its conversation(s), transcript segments,
    summary, and working agent state. No `ON DELETE CASCADE` exists at the
    DB level (see README "No Alembic migrations yet"), so child rows are
    deleted explicitly, in dependency order, before their parents. Returns
    the number of calls deleted. Does not commit - the caller controls the
    transaction, same as every other repository in this codebase.
    """
    policy = policy or CallRetentionPolicy()
    now = now or datetime.now(timezone.utc)
    cutoff = now - timedelta(days=policy.max_age_days)

    stmt = select(Call).where(Call.status == CallStatus.COMPLETED, Call.ended_at < cutoff)
    result = await session.execute(stmt)
    expired_calls = list(result.scalars().all())
    if not expired_calls:
        return 0

    call_ids = [c.id for c in expired_calls]
    conv_stmt = select(Conversation.id).where(Conversation.call_id.in_(call_ids))
    conversation_ids = list((await session.execute(conv_stmt)).scalars().all())

    if conversation_ids:
        await session.execute(
            delete(TranscriptSegment).where(TranscriptSegment.conversation_id.in_(conversation_ids))
        )
        await session.execute(delete(Summary).where(Summary.conversation_id.in_(conversation_ids)))
        await session.execute(delete(AgentState).where(AgentState.conversation_id.in_(conversation_ids)))
        await session.execute(delete(Conversation).where(Conversation.id.in_(conversation_ids)))

    await session.execute(delete(Call).where(Call.id.in_(call_ids)))
    await session.flush()
    return len(expired_calls)
