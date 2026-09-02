"""Safety/policy engine: the gate between a WOW Brain decision and any tool
execution or externally-visible action (see docs "Safety / policy engine").

A WOW Brain prediction is a *candidate*, never automatically authorized.
`PolicyEngine.evaluate` is a small, deterministic, fully unit-testable
function of (candidate action, model confidence, caller-identity certainty)
- never a hosted LLM call, and never fooled by a model claiming high
confidence for an action outside the known taxonomy.
"""

from dataclasses import dataclass
from enum import Enum

from app.brain.taxonomy import Action
from app.learning.confidence import ConfidenceAssessment

# Actions that mutate durable state or reach outside the current turn -
# these require a higher confidence bar and/or a known caller than purely
# conversational actions (ASK_CALLER_REASON, NO_ACTION, ...).
SENSITIVE_ACTIONS: frozenset[Action] = frozenset(
    {
        Action.SAVE_MEMORY,
        Action.SET_CONTEXT,
        Action.CLEAR_CONTEXT,
        Action.ENABLE_CALL_ASSISTANT,
        Action.DISABLE_CALL_ASSISTANT,
        Action.TRANSFER_CALL,
        Action.MARK_URGENT,
    }
)


class PolicyVerdict(str, Enum):
    ALLOW = "allow"
    CLARIFY = "clarify"
    REFUSE = "refuse"
    HANDOFF = "handoff"


@dataclass
class PolicyDecision:
    verdict: PolicyVerdict
    reason: str
    action: str | None = None


class PolicyEngine:
    def __init__(self, *, min_sensitive_confidence: float = 0.75):
        self._min_sensitive_confidence = min_sensitive_confidence

    def evaluate(
        self,
        *,
        action: str | None,
        confidence_assessment: ConfidenceAssessment,
        overall_confidence: float | None,
        contact_known: bool,
    ) -> PolicyDecision:
        if action is None or action == Action.NO_ACTION.value:
            return PolicyDecision(
                verdict=PolicyVerdict.ALLOW, reason="no_action_requested", action=action
            )

        if confidence_assessment.needs_review:
            return PolicyDecision(
                verdict=PolicyVerdict.CLARIFY,
                reason="low_confidence:" + ",".join(confidence_assessment.low_confidence_heads),
                action=action,
            )

        try:
            action_enum = Action(action)
        except ValueError:
            # The model predicted something outside the known taxonomy -
            # never trust that as an authorized action, regardless of its
            # reported confidence.
            return PolicyDecision(
                verdict=PolicyVerdict.CLARIFY, reason="unrecognized_action", action=action
            )

        if action_enum in SENSITIVE_ACTIONS:
            if (
                overall_confidence is not None
                and overall_confidence < self._min_sensitive_confidence
            ):
                return PolicyDecision(
                    verdict=PolicyVerdict.CLARIFY,
                    reason="sensitive_action_below_confidence_bar",
                    action=action,
                )
            if action_enum == Action.TRANSFER_CALL and not contact_known:
                return PolicyDecision(
                    verdict=PolicyVerdict.HANDOFF,
                    reason="unknown_caller_requesting_sensitive_transfer",
                    action=action,
                )

        return PolicyDecision(verdict=PolicyVerdict.ALLOW, reason="within_policy", action=action)
