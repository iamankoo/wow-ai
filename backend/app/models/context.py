import uuid

from sqlalchemy import Boolean, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin, UUIDPKMixin


class ContextProfile(UUIDPKMixin, TimestampMixin, Base):
    """A named persona/behavior profile the brain uses while handling a call.

    Can be general (contact_id is null, e.g. "sleeping", "in-a-meeting") or
    scoped to a specific contact for personalized handling.
    """

    __tablename__ = "context_profiles"

    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), index=True)
    contact_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("contacts.id"), nullable=True, index=True
    )
    name: Mapped[str] = mapped_column(String(80))
    instructions: Mapped[str] = mapped_column(Text)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
