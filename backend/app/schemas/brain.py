import uuid
from datetime import date, datetime, timezone

from pydantic import BaseModel, computed_field, field_validator

from app.models.user import PreferredLanguage, VoiceGender


class BrainCommandRequest(BaseModel):
    user_id: str
    text: str
    conversation_id: str | None = None
    caller_number: str | None = None

    @field_validator("user_id")
    @classmethod
    def _user_id_must_be_uuid(cls, value: str) -> str:
        # Kept as str (not uuid.UUID) so AgentRuntime.handle_input's existing
        # str contract is untouched - this only turns a malformed user_id
        # into a clean 422 instead of an unhandled 500 from a downstream
        # uuid.UUID(...) conversion failing deep in the agent/DB layer.
        try:
            uuid.UUID(value)
        except ValueError as exc:
            raise ValueError("user_id must be a valid UUID") from exc
        return value


class BrainCommandResponse(BaseModel):
    action_type: str
    payload: dict


class UserCreate(BaseModel):
    display_name: str
    phone_number: str
    email: str | None = None


class UserProfileUpdate(BaseModel):
    """PATCH /users/{id} - Phase 6 Part C/N. All fields optional so a
    client can save one field at a time. Changing phone_number/email
    resets the corresponding *_verified flag server-side (see
    routes/users.py) - a verified code only ever proved control over the
    destination it was sent to."""

    display_name: str | None = None
    phone_number: str | None = None
    email: str | None = None
    date_of_birth: date | None = None
    preferred_language: PreferredLanguage | None = None
    voice_gender: VoiceGender | None = None


class UserRead(BaseModel):
    id: uuid.UUID
    display_name: str
    phone_number: str
    email: str | None = None
    date_of_birth: date | None = None
    age: int | None = None
    mobile_verified: bool = False
    email_verified: bool = False
    personalization_completed: bool = False
    preferred_language: PreferredLanguage = PreferredLanguage.ENGLISH
    voice_gender: VoiceGender = VoiceGender.FEMALE
    profile_complete: bool = False
    call_assistant_enabled: bool = False
    active_until: datetime | None = None
    created_at: datetime

    model_config = {"from_attributes": True}

    @computed_field  # type: ignore[prop-decorator]
    @property
    def active_seconds_remaining(self) -> int | None:
        """Phase 6 Part K - lets the main screen show a real countdown
        instead of just an on/off state. None means either off, or on
        with no expiry ("Until I stop") - the UI already has
        call_assistant_enabled to tell those apart."""
        if not self.call_assistant_enabled or self.active_until is None:
            return None
        remaining = (self.active_until - datetime.now(timezone.utc)).total_seconds()
        return max(0, int(remaining))


class ContactCreate(BaseModel):
    user_id: uuid.UUID
    name: str
    phone_number: str
    relationship: str | None = None
    notes: str | None = None


class ContactRead(BaseModel):
    id: uuid.UUID
    user_id: uuid.UUID
    name: str
    phone_number: str
    relationship: str | None = None
    notes: str | None = None

    model_config = {"from_attributes": True}
