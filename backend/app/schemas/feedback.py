from pydantic import BaseModel

from app.interfaces.feedback import FeedbackCategory, FeedbackSource, FeedbackStatus, ImplicitSignalType


class FeedbackSubmitRequest(BaseModel):
    model_config = {"protected_namespaces": ()}

    user_id: str
    text: str
    predicted_intent: str | None = None
    predicted_context_mode: str | None = None
    predicted_action: str | None = None
    intent_confidence: float | None = None
    context_confidence: float | None = None
    action_confidence: float | None = None
    model_version: str | None = None
    conversation_id: str | None = None
    language: str | None = None
    source: FeedbackSource = FeedbackSource.EXPLICIT
    category: FeedbackCategory
    implicit_signal_type: ImplicitSignalType | None = None
    corrected_intent: str | None = None
    corrected_context_mode: str | None = None
    corrected_action: str | None = None
    corrected_caller_name: str | None = None
    # Conservative default: feedback is stored either way (for product
    # analytics / review), but is NEVER eligible for training unless this
    # is explicitly set True on the submission.
    consent_for_training: bool = False


class FeedbackRead(BaseModel):
    id: str
    status: FeedbackStatus
    predicted_intent: str | None = None
    corrected_intent: str | None = None
    consent_for_training: bool
    confidence_weight: float | None = None


class FeedbackRespondRequest(BaseModel):
    """Resolves a NEEDS_REVIEW (active-learning queue) item: was the logged
    prediction correct?"""

    correct: bool
    corrected_intent: str | None = None
    corrected_context_mode: str | None = None
    corrected_action: str | None = None
    consent_for_training: bool = False


class FeedbackApproveRequest(BaseModel):
    reviewed_by: str


class ConsentUpdateRequest(BaseModel):
    consent: bool
