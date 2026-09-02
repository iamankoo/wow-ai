"""Persistence for conversation summaries, used by the `create_summary`
agent tool. Mirrors the StateRepository pattern (ABC + SQL + in-memory test
double) used throughout `app.brain`.
"""

import uuid
from abc import ABC, abstractmethod

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.summary import Summary


class SummaryRepository(ABC):
    @abstractmethod
    async def upsert(
        self,
        *,
        conversation_id: str,
        summary_text: str,
        key_points: list[str] | None = None,
        action_items: list[str] | None = None,
    ) -> str:
        """Create or replace the summary for a conversation, return its id."""


class SqlSummaryRepository(SummaryRepository):
    def __init__(self, session: AsyncSession):
        self._session = session

    async def upsert(
        self,
        *,
        conversation_id: str,
        summary_text: str,
        key_points: list[str] | None = None,
        action_items: list[str] | None = None,
    ) -> str:
        stmt = select(Summary).where(
            Summary.conversation_id == uuid.UUID(str(conversation_id))
        )
        result = await self._session.execute(stmt)
        row = result.scalars().first()
        if row:
            row.summary_text = summary_text
            row.key_points = key_points or []
            row.action_items = action_items or []
        else:
            row = Summary(
                conversation_id=uuid.UUID(str(conversation_id)),
                summary_text=summary_text,
                key_points=key_points or [],
                action_items=action_items or [],
            )
            self._session.add(row)
        await self._session.flush()
        return str(row.id)


class InMemorySummaryRepository(SummaryRepository):
    """Test/dev double - no database required."""

    def __init__(self):
        self._store: dict[str, dict] = {}

    async def upsert(
        self,
        *,
        conversation_id: str,
        summary_text: str,
        key_points: list[str] | None = None,
        action_items: list[str] | None = None,
    ) -> str:
        self._store[conversation_id] = {
            "summary_text": summary_text,
            "key_points": key_points or [],
            "action_items": action_items or [],
        }
        return conversation_id
