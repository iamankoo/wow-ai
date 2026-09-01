"""Label validation against the WOW taxonomy (single source of truth:
backend/app/brain/taxonomy.py, re-exported via training/wow_taxonomy.py -
never a parallel label set), plus hard-negative-specific validation.
"""

from dataclasses import dataclass

from training.wow_taxonomy import is_valid_action, is_valid_context, is_valid_intent
from training.pipeline.schema import RawExample

# The confusable label pairs called out as priorities for hard-negative
# coverage - see docs/DATASET.md "Hard negatives".
CONFUSABLE_PAIRS = [
    "URGENT_CALL_vs_NON_URGENT_CALL",
    "KNOWN_CALLER_vs_UNKNOWN_CALLER",
    "SET_CONTEXT_vs_GENERAL_CONVERSATION",
    "GET_CONTEXT_vs_SET_CONTEXT",
    "END_CALL_vs_END_CONVERSATION",
    "MESSAGE_FOR_USER_vs_GENERAL_CONVERSATION",
    "CALL_PERSON_vs_HANDLE_CALLS",
    "CLEAR_CONTEXT_vs_DISABLE_CALL_ASSISTANT",
]

VALID_LANGUAGES = frozenset({"en", "hi", "hinglish"})


@dataclass
class LabelValidationResult:
    valid: bool
    errors: list[str]


def validate_labels(ex: RawExample) -> LabelValidationResult:
    errors = []
    if ex.language not in VALID_LANGUAGES:
        errors.append(f"invalid language '{ex.language}'")
    if not is_valid_intent(ex.intent):
        errors.append(f"invalid intent '{ex.intent}'")
    if ex.context_mode is not None and not is_valid_context(ex.context_mode):
        errors.append(f"invalid context_mode '{ex.context_mode}'")
    if ex.action is not None and not is_valid_action(ex.action):
        errors.append(f"invalid action '{ex.action}'")
    if not ex.text or not ex.text.strip():
        errors.append("blank text")
    return LabelValidationResult(valid=not errors, errors=errors)


def validate_hard_negative(ex: RawExample) -> LabelValidationResult:
    """A hard_negative=True example must declare which confusable pair it's
    targeting, and that pair must be a recognized one - otherwise it's just
    an unlabeled example with a flag set, which defeats the point (failure
    mining and dataset review both key off confusable_pair)."""
    if not ex.hard_negative:
        return LabelValidationResult(valid=True, errors=[])
    errors = []
    if not ex.confusable_pair:
        errors.append("hard_negative=True but confusable_pair is not set")
    elif ex.confusable_pair not in CONFUSABLE_PAIRS:
        errors.append(
            f"confusable_pair '{ex.confusable_pair}' is not in the recognized "
            f"CONFUSABLE_PAIRS list - add it there if this is a genuinely new pair"
        )
    if not ex.notes:
        errors.append("hard_negative=True but notes is empty - explain the trap")
    return LabelValidationResult(valid=not errors, errors=errors)
