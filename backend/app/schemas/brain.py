import uuid
from datetime import date

from pydantic import BaseModel

from app.models.user import PreferredLanguage, VoiceGender


class BrainCommandRequest(BaseModel):
    user_id: str
    text: str
    conversation_id: str | None = None
    caller_number: str | None = None


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

    model_config = {"from_attributes": True}


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
