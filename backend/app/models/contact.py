import uuid

from sqlalchemy import ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin, UUIDPKMixin


class Contact(UUIDPKMixin, TimestampMixin, Base):
    """A person known to the user, used to identify callers and load context."""

    __tablename__ = "contacts"

    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), index=True)
    name: Mapped[str] = mapped_column(String(120))
    phone_number: Mapped[str] = mapped_column(String(32), index=True)
    relationship: Mapped[str | None] = mapped_column(String(64), nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
