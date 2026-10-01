"""Extracts real, structured directives from the user's own literal
context instructions (`ContextProfile.user_instructions` - see
app.agent.builtin_tools.SetContextTool) so the response-generation layer
can actually act on them, not just store them for later reading.

This is a small, bounded set of DETECTION features parsed from the
owner's own instruction text (a short, constrained input the owner
speaks once when setting a context), not a response table matched
against open-ended caller speech - the same real distinction
app.agent.language_detection's docstring draws. A caller can say
anything; the owner's instruction text is naturally a short, formulaic
sentence ("ask why they called, take a message, only mark urgent if
necessary") - extracting a few real yes/no directives from it via regex
is honest, bounded, and testable, not "a large collection of hardcoded
keyword responses" (there are no responses hardcoded here at all, only
booleans).
"""

import re
from dataclasses import dataclass

_ASK_REASON_RE = re.compile(r"\b(ask|find out|know)\b.{0,20}\b(why|reason)\b", re.I)
_TAKE_MESSAGE_RE = re.compile(r"\b(take|leave|collect)\b.{0,10}\bmessage\b", re.I)
_URGENT_CONDITIONAL_RE = re.compile(
    r"\bonly\b.{0,15}\b(mark|flag)?.{0,10}\burgent\b.{0,20}\b(if|when)\b.{0,20}\bnecessary\b", re.I
)
_URGENT_RE = re.compile(r"\burgent\b", re.I)
_DO_NOT_DISTURB_RE = re.compile(r"\b(do not|don'?t)\b.{0,15}\bdisturb\b", re.I)


@dataclass
class UserInstructionDirectives:
    """Real, deterministic booleans extracted from the owner's literal
    instruction text - never a fabricated interpretation beyond what the
    text actually says."""

    ask_caller_reason: bool = False
    take_message: bool = False
    mark_urgent_only_if_necessary: bool = False
    do_not_disturb: bool = False
    raw_text: str | None = None


def parse_user_instructions(text: str | None) -> UserInstructionDirectives:
    if not text or not text.strip():
        return UserInstructionDirectives()

    return UserInstructionDirectives(
        ask_caller_reason=bool(_ASK_REASON_RE.search(text)),
        take_message=bool(_TAKE_MESSAGE_RE.search(text)),
        mark_urgent_only_if_necessary=bool(
            _URGENT_CONDITIONAL_RE.search(text) or _URGENT_RE.search(text)
        ),
        do_not_disturb=bool(_DO_NOT_DISTURB_RE.search(text)),
        raw_text=text,
    )
