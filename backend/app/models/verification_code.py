import enum
import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, Enum, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin, UUIDPKMixin


class VerificationChannel(str, enum.Enum):
    MOBILE = "mobile"
    EMAIL = "email"


class VerificationCode(UUIDPKMixin, TimestampMixin, Base):
    """A single one-time verification code request (Phase 6 Part C).

    `destination` is captured at request time (not re-read from the live
    User row) so a code stays valid against the phone/email it was actually
    sent to even if the user edits their profile before confirming it.
    `code_hash` never stores the plaintext code - see
    app/services/verification_service.py for hashing/comparison.
    """

    __tablename__ = "verification_codes"

    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), index=True)
    channel: Mapped[VerificationChannel] = mapped_column(
        Enum(VerificationChannel, name="verification_channel")
    )
    destination: Mapped[str] = mapped_column(String(255))
    code_hash: Mapped[str] = mapped_column(String(64))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    consumed: Mapped[bool] = mapped_column(Boolean, default=False)
