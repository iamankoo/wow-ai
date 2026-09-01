import uuid

from pgvector.sqlalchemy import Vector
from sqlalchemy import ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.config import get_settings
from app.db.base import Base, TimestampMixin, UUIDPKMixin

_settings = get_settings()


class Memory(UUIDPKMixin, TimestampMixin, Base):
    """A long-term memory fact, embedded for semantic recall via pgvector.

    The embedding is produced by whatever LanguageModelProvider/embedding
    model is currently configured - this table does not assume a specific
    vendor or model, only a fixed-size float vector.
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
