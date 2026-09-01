import enum
import uuid

from sqlalchemy import Enum, Float, ForeignKey, Integer, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin, UUIDPKMixin


class Speaker(str, enum.Enum):
    CALLER = "caller"
    ASSISTANT = "assistant"
    USER = "user"


class TranscriptSegment(UUIDPKMixin, TimestampMixin, Base):
    """One utterance in a conversation, produced by the STT provider or the brain."""

    __tablename__ = "transcript_segments"

    conversation_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("conversations.id"), index=True
    )
    speaker: Mapped[Speaker] = mapped_column(Enum(Speaker, name="speaker"))
    text: Mapped[str] = mapped_column(Text)
    started_at_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    ended_at_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
