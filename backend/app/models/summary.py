import uuid

from sqlalchemy import JSON, ForeignKey, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin, UUIDPKMixin


class Summary(UUIDPKMixin, TimestampMixin, Base):
    """A short, human-reviewable summary generated after a conversation ends."""

    __tablename__ = "summaries"

    conversation_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("conversations.id"), unique=True, index=True
    )
    summary_text: Mapped[str] = mapped_column(Text)
    key_points: Mapped[list] = mapped_column(JSON, default=list)
    action_items: Mapped[list] = mapped_column(JSON, default=list)
