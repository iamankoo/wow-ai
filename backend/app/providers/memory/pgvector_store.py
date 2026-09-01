"""Phase 1 reference MemoryStore implementation, backed by Postgres + pgvector.

When a query embedding is supplied, memories are ranked by cosine distance.
Without one (no embedding model wired up yet), it falls back to a simple
case-insensitive substring/recency search so the store is still useful before
an embedding model is plugged in.
"""

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.interfaces.memory_store import MemoryRecord, MemoryStore
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
    ) -> str:
        memory = Memory(
            user_id=uuid.UUID(str(user_id)),
            contact_id=uuid.UUID(str(contact_id)) if contact_id else None,
            content=content,
            embedding=embedding,
            source_type=source_type,
            source_id=uuid.UUID(str(source_id)) if source_id else None,
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
    ) -> list[MemoryRecord]:
        stmt = select(Memory).where(Memory.user_id == uuid.UUID(str(user_id)))

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
                metadata={"source_type": row.source_type},
            )
            for row in rows
        ]
