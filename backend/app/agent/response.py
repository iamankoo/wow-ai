"""Minimal response-generation layer (see docs "Reasoning / response
generation").

A LanguageModelProvider produces intent/action *structure*, not always a
natural reply - `LocalWOWModelProvider` deliberately returns `content=""`
("predicts structure, not free text"). This module is the seam that turns
(model content, policy verdict, tool outcome) into the text WOW actually
says, kept separate from orchestration so reply phrasing can change without
touching orchestration logic.

Phase 1 scope, stated plainly: English template fallbacks only. Real
Hindi/Hinglish generation needs either a fine-tuned generator or a much
larger phrase bank than would be honest to claim as finished here - see
README "Current limitations". This module raises no error and never
fabricates fluent Hindi/Hinglish it cannot actually produce.
"""

from app.agent.policy import PolicyVerdict

_FALLBACK_TEMPLATES: dict[PolicyVerdict, str] = {
    PolicyVerdict.CLARIFY: "Sorry, I didn't quite catch that - could you say it again?",
    PolicyVerdict.REFUSE: "I'm not able to do that right now.",
    PolicyVerdict.HANDOFF: "Let me make sure the right person gets back to you on that.",
}

_DEFAULT_FALLBACK = "I heard you, but I'm not sure how to respond to that yet."
_TOOL_FAILURE_FALLBACK = "I tried to do that, but something went wrong on my end - could you try again?"
_CONFIRMED_FALLBACK = "Got it - I've taken care of that."

# Used directly by the orchestrator's clarification-cancellation fast path
# (a caller rejecting a pending_action never reaches generate_response at
# all - see WowAgent.handle_input), exported here so every user-facing
# reply string lives in this one module.
CANCELLED_ACKNOWLEDGEMENT = "Okay, I won't do that."

# Per-action fallback templates for ALLOW-verdict actions that have no tool
# (see orchestrator._ACTION_TOOL_MAP) because they carry no store side
# effect - the action itself *is* the reply, not a database write.
# ASK_CALLER_REASON is the only such action today; NO_ACTION deliberately
# has none (silence/the model's own content is correct for it).
_ACTION_TEMPLATES: dict[str, str] = {
    "ASK_CALLER_REASON": "Could you tell me the reason for your call?",
}


def generate_response(
    *,
    llm_content: str | None,
    verdict: PolicyVerdict,
    tool_failed: bool = False,
    action: str | None = None,
    confirmed: bool = False,
) -> str:
    """Pick the text WOW actually says for this turn.

    An ALLOW-verdict reply from the language model provider wins when it
    said anything at all; otherwise fall back, in order, to: a fixed
    acknowledgement if this turn executed a previously-clarified action the
    caller just confirmed (`confirmed=True` - see the multi-turn
    clarification loop in `WowAgent.handle_input`), an action-specific
    template if one exists, then the generic default - so the caller
    always hears something coherent, never raw structure or a blank
    string.
    """
    if verdict == PolicyVerdict.ALLOW:
        if tool_failed:
            return _TOOL_FAILURE_FALLBACK
        if llm_content:
            return llm_content
        if confirmed:
            return _CONFIRMED_FALLBACK
        if action and action in _ACTION_TEMPLATES:
            return _ACTION_TEMPLATES[action]
        return _DEFAULT_FALLBACK
    return _FALLBACK_TEMPLATES.get(verdict, _DEFAULT_FALLBACK)
