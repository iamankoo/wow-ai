import uuid

from pydantic import BaseModel


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


class UserRead(BaseModel):
    id: uuid.UUID
    display_name: str
    phone_number: str
    email: str | None = None
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
