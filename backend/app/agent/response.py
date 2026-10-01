"""Response-generation layer (see docs "Reasoning / response generation").

A LanguageModelProvider produces intent/action *structure*, not always a
natural reply - `LocalWOWModelProvider` deliberately returns `content=""`
("predicts structure, not free text"). This module is the seam that turns
(model content, policy verdict, tool outcome, active context, detected
language) into the text WOW actually says, kept separate from
orchestration so reply phrasing can change without touching orchestration
logic.

Multilingual scope, stated plainly (see docs/ARCHITECTURE.md "Multilingual
conversation" for the full picture): this module's Hindi/Hinglish output
is a curated, bounded phrase bank covering the specific templates below -
real, tested, and genuinely different per detected language, but still
fundamentally template composition, not free generation. It never claims
more fluency than these phrases actually have, and it never fabricates a
reply for a situation none of these templates cover - `llm_content`
(whatever the active LanguageModelProvider actually produced) always wins
outright when present, in whatever language it happens to be in.

New in this round: when an ALLOW-verdict conversational turn has no more
specific reply (no llm_content, not a confirmation, no action template)
but there IS an active context profile, `generate_response` composes a
real, context-grounded reply instead of the old generic
"I heard you, but I'm not sure how to respond to that yet." fallback -
reflecting the active context mode (sleeping/busy/meeting/...) and the
user's own literal instructions (app.agent.user_instructions), not just
storing them unused. See WowAgent.handle_input for how `active_context_profile`
reaches here (the same ContextEngine.build_context() result already used
elsewhere - not a new read path).
"""

from app.agent.policy import PolicyVerdict
from app.agent.user_instructions import parse_user_instructions

_SUPPORTED_LANGUAGES = ("en", "hi", "hi-Latn")
_DEFAULT_LANGUAGE = "en"


def _lang(language: str | None) -> str:
    return language if language in _SUPPORTED_LANGUAGES else _DEFAULT_LANGUAGE


_FALLBACK_TEMPLATES: dict[PolicyVerdict, dict[str, str]] = {
    PolicyVerdict.CLARIFY: {
        "en": "Sorry, I didn't quite catch that - could you say it again?",
        "hi": "माफ़ कीजिए, मैं समझ नहीं पाया - क्या आप दोबारा कह सकते हैं?",
        "hi-Latn": "Sorry, main samajh nahi paaya - kya aap dobara keh sakte hain?",
    },
    PolicyVerdict.REFUSE: {
        "en": "I'm not able to do that right now.",
        "hi": "मैं अभी यह नहीं कर सकता।",
        "hi-Latn": "Main abhi yeh nahi kar sakta.",
    },
    PolicyVerdict.HANDOFF: {
        "en": "Let me make sure the right person gets back to you on that.",
        "hi": "मैं सुनिश्चित करूँगा कि सही व्यक्ति आपसे संपर्क करे।",
        "hi-Latn": "Main make sure karunga ki sahi vyakti aapse contact kare.",
    },
}

_DEFAULT_FALLBACK = {
    "en": "I heard you, but I'm not sure how to respond to that yet.",
    "hi": "मैंने सुना, लेकिन मुझे नहीं पता कि इसका जवाब कैसे दूँ।",
    "hi-Latn": "Maine suna, lekin mujhe nahi pata ki iska jawaab kaise doon.",
}
_TOOL_FAILURE_FALLBACK = {
    "en": "I tried to do that, but something went wrong on my end - could you try again?",
    "hi": "मैंने कोशिश की, लेकिन कुछ गड़बड़ हो गई - क्या आप दोबारा कोशिश कर सकते हैं?",
    "hi-Latn": "Maine koshish ki, lekin kuch gadbad ho gayi - kya aap dobara try kar sakte hain?",
}
_CONFIRMED_FALLBACK = {
    "en": "Got it - I've taken care of that.",
    "hi": "ठीक है, मैंने वो कर दिया है।",
    "hi-Latn": "Theek hai, maine woh kar diya hai.",
}

# Used directly by the orchestrator's clarification-cancellation fast path
# (a caller rejecting a pending_action never reaches generate_response at
# all - see WowAgent.handle_input), exported here so every user-facing
# reply string lives in this one module. Left English-only, narrow scope:
# see docs/ARCHITECTURE.md "Multilingual conversation" limitations.
CANCELLED_ACKNOWLEDGEMENT = "Okay, I won't do that."

# Per-action fallback templates for ALLOW-verdict actions that have no tool
# (see orchestrator._ACTION_TOOL_MAP) because they carry no store side
# effect - the action itself *is* the reply, not a database write.
# ASK_CALLER_REASON is the only such action today; NO_ACTION deliberately
# has none (silence/the model's own content is correct for it).
_ACTION_TEMPLATES: dict[str, dict[str, str]] = {
    "ASK_CALLER_REASON": {
        "en": "Could you tell me the reason for your call?",
        "hi": "क्या आप मुझे बता सकते हैं कि आपने किस बारे में कॉल किया है?",
        "hi-Latn": "Kya aap mujhe bata sakte hain aapne kis baare mein call kiya hai?",
    },
}

# --- Context-aware conversational composition (new this round) ---

_UNAVAILABLE_BY_MODE: dict[str, dict[str, str]] = {
    "SLEEPING": {
        "en": "They're asleep right now.",
        "hi": "वो अभी सो रहे हैं।",
        "hi-Latn": "Woh abhi so rahe hain.",
    },
    "BUSY": {
        "en": "They're busy right now.",
        "hi": "वो अभी व्यस्त हैं।",
        "hi-Latn": "Woh abhi busy hain.",
    },
    "MEETING": {
        "en": "They're in a meeting right now.",
        "hi": "वो अभी मीटिंग में हैं।",
        "hi-Latn": "Woh abhi meeting mein hain.",
    },
    "TRAVELLING": {
        "en": "They're travelling right now.",
        "hi": "वो अभी यात्रा पर हैं।",
        "hi-Latn": "Woh abhi travel par hain.",
    },
}
_UNAVAILABLE_DEFAULT = {
    "en": "They're not available right now.",
    "hi": "वो अभी उपलब्ध नहीं हैं।",
    "hi-Latn": "Woh abhi available nahi hain.",
}
_ASK_REASON_PHRASE = {
    "en": "Can I ask what this is about?",
    "hi": "क्या मैं जान सकता हूँ आप किस बारे में बात करना चाहते हैं?",
    "hi-Latn": "Kya main jaan sakta hoon aap kis baare mein baat karna chahte hain?",
}
_GENERIC_HELP_PHRASE = {
    "en": "Can I help you with something?",
    "hi": "क्या मैं आपकी किसी तरह मदद कर सकता हूँ?",
    "hi-Latn": "Kya main aapki kisi tarah madad kar sakta hoon?",
}


def _compose_contextual_reply(
    active_context_profile: dict, language: str | None
) -> str:
    """The real, new-this-round piece: a caller's ordinary conversational
    turn (no specific action, no model-generated content) while a context
    is active gets a reply that actually reflects (a) the active context
    mode and (b) the owner's own literal instructions
    (`app.agent.user_instructions`) - not the old generic "I heard you..."
    fallback, and not the instructions sitting unused in Postgres."""
    lang = _lang(language)
    mode = (active_context_profile or {}).get("name")
    unavailable = _UNAVAILABLE_BY_MODE.get(mode or "", _UNAVAILABLE_DEFAULT).get(
        lang, _UNAVAILABLE_DEFAULT[lang]
    )

    directives = parse_user_instructions((active_context_profile or {}).get("user_instructions"))
    follow_up = _ASK_REASON_PHRASE[lang] if directives.ask_caller_reason else _GENERIC_HELP_PHRASE[lang]

    return f"{unavailable} {follow_up}"


def generate_response(
    *,
    llm_content: str | None,
    verdict: PolicyVerdict,
    tool_failed: bool = False,
    action: str | None = None,
    confirmed: bool = False,
    language: str | None = None,
    active_context_profile: dict | None = None,
) -> str:
    """Pick the text WOW actually says for this turn.

    An ALLOW-verdict reply from the language model provider wins when it
    said anything at all; otherwise fall back, in order, to: a fixed
    acknowledgement if this turn executed a previously-clarified action the
    caller just confirmed (`confirmed=True` - see the multi-turn
    clarification loop in `WowAgent.handle_input`), an action-specific
    template if one exists, a context-aware composed reply if a context
    profile is active (new this round - see `_compose_contextual_reply`),
    then the generic default - so the caller always hears something
    coherent, never raw structure or a blank string.

    `language` (one of "en"/"hi"/"hi-Latn", from
    app.agent.language_detection - anything else, including None,
    defaults to "en") selects which of this module's curated phrase-bank
    entries is used for every template path, not just the new contextual
    one - existing English-only callers (language=None) see byte-identical
    output to before this round.
    """
    lang = _lang(language)
    if verdict == PolicyVerdict.ALLOW:
        if tool_failed:
            return _TOOL_FAILURE_FALLBACK[lang]
        if llm_content:
            return llm_content
        if confirmed:
            return _CONFIRMED_FALLBACK[lang]
        if action and action in _ACTION_TEMPLATES:
            return _ACTION_TEMPLATES[action][lang]
        if active_context_profile:
            return _compose_contextual_reply(active_context_profile, lang)
        return _DEFAULT_FALLBACK[lang]
    return _FALLBACK_TEMPLATES.get(verdict, {}).get(lang, _DEFAULT_FALLBACK[lang])
