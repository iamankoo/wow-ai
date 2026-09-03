"""Phase 6 Part M - real call history. Reads only, from the same
Call/Conversation/TranscriptSegment/Summary rows CallRecorder already
writes during an actual handled call (Block 5/6/7's media pipeline, and
app/agent/call_recorder.py) - no second/local call-history store, no
hardcoded fake data.
"""

import uuid
from datetime import date, datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db
from app.models.call import Call
from app.models.contact import Contact
from app.models.conversation import Conversation
from app.models.summary import Summary
from app.models.transcript import TranscriptSegment
from app.schemas.calls import (
    CallDetail,
    CallListItem,
    CallsTodaySummary,
    SummaryRead,
    TranscriptSegmentRead,
)

router = APIRouter(tags=["calls"])


async def _call_list_items(calls: list[Call], session: AsyncSession) -> list[CallListItem]:
    if not calls:
        return []
    call_ids = [c.id for c in calls]
    contact_ids = [c.contact_id for c in calls if c.contact_id is not None]

    names_by_contact: dict = {}
    if contact_ids:
        result = await session.execute(select(Contact).where(Contact.id.in_(contact_ids)))
        names_by_contact = {c.id: c.name for c in result.scalars().all()}

    convo_result = await session.execute(select(Conversation).where(Conversation.call_id.in_(call_ids)))
    conversations = convo_result.scalars().all()
    convo_ids = [c.id for c in conversations]
    call_id_by_convo = {c.id: c.call_id for c in conversations}

    summarized_call_ids: set = set()
    if convo_ids:
        summary_result = await session.execute(
            select(Summary.conversation_id).where(Summary.conversation_id.in_(convo_ids))
        )
        for convo_id in summary_result.scalars().all():
            call_id = call_id_by_convo.get(convo_id)
            if call_id is not None:
                summarized_call_ids.add(call_id)

    items = []
    for call in calls:
        items.append(
            CallListItem(
                id=call.id,
                caller_number=call.caller_number,
                caller_name=names_by_contact.get(call.contact_id),
                direction=call.direction,
                status=call.status,
                started_at=call.started_at,
                ended_at=call.ended_at,
                has_summary=call.id in summarized_call_ids,
            )
        )
    return items


@router.get("/users/{user_id}/calls", response_model=list[CallListItem])
async def list_calls(
    user_id: str, limit: int = 50, session: AsyncSession = Depends(get_db)
) -> list[CallListItem]:
    stmt = (
        select(Call)
        .where(Call.user_id == user_id)
        .order_by(Call.created_at.desc())
        .limit(limit)
    )
    calls = (await session.execute(stmt)).scalars().all()
    return await _call_list_items(list(calls), session)


@router.get("/users/{user_id}/calls/today-summary", response_model=CallsTodaySummary)
async def calls_today_summary(
    user_id: str, session: AsyncSession = Depends(get_db)
) -> CallsTodaySummary:
    today_start = datetime.combine(date.today(), datetime.min.time(), tzinfo=timezone.utc)
    stmt = select(Call).where(Call.user_id == user_id, Call.created_at >= today_start)
    calls = (await session.execute(stmt)).scalars().all()

    total_seconds = 0
    for call in calls:
        if call.started_at is not None and call.ended_at is not None:
            total_seconds += int((call.ended_at - call.started_at).total_seconds())

    return CallsTodaySummary(
        calls_handled=len(calls),
        unique_callers=len({c.caller_number for c in calls}),
        total_seconds=total_seconds,
    )


@router.get("/calls/{call_id}", response_model=CallDetail)
async def get_call(call_id: str, session: AsyncSession = Depends(get_db)) -> CallDetail:
    try:
        call = await session.get(Call, uuid.UUID(call_id))
    except ValueError:
        call = None
    if call is None:
        raise HTTPException(status_code=404, detail="Call not found")

    [item] = await _call_list_items([call], session)

    convo_result = await session.execute(
        select(Conversation).where(Conversation.call_id == call.id).order_by(Conversation.created_at.desc())
    )
    conversation = convo_result.scalars().first()

    transcript: list[TranscriptSegmentRead] = []
    summary: SummaryRead | None = None
    if conversation is not None:
        seg_result = await session.execute(
            select(TranscriptSegment)
            .where(TranscriptSegment.conversation_id == conversation.id)
            .order_by(TranscriptSegment.created_at.asc())
        )
        transcript = [TranscriptSegmentRead.model_validate(s) for s in seg_result.scalars().all()]

        summary_result = await session.execute(
            select(Summary).where(Summary.conversation_id == conversation.id)
        )
        summary_row = summary_result.scalars().first()
        if summary_row is not None:
            summary = SummaryRead.model_validate(summary_row)

    return CallDetail(**item.model_dump(), transcript=transcript, summary=summary)
