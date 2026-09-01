"""Confidence weighting for training-data ranking, and the active-learning
threshold policy for flagging low-confidence predictions for user review.

These are two related but distinct ideas, both called "confidence":

- confidence_weight (this module's EXPLICIT_CONFIDENCE / IMPLICIT_CONFIDENCE):
  how much a *feedback signal* should count when ranking/filtering training
  candidates. A fixed, small set of tiers - not a learned or per-example
  value - because feedback confidence is about how trustworthy the signal
  itself is (an explicit correction vs. an inferred behavioral cue), not
  about the underlying prediction.
- model confidence (ConfidencePolicy below): the softmax confidence WOW's
  own classifier heads report for a prediction. Used only to decide whether
  a prediction is trustworthy enough to act on directly, or should be
  logged to the active-learning review queue instead - never treated as a
  guarantee of correctness (see docs/SELF_LEARNING.md "Model confidence").
"""

from dataclasses import dataclass

from app.interfaces.feedback import FeedbackCategory, FeedbackSource, ImplicitSignalType

# Explicit feedback is a direct human judgment - trusted at (near) face
# value. PARTIALLY_CORRECT sits below CORRECT/a correction because it's an
# admission the signal is mixed.
EXPLICIT_CONFIDENCE: dict[FeedbackCategory, float] = {
    category: 1.0 for category in FeedbackCategory
}
EXPLICIT_CONFIDENCE[FeedbackCategory.PARTIALLY_CORRECT] = 0.7

# Implicit signals are inferred from behavior, not stated - two tiers per
# docs/SELF_LEARNING.md: a direct edit/correction (0.8) is fairly reliable;
# a signal that only weakly implies WOW was wrong (0.4) is not.
_DIRECT_EDIT = 0.8
_WEAK_BEHAVIORAL = 0.4

IMPLICIT_CONFIDENCE: dict[ImplicitSignalType, float] = {
    ImplicitSignalType.ACCEPTED_SUGGESTION: _DIRECT_EDIT,
    ImplicitSignalType.EDITED_SUMMARY: _DIRECT_EDIT,
    ImplicitSignalType.CORRECTED_CONTACT: _DIRECT_EDIT,
    ImplicitSignalType.CHANGED_ACTION: _DIRECT_EDIT,
    ImplicitSignalType.CHANGED_CONTEXT_AFTER_PREDICTION: _WEAK_BEHAVIORAL,
    ImplicitSignalType.REJECTED_ACTION: _WEAK_BEHAVIORAL,
    ImplicitSignalType.TOOK_OVER_CALL: _WEAK_BEHAVIORAL,
}


def confidence_weight(
    source: FeedbackSource | None,
    category: FeedbackCategory | None,
    implicit_signal_type: ImplicitSignalType | None,
) -> float | None:
    """The training-data-ranking weight for one feedback record. Returns
    None if there isn't enough information to assign one (e.g. a bare
    NEEDS_REVIEW row with no feedback yet)."""
    if source == FeedbackSource.EXPLICIT and category is not None:
        return EXPLICIT_CONFIDENCE.get(category, 1.0)
    if source == FeedbackSource.IMPLICIT and implicit_signal_type is not None:
        return IMPLICIT_CONFIDENCE.get(implicit_signal_type, _WEAK_BEHAVIORAL)
    return None


@dataclass
class ConfidenceThresholds:
    intent: float = 0.6
    context: float = 0.6
    action: float = 0.6


@dataclass
class ConfidenceAssessment:
    needs_review: bool
    low_confidence_heads: list[str]


class ConfidencePolicy:
    """Decides whether a prediction is trustworthy enough to act on
    directly, based on per-head softmax confidence vs configurable
    thresholds (app.config.Settings.*_confidence_threshold)."""

    def __init__(self, thresholds: ConfidenceThresholds | None = None):
        self._thresholds = thresholds or ConfidenceThresholds()

    def assess(
        self,
        *,
        intent_confidence: float | None,
        context_confidence: float | None = None,
        action_confidence: float | None = None,
    ) -> ConfidenceAssessment:
        low: list[str] = []
        if intent_confidence is not None and intent_confidence < self._thresholds.intent:
            low.append("intent")
        if context_confidence is not None and context_confidence < self._thresholds.context:
            low.append("context")
        if action_confidence is not None and action_confidence < self._thresholds.action:
            low.append("action")
        return ConfidenceAssessment(needs_review=bool(low), low_confidence_heads=low)
