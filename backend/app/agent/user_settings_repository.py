"""Write path for the small set of per-user settings agent tools can
change directly (currently just `call_assistant_enabled`). Mirrors the
StateRepository/SummaryRepository/ContextProfileRepository pattern (ABC +
SQL + in-memory test double).
"""

import uuid
from abc import ABC, abstractmethod

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.user import User


class UserSettingsRepository(ABC):
    @abstractmethod
    async def set_call_assistant_enabled(self, *, user_id: str, enabled: bool) -> bool:
        """Returns False if no such user exists (a tool failure, not an
        exception - consistent with MemoryStore.delete's "missing row is a
        result, not an error" convention elsewhere in this codebase)."""


class SqlUserSettingsRepository(UserSettingsRepository):
    def __init__(self, session: AsyncSession):
        self._session = session

    async def set_call_assistant_enabled(self, *, user_id: str, enabled: bool) -> bool:
        user = await self._session.get(User, uuid.UUID(str(user_id)))
        if user is None:
            return False
        user.call_assistant_enabled = enabled
        await self._session.flush()
        return True


class InMemoryUserSettingsRepository(UserSettingsRepository):
    """Test/dev double - no database required."""

    def __init__(self):
        self._enabled: dict[str, bool] = {}

    async def set_call_assistant_enabled(self, *, user_id: str, enabled: bool) -> bool:
        self._enabled[user_id] = enabled
        return True

    def is_enabled(self, *, user_id: str) -> bool:
        """Test helper: the currently-set value for this user, defaulting
        to False (matching the model column's default) if never set."""
        return self._enabled.get(user_id, False)
