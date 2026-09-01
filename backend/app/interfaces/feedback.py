"""Feedback/self-learning abstractions - the seam that keeps the learning
pipeline (app/learning/) independent of SQLAlchemy, so its privacy-critical
logic (consent gating, redaction, promotion decisions) is unit-testable
without a database, the same way ContextEngine/StateRepository/
LanguageModelProvider are for the rest of the brain.

See docs/SELF_LEARNING.md for the full architecture this supports:

    WOW prediction -> user feedback (explicit or implicit)
        -> FeedbackRepository (stores FeedbackRecord)
        -> FeedbackProcessor (consent -> retention -> PII detect -> redact)
        -> human approval (explicit authorization, never automatic)
        -> TrainingCandidateBuilder -> dataset file
        -> training/evaluation (existing pipeline) -> ModelRegistry/PromotionManager
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum


class FeedbackSource(str, Enum):
    EXPLICIT = "explicit"
    IMPLICIT = "implicit"


class FeedbackCategory(str, Enum):
    CORRECT = "correct"
    INCORRECT = "incorrect"
    PARTIALLY_CORRECT = "partially_correct"
    WRONG_INTENT = "wrong_intent"
    WRONG_CONTEXT = "wrong_context"
    WRONG_ACTION = "wrong_action"
    WRONG_CALLER_CLASSIFICATION = "wrong_caller_classification"
    WRONG_SUMMARY = "wrong_summary"
    WRONG_RESPONSE = "wrong_response"
    USER_CORRECTION = "user_correction"


class ImplicitSignalType(str, Enum):
    ACCEPTED_SUGGESTION = "accepted_suggestion"
    EDITED_SUMMARY = "edited_summary"
    CHANGED_CONTEXT_AFTER_PREDICTION = "changed_context_after_prediction"
    CORRECTED_CONTACT = "corrected_contact"
    CHANGED_ACTION = "changed_action"
    REJECTED_ACTION = "rejected_action"
    TOOK_OVER_CALL = "took_over_call"


class FeedbackStatus(str, Enum):
    NEEDS_REVIEW = "needs_review"
    RECEIVED = "received"
    REJECTED = "rejected"
    CANDIDATE = "candidate"
    APPROVED = "approved"
    INCLUDED = "included"


@dataclass
class FeedbackRecord:
    """Plain-data mirror of app/models/feedback.py:FeedbackEvent. The
    learning pipeline operates entirely on this type - only
    app/learning/feedback_repository.py knows about the ORM."""

    id: str
    user_id: str
    raw_text: str
    status: FeedbackStatus
    created_at: datetime
    conversation_id: str | None = None
    redacted_text: str | None = None
    language: str | None = None

    predicted_intent: str | None = None
    predicted_context_mode: str | None = None
    predicted_action: str | None = None
    intent_confidence: float | None = None
    context_confidence: float | None = None
    action_confidence: float | None = None
    model_version: str | None = None

    source: FeedbackSource | None = None
    category: FeedbackCategory | None = None
    implicit_signal_type: ImplicitSignalType | None = None
    confidence_weight: float | None = None

    corrected_intent: str | None = None
    corrected_context_mode: str | None = None
    corrected_action: str | None = None
    corrected_caller_name: str | None = None

    consent_for_training: bool = False
    rejection_reason: str | None = None
    candidate_dataset_batch: str | None = None


@dataclass
class FeedbackSubmission:
    """Input to FeedbackRepository.create - everything needed to record one
    feedback signal (or one logged low-confidence prediction, if source/
    category are left None and status defaults to NEEDS_REVIEW)."""

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
    source: FeedbackSource | None = None
    category: FeedbackCategory | None = None
    implicit_signal_type: ImplicitSignalType | None = None
    corrected_intent: str | None = None
    corrected_context_mode: str | None = None
    corrected_action: str | None = None
    corrected_caller_name: str | None = None
    consent_for_training: bool = False
    status: FeedbackStatus = FeedbackStatus.RECEIVED


class FeedbackRepository(ABC):
    @abstractmethod
    async def create(self, submission: FeedbackSubmission) -> FeedbackRecord: ...

    @abstractmethod
    async def get(self, feedback_id: str) -> FeedbackRecord | None: ...

    @abstractmethod
    async def list_by_status(self, status: FeedbackStatus, *, user_id: str | None = None) -> list[FeedbackRecord]: ...

    @abstractmethod
    async def list_by_user(self, user_id: str) -> list[FeedbackRecord]: ...

    @abstractmethod
    async def update(self, record: FeedbackRecord) -> None: ...

    @abstractmethod
    async def delete(self, feedback_id: str) -> bool: ...

    @abstractmethod
    async def delete_by_user(self, user_id: str, *, statuses: list[FeedbackStatus] | None = None) -> int: ...


@dataclass
class RedactionResult:
    redacted_text: str
    was_modified: bool
    redaction_types: list[str] = field(default_factory=list)


class PrivacyFilter(ABC):
    @abstractmethod
    def redact(self, text: str) -> RedactionResult:
        """Best-effort PII redaction. This is defense-in-depth regex
        matching, not a guarantee of perfect PII removal - see
        docs/SELF_LEARNING.md "Privacy filter limitations"."""
