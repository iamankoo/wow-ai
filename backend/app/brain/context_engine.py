"""Phase 1 reference ContextEngine implementation.

Builds the ConversationContext by looking up the contact (by caller number),
the active ContextProfile for that contact/user, and recent memories via the
MemoryStore. Real database lookups, no mocked data - the "unknown caller"
and "no active profile" paths are simply None, which callers must handle.
"""

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.interfaces.context_engine import ContextEngine, ConversationContext
from app.interfaces.memory_store import MemoryStore
from app.models.contact import Contact
from app.models.context import ContextProfile


class DefaultContextEngine(ContextEngine):
    def __init__(self, session: AsyncSession, memory_store: MemoryStore):
        self._session = session
        self._memory_store = memory_store

    async def build_context(
        self,
        *,
        user_id: str,
        caller_number: str | None = None,
        conversation_id: str | None = None,
    ) -> ConversationContext:
        contact = await self._find_contact(user_id, caller_number)
        profile = await self._find_active_profile(
            user_id, contact.id if contact else None
        )
        memories = await self._memory_store.search(
            user_id=user_id,
            query="",
            top_k=5,
        )

        return ConversationContext(
            user_id=user_id,
            contact={
                "id": str(contact.id),
                "name": contact.name,
                "relationship": contact.relationship,
            }
            if contact
            else None,
            context_profile={
                "id": str(profile.id),
                "name": profile.name,
                "instructions": profile.instructions,
            }
            if profile
            else None,
            recent_memories=[m.content for m in memories],
            conversation_history=[],
        )

    async def _find_contact(
        self, user_id: str, caller_number: str | None
    ) -> Contact | None:
        if not caller_number:
            return None
        stmt = select(Contact).where(
            Contact.user_id == uuid.UUID(str(user_id)),
            Contact.phone_number == caller_number,
        )
        result = await self._session.execute(stmt)
        return result.scalars().first()

    async def _find_active_profile(
        self, user_id: str, contact_id: uuid.UUID | None
    ) -> ContextProfile | None:
        stmt = select(ContextProfile).where(
            ContextProfile.user_id == uuid.UUID(str(user_id)),
            ContextProfile.is_active.is_(True),
        )
        if contact_id is not None:
            stmt = stmt.where(
                (ContextProfile.contact_id == contact_id)
                | (ContextProfile.contact_id.is_(None))
            )
            stmt = stmt.order_by(ContextProfile.contact_id.is_(None))
        else:
            stmt = stmt.where(ContextProfile.contact_id.is_(None))
        result = await self._session.execute(stmt)
        return result.scalars().first()
