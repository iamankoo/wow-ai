"""Memory API - see docs/ARCHITECTURE.md "Memory system" / "Memory safety".

Every route operates through the MemoryStore interface (never raw SQL
against the Memory table directly), so this is a thin wrapper over the same
abstraction WowAgent's save_memory tool uses.
"""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db
from app.interfaces.memory_store import MemoryType
from app.providers.memory.pgvector_store import PgVectorMemoryStore
from app.schemas.memory import MemoryApproveRequest, MemoryCreateRequest, MemoryRead

router = APIRouter(prefix="/memories", tags=["memories"])


def _to_read(record) -> MemoryRead:
    return MemoryRead(
        id=record.id,
        content=record.content,
        memory_type=record.memory_type,
        status=record.status,
        confidence=record.confidence,
    )


@router.post("", response_model=MemoryRead, status_code=201)
async def create_memory(
    payload: MemoryCreateRequest, session: AsyncSession = Depends(get_db)
) -> MemoryRead:
    store = PgVectorMemoryStore(session)
    memory_id = await store.add(
        user_id=payload.user_id,
        content=payload.content,
        contact_id=payload.contact_id,
        memory_type=payload.memory_type,
        status=payload.status,
        confidence=payload.confidence,
    )
    await session.commit()
    return MemoryRead(
        id=memory_id,
        content=payload.content,
        memory_type=payload.memory_type,
        status=payload.status,
        confidence=payload.confidence,
    )


@router.get("", response_model=list[MemoryRead])
async def list_memories(
    user_id: str,
    memory_type: MemoryType | None = None,
    top_k: int = 20,
    session: AsyncSession = Depends(get_db),
) -> list[MemoryRead]:
    store = PgVectorMemoryStore(session)
    records = await store.search(
        user_id=user_id, query="", top_k=top_k, memory_type=memory_type
    )
    return [_to_read(r) for r in records]


@router.delete("/{memory_id}")
async def delete_memory(
    memory_id: str, user_id: str, session: AsyncSession = Depends(get_db)
) -> dict:
    """User-initiated memory deletion (docs "Memory safety": a user must be
    able to remove stored memories). Soft-delete - see Memory.deleted_at."""
    store = PgVectorMemoryStore(session)
    deleted = await store.delete(user_id=user_id, memory_id=memory_id)
    await session.commit()
    return {"deleted": deleted}


@router.post("/{memory_id}/approve", response_model=dict)
async def approve_memory(
    memory_id: str, payload: MemoryApproveRequest, session: AsyncSession = Depends(get_db)
) -> dict:
    """Explicit user confirmation that a stored memory is correct - the
    trust-tier promotion path from docs "Memory safety"."""
    store = PgVectorMemoryStore(session)
    approved = await store.approve(
        user_id=payload.user_id, memory_id=memory_id, status=payload.status
    )
    if not approved:
        raise HTTPException(404, f"No memory {memory_id} for user {payload.user_id}")
    await session.commit()
    return {"approved": True, "status": payload.status.value}
