import enum
import uuid
from datetime import datetime

from sqlalchemy import DateTime, Enum, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin, UUIDPKMixin


class CallDirection(str, enum.Enum):
    INBOUND = "inbound"
    OUTBOUND = "outbound"


class CallStatus(str, enum.Enum):
    RINGING = "ringing"
    ACTIVE = "active"
    COMPLETED = "completed"
    MISSED = "missed"
    VOICEMAIL = "voicemail"


class Call(UUIDPKMixin, TimestampMixin, Base):
    """A single phone call handled (or observed) by WOW AI."""

    __tablename__ = "calls"

    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), index=True)
    contact_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("contacts.id"), nullable=True, index=True
    )
    context_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("context_profiles.id"), nullable=True
    )
    caller_number: Mapped[str] = mapped_column(String(32))
    direction: Mapped[CallDirection] = mapped_column(
        Enum(CallDirection, name="call_direction")
    )
    status: Mapped[CallStatus] = mapped_column(
        Enum(CallStatus, name="call_status"), default=CallStatus.RINGING
    )
    started_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    ended_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
