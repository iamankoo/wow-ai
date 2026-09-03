from sqlalchemy import Boolean, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin, UUIDPKMixin


class User(UUIDPKMixin, TimestampMixin, Base):
    """The person WOW AI works on behalf of (the phone owner)."""

    __tablename__ = "users"

    display_name: Mapped[str] = mapped_column(String(120))
    phone_number: Mapped[str] = mapped_column(String(32), unique=True, index=True)
    email: Mapped[str | None] = mapped_column(String(255), nullable=True)

    # Default consent for new feedback events submitted without an explicit
    # per-submission override - conservative by design (opt-in, not
    # opt-out). See docs/SELF_LEARNING.md "Privacy and consent".
    training_data_consent: Mapped[bool] = mapped_column(Boolean, default=False)

    # Whether WOW is currently authorized to answer/handle incoming calls on
    # this user's behalf - written by the enable_call_assistant/
    # disable_call_assistant agent tools (app/agent/builtin_tools.py), off
    # by default so automation is always opt-in.
    call_assistant_enabled: Mapped[bool] = mapped_column(Boolean, default=False)
