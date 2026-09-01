"""FeedbackEvent - the persistence layer for WOW's controlled self-learning
loop (see docs/SELF_LEARNING.md). One row per feedback signal (explicit
user correction, or an implicit behavioral signal) OR per low-confidence
prediction logged for active-learning review before any feedback exists.

Status lifecycle (app/interfaces/feedback.py:FeedbackStatus documents the
full state machine and what each transition requires):

    NEEDS_REVIEW -> RECEIVED -> REJECTED
                             -> CANDIDATE -> APPROVED -> INCLUDED

Nothing in this table is ever training data by default - see
app/learning/feedback_processor.py for the privacy pipeline that gates
every transition past RECEIVED.
"""

import enum
import uuid

from sqlalchemy import Boolean, Enum, Float, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin, UUIDPKMixin


class FeedbackSource(str, enum.Enum):
    EXPLICIT = "explicit"
    IMPLICIT = "implicit"


class FeedbackCategory(str, enum.Enum):
    """What the feedback is actually saying about a prediction. Deliberately
    a flat enum matching product-facing feedback categories 1:1, rather than
    a generic positive/negative polarity - "wrong_context" and "wrong_action"
    need to be distinguishable so failure mining can cluster by field."""

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


class ImplicitSignalType(str, enum.Enum):
    ACCEPTED_SUGGESTION = "accepted_suggestion"
    EDITED_SUMMARY = "edited_summary"
    CHANGED_CONTEXT_AFTER_PREDICTION = "changed_context_after_prediction"
    CORRECTED_CONTACT = "corrected_contact"
    CHANGED_ACTION = "changed_action"
    REJECTED_ACTION = "rejected_action"
    TOOK_OVER_CALL = "took_over_call"


class FeedbackStatus(str, enum.Enum):
    NEEDS_REVIEW = "needs_review"   # low-confidence prediction awaiting user response (active learning)
    RECEIVED = "received"           # feedback recorded, not yet processed by the privacy pipeline
    REJECTED = "rejected"           # failed consent/retention/validation - never usable, terminal
    CANDIDATE = "candidate"         # passed the privacy pipeline; awaiting human approval
    APPROVED = "approved"           # a human explicitly authorized this for dataset inclusion
    INCLUDED = "included"           # actually written into a built training-candidate dataset file


class FeedbackEvent(UUIDPKMixin, TimestampMixin, Base):
    __tablename__ = "feedback_events"

    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), index=True)
    conversation_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("conversations.id"), nullable=True, index=True
    )

    # The utterance the prediction was made on. raw_text is never exposed
    # outside this table/export; anything downstream of the privacy filter
    # uses redacted_text only.
    raw_text: Mapped[str] = mapped_column(Text)
    redacted_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    language: Mapped[str | None] = mapped_column(String(16), nullable=True)

    predicted_intent: Mapped[str | None] = mapped_column(String(64), nullable=True)
    predicted_context_mode: Mapped[str | None] = mapped_column(String(32), nullable=True)
    predicted_action: Mapped[str | None] = mapped_column(String(64), nullable=True)
    intent_confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    context_confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    action_confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    model_version: Mapped[str | None] = mapped_column(String(32), nullable=True)

    source: Mapped[FeedbackSource | None] = mapped_column(
        Enum(FeedbackSource, name="feedback_source"), nullable=True
    )
    category: Mapped[FeedbackCategory | None] = mapped_column(
        Enum(FeedbackCategory, name="feedback_category"), nullable=True
    )
    implicit_signal_type: Mapped[ImplicitSignalType | None] = mapped_column(
        Enum(ImplicitSignalType, name="implicit_signal_type"), nullable=True
    )
    # Training-data-ranking weight, NOT a probability - see
    # app/learning/confidence.py for the fixed tiers this is drawn from
    # (explicit=1.0, direct implicit edit=0.8, weak behavioral signal=0.4).
    confidence_weight: Mapped[float | None] = mapped_column(Float, nullable=True)

    corrected_intent: Mapped[str | None] = mapped_column(String(64), nullable=True)
    corrected_context_mode: Mapped[str | None] = mapped_column(String(32), nullable=True)
    corrected_action: Mapped[str | None] = mapped_column(String(64), nullable=True)
    corrected_caller_name: Mapped[str | None] = mapped_column(String(120), nullable=True)

    consent_for_training: Mapped[bool] = mapped_column(Boolean, default=False)
    status: Mapped[FeedbackStatus] = mapped_column(
        Enum(FeedbackStatus, name="feedback_status"), default=FeedbackStatus.RECEIVED
    )
    rejection_reason: Mapped[str | None] = mapped_column(String(64), nullable=True)
    candidate_dataset_batch: Mapped[str | None] = mapped_column(String(64), nullable=True)
