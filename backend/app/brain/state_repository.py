"""Persistence for the brain's working state (AgentState table).

Kept as a tiny protocol-like abstract class, separate from the ORM, so unit
tests can swap in an in-memory implementation without a database.
"""

import uuid
from abc import ABC, abstractmethod

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.agent_state import AgentState


class StateRepository(ABC):
    @abstractmethod
    async def get(
        self, *, user_id: str, key: str, conversation_id: str | None = None
    ) -> dict | None: ...

    @abstractmethod
    async def set(
        self,
        *,
        user_id: str,
        key: str,
        value: dict,
        conversation_id: str | None = None,
    ) -> None: ...


class SqlStateRepository(StateRepository):
    def __init__(self, session: AsyncSession):
        self._session = session

    async def get(
        self, *, user_id: str, key: str, conversation_id: str | None = None
    ) -> dict | None:
        stmt = select(AgentState).where(
            AgentState.user_id == uuid.UUID(str(user_id)),
            AgentState.state_key == key,
        )
        if conversation_id is not None:
            stmt = stmt.where(
                AgentState.conversation_id == uuid.UUID(str(conversation_id))
            )
        result = await self._session.execute(stmt)
        row = result.scalars().first()
        return row.state_value if row else None

    async def set(
        self,
        *,
        user_id: str,
        key: str,
        value: dict,
        conversation_id: str | None = None,
    ) -> None:
        stmt = select(AgentState).where(
            AgentState.user_id == uuid.UUID(str(user_id)),
            AgentState.state_key == key,
        )
        if conversation_id is not None:
            stmt = stmt.where(
                AgentState.conversation_id == uuid.UUID(str(conversation_id))
            )
        result = await self._session.execute(stmt)
        row = result.scalars().first()
        if row:
            row.state_value = value
        else:
            row = AgentState(
                user_id=uuid.UUID(str(user_id)),
                conversation_id=uuid.UUID(str(conversation_id))
                if conversation_id
                else None,
                state_key=key,
                state_value=value,
            )
            self._session.add(row)
        await self._session.flush()


class InMemoryStateRepository(StateRepository):
    """Test/dev double - no database required."""

    def __init__(self):
        self._store: dict[tuple[str, str, str | None], dict] = {}

    async def get(
        self, *, user_id: str, key: str, conversation_id: str | None = None
    ) -> dict | None:
        return self._store.get((user_id, key, conversation_id))

    async def set(
        self,
        *,
        user_id: str,
        key: str,
        value: dict,
        conversation_id: str | None = None,
    ) -> None:
        self._store[(user_id, key, conversation_id)] = value
