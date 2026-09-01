"""Canonical WOW Brain taxonomy: intents, context modes, structured actions,
and caller relationship types.

This is the single source of truth for these vocabularies. Every provider
(RuleBasedLanguageModelProvider, LocalWOWModelProvider, and any future
provider) and every training-time consumer (training/wow_taxonomy.py)
references these enums instead of hard-coding string literals.

Extending the taxonomy: add a new member to the relevant Enum and a
matching entry in its `*_DESCRIPTIONS` dict. Nothing else needs to change
for the registry itself to pick it up - callers that iterate the Enum or
the descriptions dict see new members automatically.
"""

from enum import Enum


class Intent(str, Enum):
    SET_CONTEXT = "SET_CONTEXT"
    CLEAR_CONTEXT = "CLEAR_CONTEXT"
    GET_CONTEXT = "GET_CONTEXT"
    CALL_PERSON = "CALL_PERSON"
    HANDLE_CALLS = "HANDLE_CALLS"
    UNKNOWN_CALLER = "UNKNOWN_CALLER"
    KNOWN_CALLER = "KNOWN_CALLER"
    URGENT_CALL = "URGENT_CALL"
    NON_URGENT_CALL = "NON_URGENT_CALL"
    MESSAGE_FOR_USER = "MESSAGE_FOR_USER"
    SCHEDULE_REQUEST = "SCHEDULE_REQUEST"
    CANCEL_REQUEST = "CANCEL_REQUEST"
    SUMMARIZE_CONVERSATION = "SUMMARIZE_CONVERSATION"
    END_CONVERSATION = "END_CONVERSATION"
    TRANSFER_TO_USER = "TRANSFER_TO_USER"
    GENERAL_CONVERSATION = "GENERAL_CONVERSATION"
    UNKNOWN = "UNKNOWN"


INTENT_DESCRIPTIONS: dict[Intent, str] = {
    Intent.SET_CONTEXT: "User is telling WOW to switch into a specific context/mode (sleeping, busy, meeting, etc).",
    Intent.CLEAR_CONTEXT: "User is telling WOW to leave the current context and return to normal/available.",
    Intent.GET_CONTEXT: "User is asking WOW what context/mode is currently active.",
    Intent.CALL_PERSON: "User is asking WOW to call or connect them to a specific person.",
    Intent.HANDLE_CALLS: "User is authorizing WOW to answer/handle incoming calls on their behalf.",
    Intent.UNKNOWN_CALLER: "The caller is not a recognized contact.",
    Intent.KNOWN_CALLER: "The caller is a recognized contact (family, friend, colleague, business contact).",
    Intent.URGENT_CALL: "The call/message has been identified as urgent and needs elevated attention.",
    Intent.NON_URGENT_CALL: "The call/message is not time-sensitive.",
    Intent.MESSAGE_FOR_USER: "The caller wants to leave a message for the user.",
    Intent.SCHEDULE_REQUEST: "The caller/user is requesting to schedule something (a call, meeting, callback).",
    Intent.CANCEL_REQUEST: "The caller/user is requesting to cancel something previously scheduled.",
    Intent.SUMMARIZE_CONVERSATION: "A request to produce a summary of the current or a past conversation.",
    Intent.END_CONVERSATION: "The conversation is being wrapped up / ended.",
    Intent.TRANSFER_TO_USER: "The call should be handed off to the actual user (human takeover).",
    Intent.GENERAL_CONVERSATION: "Ordinary conversational content with no specific actionable intent above.",
    Intent.UNKNOWN: "The system cannot confidently classify the input.",
}


class ContextMode(str, Enum):
    SLEEPING = "SLEEPING"
    BUSY = "BUSY"
    MEETING = "MEETING"
    TRAVELLING = "TRAVELLING"
    UNAVAILABLE = "UNAVAILABLE"
    CUSTOM = "CUSTOM"
    NORMAL = "NORMAL"


CONTEXT_DESCRIPTIONS: dict[ContextMode, str] = {
    ContextMode.SLEEPING: "User is asleep and does not want to be disturbed.",
    ContextMode.BUSY: "User is occupied and cannot take calls right now.",
    ContextMode.MEETING: "User is in a meeting.",
    ContextMode.TRAVELLING: "User is travelling and may have limited availability.",
    ContextMode.UNAVAILABLE: "User is generally unavailable, reason unspecified.",
    ContextMode.CUSTOM: "A user-defined context not covered by the standard modes.",
    ContextMode.NORMAL: "User is available as normal; no special handling active.",
}


class Action(str, Enum):
    ENABLE_CALL_ASSISTANT = "ENABLE_CALL_ASSISTANT"
    DISABLE_CALL_ASSISTANT = "DISABLE_CALL_ASSISTANT"
    SET_CONTEXT = "SET_CONTEXT"
    CLEAR_CONTEXT = "CLEAR_CONTEXT"
    ANSWER_CALL = "ANSWER_CALL"
    ASK_CALLER_REASON = "ASK_CALLER_REASON"
    COLLECT_MESSAGE = "COLLECT_MESSAGE"
    MARK_URGENT = "MARK_URGENT"
    TRANSFER_CALL = "TRANSFER_CALL"
    END_CALL = "END_CALL"
    SAVE_MEMORY = "SAVE_MEMORY"
    CREATE_SUMMARY = "CREATE_SUMMARY"
    NO_ACTION = "NO_ACTION"


ACTION_DESCRIPTIONS: dict[Action, str] = {
    Action.ENABLE_CALL_ASSISTANT: "Turn on WOW's call-handling automation.",
    Action.DISABLE_CALL_ASSISTANT: "Turn off WOW's call-handling automation.",
    Action.SET_CONTEXT: "Persist a new active context mode.",
    Action.CLEAR_CONTEXT: "Reset the active context back to normal.",
    Action.ANSWER_CALL: "Answer an incoming call on the user's behalf.",
    Action.ASK_CALLER_REASON: "Ask the caller why they are calling.",
    Action.COLLECT_MESSAGE: "Take a message from the caller for the user.",
    Action.MARK_URGENT: "Flag the current call/message as urgent.",
    Action.TRANSFER_CALL: "Hand the call over to the user directly.",
    Action.END_CALL: "End the current call.",
    Action.SAVE_MEMORY: "Persist a fact from this interaction to memory.",
    Action.CREATE_SUMMARY: "Generate a summary record of the conversation.",
    Action.NO_ACTION: "No action is required in response to this input.",
}


class CallerRelationship(str, Enum):
    FAMILY = "FAMILY"
    FRIEND = "FRIEND"
    COLLEAGUE = "COLLEAGUE"
    BUSINESS_CONTACT = "BUSINESS_CONTACT"
    UNKNOWN = "UNKNOWN"
    SPAM_SUSPICIOUS = "SPAM_SUSPICIOUS"


def is_valid_intent(name: str) -> bool:
    return name in Intent._value2member_map_


def is_valid_context(name: str) -> bool:
    return name in ContextMode._value2member_map_


def is_valid_action(name: str) -> bool:
    return name in Action._value2member_map_


def is_valid_relationship(name: str) -> bool:
    return name in CallerRelationship._value2member_map_
