"""Write path for ContextProfile rows (backend/app/models/context.py),
used by the set_context/clear_context agent tools. Mirrors the
StateRepository/SummaryRepository pattern (ABC + SQL + in-memory test
double) used throughout `app.brain`/`app.agent`.

`DefaultContextEngine` (app/brain/context_engine.py) is the read side of
this same table - it already looks up whichever profile has
`is_active=True` for a (user_id, contact_id) scope. This module is the
write side that was missing: nothing previously set `is_active`, so a
predicted SET_CONTEXT/CLEAR_CONTEXT action could only be reported, never
actually applied.

Scoping: a `contact_id` of None means "the general profile" (applies to
any caller); a given `contact_id` means a profile specific to that
contact. Setting or clearing a profile only ever touches rows in the same
scope - setting a contact-specific profile never deactivates the user's
general profile, and vice versa.
"""

import uuid
from abc import ABC, abstractmethod

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.context import ContextProfile


class ContextProfileRepository(ABC):
    @abstractmethod
    async def set_active(
        self,
        *,
        user_id: str,
        name: str,
        instructions: str,
        contact_id: str | None = None,
    ) -> str:
        """Activate the profile named `name` for this (user, contact) scope,
        creating it if it doesn't exist yet and deactivating any other
        currently-active profile in the same scope. Returns the profile id."""

    @abstractmethod
    async def clear_active(self, *, user_id: str, contact_id: str | None = None) -> int:
        """Deactivate whichever profile(s) are currently active for this
        scope. Returns how many rows were deactivated (0 if none were
        active - not an error, "already clear" is a success state)."""


class SqlContextProfileRepository(ContextProfileRepository):
    def __init__(self, session: AsyncSession):
        self._session = session

    async def set_active(
        self,
        *,
        user_id: str,
        name: str,
        instructions: str,
        contact_id: str | None = None,
    ) -> str:
        uid = uuid.UUID(str(user_id))
        cid = uuid.UUID(str(contact_id)) if contact_id else None

        existing_active = await self._active_rows(uid, cid)
        target: ContextProfile | None = None
        for row in existing_active:
            if row.name == name:
                target = row
            else:
                row.is_active = False

        if target is None:
            stmt = select(ContextProfile).where(
                ContextProfile.user_id == uid,
                ContextProfile.contact_id == cid,
                ContextProfile.name == name,
            )
            result = await self._session.execute(stmt)
            target = result.scalars().first()

        if target is None:
            target = ContextProfile(
                user_id=uid,
                contact_id=cid,
                name=name,
                instructions=instructions,
                is_active=True,
            )
            self._session.add(target)
        else:
            target.instructions = instructions
            target.is_active = True

        await self._session.flush()
        return str(target.id)

    async def clear_active(self, *, user_id: str, contact_id: str | None = None) -> int:
        uid = uuid.UUID(str(user_id))
        cid = uuid.UUID(str(contact_id)) if contact_id else None
        rows = await self._active_rows(uid, cid)
        for row in rows:
            row.is_active = False
        await self._session.flush()
        return len(rows)

    async def _active_rows(
        self, user_id: uuid.UUID, contact_id: uuid.UUID | None
    ) -> list[ContextProfile]:
        stmt = select(ContextProfile).where(
            ContextProfile.user_id == user_id,
            ContextProfile.contact_id == contact_id,
            ContextProfile.is_active.is_(True),
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())


class InMemoryContextProfileRepository(ContextProfileRepository):
    """Test/dev double - no database required."""

    def __init__(self):
        # (user_id, contact_id, name) -> {"id": str, "instructions": str, "is_active": bool}
        self._profiles: dict[tuple[str, str | None, str], dict] = {}
        self._next_id = 1

    async def set_active(
        self,
        *,
        user_id: str,
        name: str,
        instructions: str,
        contact_id: str | None = None,
    ) -> str:
        for key, profile in self._profiles.items():
            if key[0] == user_id and key[1] == contact_id and key[2] != name:
                profile["is_active"] = False

        key = (user_id, contact_id, name)
        profile = self._profiles.get(key)
        if profile is None:
            profile = {"id": str(self._next_id), "instructions": instructions, "is_active": True}
            self._next_id += 1
            self._profiles[key] = profile
        else:
            profile["instructions"] = instructions
            profile["is_active"] = True
        return profile["id"]

    async def clear_active(self, *, user_id: str, contact_id: str | None = None) -> int:
        cleared = 0
        for key, profile in self._profiles.items():
            if key[0] == user_id and key[1] == contact_id and profile["is_active"]:
                profile["is_active"] = False
                cleared += 1
        return cleared

    def active_name(self, *, user_id: str, contact_id: str | None = None) -> str | None:
        """Test helper: the currently-active profile's name for this scope, if any."""
        for key, profile in self._profiles.items():
            if key[0] == user_id and key[1] == contact_id and profile["is_active"]:
                return key[2]
        return None
