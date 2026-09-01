import enum
import uuid
from datetime import datetime

from sqlalchemy import DateTime, Enum, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin, UUIDPKMixin


class ConversationStatus(str, enum.Enum):
    ACTIVE = "active"
    COMPLETED = "completed"


class Conversation(UUIDPKMixin, TimestampMixin, Base):
    """A conversation session: either tied to a phone Call, or a standalone
    text/voice session (e.g. the user talking to WOW AI directly)."""

    __tablename__ = "conversations"

    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), index=True)
    call_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("calls.id"), nullable=True, index=True
    )
    status: Mapped[ConversationStatus] = mapped_column(
        Enum(ConversationStatus, name="conversation_status"),
        default=ConversationStatus.ACTIVE,
    )
    started_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    ended_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
