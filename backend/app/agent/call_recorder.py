"""Persists a call's lifecycle into the domain tables (docs "Call
lifecycle" / "Call recording / transcript"): `Call`, `Conversation`,
`TranscriptSegment`, `Summary`. Optional by design - `WowAgent` and
`app/simulation/call_simulator.run_simulated_call` work identically with
or without one; a `CallRecorder` is what turns a call's history into
something durable in Postgres rather than living only in
`ConversationState` (which is scoped to the agent's working state, not
call history/reporting).
"""

import uuid
from datetime import datetime, timezone

from sqlalchemy.ext.asyncio import AsyncSession

from app.agent.summary_repository import SummaryRepository
from app.models.call import Call, CallDirection, CallStatus
from app.models.conversation import Conversation, ConversationStatus
from app.models.transcript import Speaker, TranscriptSegment


class CallRecorder:
    def __init__(self, session: AsyncSession, summary_repository: SummaryRepository | None = None):
        self._session = session
        self._summary_repo = summary_repository

    async def start_call(
        self,
        *,
        user_id: str,
        caller_number: str | None,
        direction: CallDirection,
        contact_id: str | None = None,
    ) -> tuple[Call, Conversation]:
        now = datetime.now(timezone.utc)
        call = Call(
            user_id=uuid.UUID(str(user_id)),
            contact_id=uuid.UUID(str(contact_id)) if contact_id else None,
            caller_number=caller_number or "unknown",
            direction=direction,
            status=CallStatus.ACTIVE,
            started_at=now,
        )
        self._session.add(call)
        await self._session.flush()

        conversation = Conversation(
            user_id=uuid.UUID(str(user_id)),
            call_id=call.id,
            status=ConversationStatus.ACTIVE,
            started_at=now,
        )
        self._session.add(conversation)
        await self._session.flush()
        return call, conversation

    async def record_turn(self, *, conversation_id: str, speaker: Speaker, text: str) -> None:
        segment = TranscriptSegment(
            conversation_id=uuid.UUID(str(conversation_id)),
            speaker=speaker,
            text=text,
        )
        self._session.add(segment)
        await self._session.flush()

    async def end_call(
        self,
        *,
        call: Call,
        conversation: Conversation,
        summary_text: str | None = None,
    ) -> None:
        now = datetime.now(timezone.utc)
        call.status = CallStatus.COMPLETED
        call.ended_at = now
        conversation.status = ConversationStatus.COMPLETED
        conversation.ended_at = now
        await self._session.flush()

        if summary_text is not None and self._summary_repo is not None:
            await self._summary_repo.upsert(
                conversation_id=str(conversation.id), summary_text=summary_text
            )
