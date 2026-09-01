"""Operations that touch the User/Memory tables directly (unlike the rest
of app/learning/, which is DB-agnostic behind FeedbackRepository) - these
are simple enough CRUD that an interface layer would be pure ceremony,
matching how app/api/routes/contacts.py talks to the ORM directly.

Personalization vs. model training (docs/SELF_LEARNING.md section 5):
Memory/ContextProfile rows are per-user personalization ("Aniket prefers
family calls treated as high-priority") and never feed the global training
pipeline. reset_personalization only touches that data - it has nothing to
do with FeedbackEvent/model retraining.
"""

import uuid

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.memory import Memory
from app.models.user import User


async def set_training_data_consent(session: AsyncSession, user_id: str, consent: bool) -> None:
    """The "disable learning" / "enable learning" toggle - the per-user
    default that new feedback submissions inherit unless a submission
    explicitly overrides it. Does not retroactively change past events."""
    user = await session.get(User, uuid.UUID(str(user_id)))
    if user is None:
        raise ValueError(f"No user with id {user_id}")
    user.training_data_consent = consent
    await session.flush()


async def get_training_data_consent(session: AsyncSession, user_id: str) -> bool:
    user = await session.get(User, uuid.UUID(str(user_id)))
    if user is None:
        raise ValueError(f"No user with id {user_id}")
    return user.training_data_consent


async def reset_personalization(session: AsyncSession, user_id: str) -> int:
    """Deletes every learned Memory for this user - "reset learned
    personalization". Does not touch FeedbackEvent rows or any trained
    model; it only clears the per-user personalization store."""
    stmt = select(Memory).where(Memory.user_id == uuid.UUID(str(user_id)))
    result = await session.execute(stmt)
    rows = list(result.scalars().all())
    if rows:
        await session.execute(delete(Memory).where(Memory.user_id == uuid.UUID(str(user_id))))
        await session.flush()
    return len(rows)
