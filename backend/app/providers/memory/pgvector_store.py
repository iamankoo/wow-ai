"""Phase 1 reference MemoryStore implementation, backed by Postgres + pgvector.

When a query embedding is supplied, memories are ranked by cosine distance.
Without one (no embedding model wired up yet), it falls back to a simple
case-insensitive substring/recency search so the store is still useful before
an embedding model is plugged in.
"""

import uuid
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.interfaces.memory_store import MemoryRecord, MemoryStatus, MemoryStore, MemoryType
from app.models.memory import Memory


class PgVectorMemoryStore(MemoryStore):
    def __init__(self, session: AsyncSession):
        self._session = session

    async def add(
        self,
        *,
        user_id: str,
        content: str,
        contact_id: str | None = None,
        embedding: list[float] | None = None,
        source_type: str = "manual",
        source_id: str | None = None,
        memory_type: MemoryType = MemoryType.SEMANTIC,
        status: MemoryStatus = MemoryStatus.OBSERVED,
        confidence: float | None = None,
    ) -> str:
        memory = Memory(
            user_id=uuid.UUID(str(user_id)),
            contact_id=uuid.UUID(str(contact_id)) if contact_id else None,
            content=content,
            embedding=embedding,
            source_type=source_type,
            source_id=uuid.UUID(str(source_id)) if source_id else None,
            memory_type=memory_type,
            status=status,
            confidence=confidence,
        )
        self._session.add(memory)
        await self._session.flush()
        return str(memory.id)

    async def search(
        self,
        *,
        user_id: str,
        query: str,
        query_embedding: list[float] | None = None,
        top_k: int = 5,
        memory_type: MemoryType | None = None,
        include_deleted: bool = False,
    ) -> list[MemoryRecord]:
        stmt = select(Memory).where(Memory.user_id == uuid.UUID(str(user_id)))
        if not include_deleted:
            stmt = stmt.where(Memory.deleted_at.is_(None))
        if memory_type is not None:
            stmt = stmt.where(Memory.memory_type == memory_type)

        if query_embedding is not None:
            stmt = stmt.order_by(Memory.embedding.cosine_distance(query_embedding))
        else:
            if query:
                stmt = stmt.where(Memory.content.ilike(f"%{query}%"))
            stmt = stmt.order_by(Memory.created_at.desc())

        stmt = stmt.limit(top_k)
        result = await self._session.execute(stmt)
        rows = result.scalars().all()
        return [
            MemoryRecord(
                id=str(row.id),
                content=row.content,
                memory_type=row.memory_type,
                status=row.status,
                confidence=row.confidence,
                metadata={"source_type": row.source_type},
            )
            for row in rows
        ]

    async def delete(self, *, user_id: str, memory_id: str) -> bool:
        stmt = select(Memory).where(
            Memory.id == uuid.UUID(str(memory_id)),
            Memory.user_id == uuid.UUID(str(user_id)),
            Memory.deleted_at.is_(None),
        )
        result = await self._session.execute(stmt)
        row = result.scalars().first()
        if row is None:
            return False
        row.deleted_at = datetime.now(timezone.utc)
        await self._session.flush()
        return True

    async def approve(
        self, *, user_id: str, memory_id: str, status: MemoryStatus = MemoryStatus.USER_APPROVED
    ) -> bool:
        stmt = select(Memory).where(
            Memory.id == uuid.UUID(str(memory_id)),
            Memory.user_id == uuid.UUID(str(user_id)),
        )
        result = await self._session.execute(stmt)
        row = result.scalars().first()
        if row is None:
            return False
        row.status = status
        await self._session.flush()
        return True
