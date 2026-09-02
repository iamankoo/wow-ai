"""PolicyEngine verdicts - see app/agent/policy.py."""

from app.brain.taxonomy import Action
from app.agent.policy import PolicyEngine, PolicyVerdict
from app.learning.confidence import ConfidenceAssessment

_OK = ConfidenceAssessment(needs_review=False, low_confidence_heads=[])
_LOW = ConfidenceAssessment(needs_review=True, low_confidence_heads=["action"])


def test_no_action_is_always_allowed():
    engine = PolicyEngine()
    decision = engine.evaluate(
        action=None, confidence_assessment=_OK, overall_confidence=0.9, contact_known=False
    )
    assert decision.verdict == PolicyVerdict.ALLOW

    decision = engine.evaluate(
        action=Action.NO_ACTION.value,
        confidence_assessment=_OK,
        overall_confidence=0.1,
        contact_known=False,
    )
    assert decision.verdict == PolicyVerdict.ALLOW


def test_low_confidence_routes_to_clarify():
    engine = PolicyEngine()
    decision = engine.evaluate(
        action=Action.ANSWER_CALL.value,
        confidence_assessment=_LOW,
        overall_confidence=0.3,
        contact_known=True,
    )
    assert decision.verdict == PolicyVerdict.CLARIFY
    assert "low_confidence" in decision.reason


def test_unrecognized_action_never_trusted_even_at_high_confidence():
    engine = PolicyEngine()
    decision = engine.evaluate(
        action="DELETE_EVERYTHING",
        confidence_assessment=_OK,
        overall_confidence=0.99,
        contact_known=True,
    )
    assert decision.verdict == PolicyVerdict.CLARIFY
    assert decision.reason == "unrecognized_action"


def test_sensitive_action_requires_high_confidence():
    engine = PolicyEngine(min_sensitive_confidence=0.75)
    decision = engine.evaluate(
        action=Action.SAVE_MEMORY.value,
        confidence_assessment=_OK,
        overall_confidence=0.5,
        contact_known=True,
    )
    assert decision.verdict == PolicyVerdict.CLARIFY
    assert decision.reason == "sensitive_action_below_confidence_bar"


def test_sensitive_action_allowed_at_high_confidence():
    engine = PolicyEngine(min_sensitive_confidence=0.75)
    decision = engine.evaluate(
        action=Action.SAVE_MEMORY.value,
        confidence_assessment=_OK,
        overall_confidence=0.9,
        contact_known=True,
    )
    assert decision.verdict == PolicyVerdict.ALLOW


def test_transfer_to_unknown_caller_hands_off():
    engine = PolicyEngine(min_sensitive_confidence=0.5)
    decision = engine.evaluate(
        action=Action.TRANSFER_CALL.value,
        confidence_assessment=_OK,
        overall_confidence=0.9,
        contact_known=False,
    )
    assert decision.verdict == PolicyVerdict.HANDOFF


def test_non_sensitive_action_allowed_regardless_of_contact():
    engine = PolicyEngine()
    decision = engine.evaluate(
        action=Action.ASK_CALLER_REASON.value,
        confidence_assessment=_OK,
        overall_confidence=0.4,
        contact_known=False,
    )
    assert decision.verdict == PolicyVerdict.ALLOW
