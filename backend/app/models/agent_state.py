import uuid

from sqlalchemy import JSON, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin, UUIDPKMixin


class AgentState(UUIDPKMixin, TimestampMixin, Base):
    """Persisted key/value working state for the agent brain, scoped to a user
    and optionally a specific conversation. This is the durable backing store
    for the LangGraph-style stateful graph (current intent, slots, step, etc).
    """

    __tablename__ = "agent_states"

    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), index=True)
    conversation_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("conversations.id"), nullable=True, index=True
    )
    state_key: Mapped[str] = mapped_column(String(80), index=True)
    state_value: Mapped[dict] = mapped_column(JSON, default=dict)
