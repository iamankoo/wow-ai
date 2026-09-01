from app.interfaces.feedback import FeedbackCategory, FeedbackSource, ImplicitSignalType
from app.learning.confidence import (
    ConfidencePolicy,
    ConfidenceThresholds,
    confidence_weight,
)


def test_explicit_correction_gets_full_confidence():
    w = confidence_weight(FeedbackSource.EXPLICIT, FeedbackCategory.USER_CORRECTION, None)
    assert w == 1.0


def test_explicit_partially_correct_gets_reduced_confidence():
    w = confidence_weight(FeedbackSource.EXPLICIT, FeedbackCategory.PARTIALLY_CORRECT, None)
    assert w == 0.7


def test_implicit_direct_edit_gets_08():
    w = confidence_weight(FeedbackSource.IMPLICIT, None, ImplicitSignalType.EDITED_SUMMARY)
    assert w == 0.8


def test_implicit_weak_behavioral_signal_gets_04():
    w = confidence_weight(FeedbackSource.IMPLICIT, None, ImplicitSignalType.TOOK_OVER_CALL)
    assert w == 0.4


def test_explicit_confidence_always_exceeds_implicit_confidence():
    explicit = confidence_weight(FeedbackSource.EXPLICIT, FeedbackCategory.CORRECT, None)
    implicit = confidence_weight(FeedbackSource.IMPLICIT, None, ImplicitSignalType.ACCEPTED_SUGGESTION)
    assert explicit > implicit


def test_missing_category_or_signal_type_returns_none():
    assert confidence_weight(FeedbackSource.EXPLICIT, None, None) is None
    assert confidence_weight(FeedbackSource.IMPLICIT, None, None) is None
    assert confidence_weight(None, None, None) is None


def test_confidence_policy_flags_low_intent_confidence():
    policy = ConfidencePolicy(ConfidenceThresholds(intent=0.6))
    assessment = policy.assess(intent_confidence=0.4)
    assert assessment.needs_review is True
    assert assessment.low_confidence_heads == ["intent"]


def test_confidence_policy_does_not_flag_high_confidence():
    policy = ConfidencePolicy(ConfidenceThresholds(intent=0.6))
    assessment = policy.assess(intent_confidence=0.9, context_confidence=0.8, action_confidence=0.95)
    assert assessment.needs_review is False
    assert assessment.low_confidence_heads == []


def test_confidence_policy_flags_multiple_low_heads():
    policy = ConfidencePolicy(ConfidenceThresholds(intent=0.6, context=0.6, action=0.6))
    assessment = policy.assess(intent_confidence=0.9, context_confidence=0.3, action_confidence=0.2)
    assert assessment.needs_review is True
    assert set(assessment.low_confidence_heads) == {"context", "action"}


def test_confidence_policy_ignores_heads_with_no_confidence_reported():
    policy = ConfidencePolicy()
    assessment = policy.assess(intent_confidence=0.9)
    assert assessment.needs_review is False
