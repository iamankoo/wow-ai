"""Deterministic yes/no confirmation matcher for the multi-turn
clarification loop (see docs "Clarification loop", `WowAgent.handle_input`).

Never a hosted LLM call - a small, fixed-vocabulary check, the same
"boring and testable" spirit as `PolicyEngine`/`ConfidencePolicy`: when a
turn ends in `PolicyVerdict.CLARIFY` with an actionable (just
under-confident) candidate action, the orchestrator remembers it as
`ConversationState.pending_action` and asks a clarifying question; the
*next* turn's reply is checked against this module before being sent back
to the brain, so a caller confirming or rejecting the suggestion is
handled deterministically rather than being re-classified from scratch.
"""

_AFFIRMATIVE = {
    "yes", "yeah", "yep", "yup", "correct", "right", "confirm", "confirmed",
    "sure", "ok", "okay", "affirmative", "do it", "please do", "go ahead",
    "thats right", "that's right",
}
_NEGATIVE = {
    "no", "nope", "nah", "cancel", "stop", "wrong", "incorrect", "negative",
    "not that", "dont", "don't", "never mind", "nevermind",
}


def interpret_confirmation(text: str | None) -> bool | None:
    """True if `text` reads as an affirmative confirmation, False if a
    clear rejection, None if neither (the caller said something else -
    treat this turn as a fresh, unrelated one rather than guessing)."""
    if not text:
        return None
    normalized = text.strip().lower().rstrip(".!? ")
    if normalized in _AFFIRMATIVE:
        return True
    if normalized in _NEGATIVE:
        return False
    first_word = normalized.split(" ", 1)[0]
    if first_word in _AFFIRMATIVE:
        return True
    if first_word in _NEGATIVE:
        return False
    return None
