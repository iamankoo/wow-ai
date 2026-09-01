"""Phase 1 reference LanguageModelProvider implementation.

This is intentionally rule-based (keyword/pattern matching) rather than a
call to a hosted LLM: WOW AI's brain must not be architecturally tied to any
vendor's API. This provider is a real, working implementation of the
LanguageModelProvider contract - swap it for a self-hosted/fine-tuned model
later by implementing the same interface, with no changes required in
app/brain or app/api.
"""

import re

from app.brain.taxonomy import Action, ContextMode, Intent
from app.interfaces.llm import LanguageModelProvider, LLMMessage, LLMResponse

# Ordered list of (intent, pattern) - first match wins. This is the original
# Phase 1A demo intent set (call-answering conversational replies); kept
# unchanged so existing behavior/tests are unaffected.
_INTENT_PATTERNS: list[tuple[str, re.Pattern]] = [
    ("greeting", re.compile(r"\b(hi|hello|hey)\b", re.I)),
    (
        "take_message",
        re.compile(r"\b(leave|take|pass on)\b.*\bmessage\b|\btell\b.*\bthat\b", re.I),
    ),
    (
        "schedule_callback",
        re.compile(r"\b(call\s?back|schedule|reschedule|call me)\b", re.I),
    ),
    ("check_availability", re.compile(r"\b(available|free|busy|around)\b", re.I)),
    ("goodbye", re.compile(r"\b(bye|goodbye|talk later|hang up)\b", re.I)),
]

_INTENT_REPLIES = {
    "greeting": "Hello, this is WOW AI. How can I help you today?",
    "take_message": "Sure, I'll pass that message along as soon as they're available.",
    "schedule_callback": "I can arrange a callback - what time works best for you?",
    "check_availability": "They're not available right now, but I can take a message.",
    "goodbye": "Thanks for calling, have a great day!",
    "unknown": "I'm not sure I understood that - could you say it differently?",
}

# Independent pattern set for the WOW Brain taxonomy (backend/app/brain/taxonomy.py) -
# context/call-handling commands (Phase 1B). Kept separate from
# _INTENT_PATTERNS above so it never changes the original demo intent's
# behavior; used as the deterministic baseline compared against
# LocalWOWModelProvider in training/evaluation/evaluate.py.
_WOW_TAXONOMY_RULES: list[tuple[re.Pattern, Intent, ContextMode | None, Action]] = [
    (re.compile(r"\b(stop handling|mat sambhaalo|disable)\b.*\bcalls?\b", re.I),
     Intent.HANDLE_CALLS, None, Action.DISABLE_CALL_ASSISTANT),
    (re.compile(r"\b(handle (my |)calls?|sambhaal|call.?s sambhaal)\b", re.I),
     Intent.HANDLE_CALLS, None, Action.ENABLE_CALL_ASSISTANT),
    (re.compile(r"\b(sleep|sleeping|so raha|sona hai|neend)\b", re.I),
     Intent.SET_CONTEXT, ContextMode.SLEEPING, Action.SET_CONTEXT),
    (re.compile(r"\bmeeting\b", re.I),
     Intent.SET_CONTEXT, ContextMode.MEETING, Action.SET_CONTEXT),
    (re.compile(r"\b(travel|travelling|safar|flight)\b", re.I),
     Intent.SET_CONTEXT, ContextMode.TRAVELLING, Action.SET_CONTEXT),
    (re.compile(r"\bbusy\b", re.I),
     Intent.SET_CONTEXT, ContextMode.BUSY, Action.SET_CONTEXT),
    (re.compile(r"\b(normal|free now|available again|wapas normal)\b", re.I),
     Intent.CLEAR_CONTEXT, ContextMode.NORMAL, Action.CLEAR_CONTEXT),
    (re.compile(r"\b(urgent|emergency|turant|zaroori)\b", re.I),
     Intent.URGENT_CALL, None, Action.MARK_URGENT),
    (re.compile(r"\bsummary\b", re.I),
     Intent.SUMMARIZE_CONVERSATION, None, Action.CREATE_SUMMARY),
    (re.compile(r"\b(bye|goodbye|thanks.*bye)\b", re.I),
     Intent.END_CONVERSATION, None, Action.END_CALL),
]


class RuleBasedLanguageModelProvider(LanguageModelProvider):
    """Deterministic keyword-based intent classifier + canned response generator.

    Also exposes `classify_wow_taxonomy`, a second, independent keyword
    classifier over the WOW Brain taxonomy - used as the deterministic
    baseline in evaluation (see training/evaluation/evaluate.py). The two
    classifiers are kept fully separate so extending WOW-taxonomy coverage
    never changes the original demo intent's behavior.
    """

    async def generate(
        self, messages: list[LLMMessage], *, context: dict | None = None
    ) -> LLMResponse:
        last_user_message = next(
            (m.content for m in reversed(messages) if m.role == "user"), ""
        )
        intent = self._classify(last_user_message)
        reply = _INTENT_REPLIES[intent]

        wow_intent, wow_context, wow_action = self.classify_wow_taxonomy(last_user_message)

        return LLMResponse(
            content=reply,
            intent=intent,
            slots={
                "wow_context_mode": wow_context.value if wow_context else None,
                "wow_action": wow_action.value if wow_action else None,
            },
            metadata={
                "provider": "rule_based_v0",
                "wow_intent": wow_intent.value,
            },
        )

    @staticmethod
    def _classify(text: str) -> str:
        for intent, pattern in _INTENT_PATTERNS:
            if pattern.search(text):
                return intent
        return "unknown"

    @staticmethod
    def classify_wow_taxonomy(text: str) -> tuple[Intent, ContextMode | None, Action]:
        for pattern, intent, context_mode, action in _WOW_TAXONOMY_RULES:
            if pattern.search(text):
                return intent, context_mode, action
        return Intent.UNKNOWN, None, Action.NO_ACTION
