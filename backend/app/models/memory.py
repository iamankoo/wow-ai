import enum
import uuid
from datetime import datetime

from pgvector.sqlalchemy import Vector
from sqlalchemy import DateTime, Enum, Float, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.config import get_settings
from app.db.base import Base, TimestampMixin, UUIDPKMixin

_settings = get_settings()


class MemoryType(str, enum.Enum):
    """Which of the four memory kinds from docs/ARCHITECTURE.md this row is.

    SHORT_TERM rows are conversation-scoped and expected to be cheap to
    invalidate/expire; the other three are the durable, cross-call store.
    """

    EPISODIC = "episodic"  # what happened in a specific past call
    SEMANTIC = "semantic"  # stable facts/preferences, not tied to one call
    CONTACT = "contact"  # facts about a specific contact/relationship
    SHORT_TERM = "short_term"  # this call only - active topics, unresolved requests


class MemoryStatus(str, enum.Enum):
    """How much this memory should be trusted - see docs "Memory safety".

    A statement WOW merely observed in conversation is not automatically a
    permanent fact: it starts OBSERVED (or INFERRED, if WOW derived rather
    than heard it) and only becomes CONFIRMED/USER_APPROVED through an
    explicit confirmation step. Retrieval/ranking should weight status
    alongside `confidence`, never assume every row is equally reliable.
    """

    OBSERVED = "observed"
    INFERRED = "inferred"
    CONFIRMED = "confirmed"
    USER_APPROVED = "user_approved"


class Memory(UUIDPKMixin, TimestampMixin, Base):
    """A memory fact, embedded for semantic recall via pgvector.

    The embedding is produced by whatever LanguageModelProvider/embedding
    model is currently configured - this table does not assume a specific
    vendor or model, only a fixed-size float vector.

    `deleted_at` is a soft-delete marker: user-facing deletion
    (`DELETE /memories/{id}`) sets it rather than removing the row outright,
    so an accidental delete is recoverable and the row remains available for
    audit; `MemoryStore.delete` callers that need a hard delete (e.g.
    personalization.reset_personalization) still issue a real SQL DELETE.
    """

    __tablename__ = "memories"

    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), index=True)
    contact_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("contacts.id"), nullable=True, index=True
    )
    content: Mapped[str] = mapped_column(Text)
    embedding: Mapped[list[float] | None] = mapped_column(
        Vector(_settings.memory_embedding_dim), nullable=True
    )
    source_type: Mapped[str] = mapped_column(String(32), default="manual")
    source_id: Mapped[uuid.UUID | None] = mapped_column(nullable=True)
    memory_type: Mapped[MemoryType] = mapped_column(
        Enum(MemoryType, name="memory_type"), default=MemoryType.SEMANTIC
    )
    status: Mapped[MemoryStatus] = mapped_column(
        Enum(MemoryStatus, name="memory_status"), default=MemoryStatus.OBSERVED
    )
    confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    deleted_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
