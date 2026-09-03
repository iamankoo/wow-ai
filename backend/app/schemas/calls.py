import uuid
from datetime import datetime

from pydantic import BaseModel

from app.models.call import CallDirection, CallStatus
from app.models.transcript import Speaker


class CallListItem(BaseModel):
    """One row for the mobile app's call-history list (Phase 6 Part M) -
    real data written by CallRecorder during an actual handled call, never
    invented client-side."""

    id: uuid.UUID
    caller_number: str
    caller_name: str | None = None
    direction: CallDirection
    status: CallStatus
    started_at: datetime | None = None
    ended_at: datetime | None = None
    has_summary: bool = False

    model_config = {"from_attributes": True}


class TranscriptSegmentRead(BaseModel):
    speaker: Speaker
    text: str

    model_config = {"from_attributes": True}


class SummaryRead(BaseModel):
    summary_text: str
    key_points: list = []
    action_items: list = []

    model_config = {"from_attributes": True}


class CallDetail(CallListItem):
    transcript: list[TranscriptSegmentRead] = []
    summary: SummaryRead | None = None


class CallsTodaySummary(BaseModel):
    """Backs the main screen's Today's Summary tiles with real numbers -
    computed from the same Call rows, not invented."""

    calls_handled: int
    unique_callers: int
    total_seconds: int
