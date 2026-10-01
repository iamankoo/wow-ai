"""WowAgent (opt-in orchestrator) end-to-end tests using fakes for every
provider - no database required. See app/agent/orchestrator.py."""

from app.agent.context_profile_repository import InMemoryContextProfileRepository
from app.agent.orchestrator import WowAgent, build_default_tool_registry
from app.agent.summary_repository import InMemorySummaryRepository
from app.agent.user_settings_repository import InMemoryUserSettingsRepository
from app.brain.state_repository import InMemoryStateRepository
from app.interfaces.context_engine import ConversationContext
from app.interfaces.feedback import FeedbackRepository, FeedbackStatus, FeedbackSubmission
from app.interfaces.llm import LLMResponse
from app.learning.feedback_repository import InMemoryFeedbackRepository
from tests.agent_fakes import FakeContextEngine, FakeLLMProvider, InMemoryMemoryStore


def _agent(
    response: LLMResponse,
    *,
    memory_store: InMemoryMemoryStore | None = None,
    context: ConversationContext | None = None,
    feedback_repository: FeedbackRepository | None = None,
    context_profile_repository: InMemoryContextProfileRepository | None = None,
    user_settings_repository: InMemoryUserSettingsRepository | None = None,
) -> WowAgent:
    memory_store = memory_store or InMemoryMemoryStore()
    summary_repo = InMemorySummaryRepository()
    context_profile_repo = context_profile_repository or InMemoryContextProfileRepository()
    user_settings_repo = user_settings_repository or InMemoryUserSettingsRepository()
    tools = build_default_tool_registry(
        memory_store, summary_repo, context_profile_repo, user_settings_repo
    )
    return WowAgent(
        FakeLLMProvider(response),
        FakeContextEngine(context),
        InMemoryStateRepository(),
        tools,
        feedback_repository=feedback_repository,
    )


async def test_allowed_general_conversation_returns_llm_reply():
    response = LLMResponse(
        content="Hello! How can I help?", intent="GENERAL_CONVERSATION", slots={}, metadata={}
    )
    agent = _agent(response)
    action = await agent.handle_input(user_id="u1", text="hi", conversation_id="c1")
    assert action.type == "GENERAL_CONVERSATION"
    assert action.payload["reply"] == "Hello! How can I help?"
    assert action.payload["policy_decision"] == "allow"
    assert action.payload["turn_count"] == 1
    assert set(action.payload["durations_ms"]) >= {"context", "brain", "policy", "response"}


async def test_low_confidence_action_is_clarified_not_executed():
    memory_store = InMemoryMemoryStore()
    response = LLMResponse(
        content="",
        intent="SAVE_MEMORY_INTENT",
        slots={"action": "SAVE_MEMORY"},
        metadata={"confidence": {"intent": 0.9, "action": 0.2}},
    )
    agent = _agent(response, memory_store=memory_store)
    action = await agent.handle_input(
        user_id="u1", text="remember I like tea", conversation_id="c1"
    )
    assert action.payload["policy_decision"] == "clarify"
    assert action.payload["tool_results"] == []
    assert memory_store.records == []


async def test_high_confidence_save_memory_action_invokes_tool():
    memory_store = InMemoryMemoryStore()
    response = LLMResponse(
        content="",
        intent="SAVE_MEMORY_INTENT",
        slots={"action": "SAVE_MEMORY"},
        metadata={"confidence": {"intent": 0.95, "action": 0.9}},
    )
    agent = _agent(response, memory_store=memory_store)
    action = await agent.handle_input(
        user_id="u1", text="remember I like tea", conversation_id="c1"
    )
    assert action.payload["policy_decision"] == "allow"
    assert action.payload["tool_results"] == [
        {"tool": "save_memory", "success": True, "error": None}
    ]
    assert memory_store.records[0]["content"] == "remember I like tea"


async def test_unrecognized_action_from_model_is_never_trusted():
    response = LLMResponse(
        content="",
        intent="X",
        slots={"action": "DELETE_ALL_DATA"},
        metadata={"confidence": {"intent": 0.99, "action": 0.99}},
    )
    agent = _agent(response)
    action = await agent.handle_input(
        user_id="u1", text="do something dangerous", conversation_id="c1"
    )
    assert action.payload["candidate_action"] is None
    assert action.payload["tool_results"] == []


async def test_state_persists_turn_count_and_lifecycle_across_calls():
    response = LLMResponse(content="ok", intent="GENERAL_CONVERSATION", slots={}, metadata={})
    agent = _agent(response)
    first = await agent.handle_input(user_id="u1", text="hi", conversation_id="c1")
    second = await agent.handle_input(user_id="u1", text="hi again", conversation_id="c1")
    assert first.payload["turn_count"] == 1
    assert second.payload["turn_count"] == 2
    assert second.payload["lifecycle"] == "listening"


async def test_low_confidence_prediction_is_logged_to_review_queue():
    feedback_repo = InMemoryFeedbackRepository()
    response = LLMResponse(
        content="",
        intent="SET_CONTEXT",
        slots={"action": "SET_CONTEXT", "context_mode": "SLEEPING"},
        metadata={"confidence": {"intent": 0.42}},
    )
    agent = _agent(response, feedback_repository=feedback_repo)
    await agent.handle_input(user_id="u1", text="I'm sleeping.", conversation_id="c1")

    queue = await feedback_repo.list_by_status(FeedbackStatus.NEEDS_REVIEW, user_id="u1")
    assert len(queue) == 1
    assert queue[0].predicted_intent == "SET_CONTEXT"
    assert queue[0].predicted_context_mode == "SLEEPING"
    assert queue[0].intent_confidence == 0.42


async def test_high_confidence_prediction_is_not_logged_to_review_queue():
    feedback_repo = InMemoryFeedbackRepository()
    response = LLMResponse(
        content="ok", intent="GENERAL_CONVERSATION", slots={}, metadata={"confidence": {"intent": 0.95}}
    )
    agent = _agent(response, feedback_repository=feedback_repo)
    await agent.handle_input(user_id="u1", text="hi", conversation_id="c1")

    queue = await feedback_repo.list_by_status(FeedbackStatus.NEEDS_REVIEW, user_id="u1")
    assert queue == []


async def test_feedback_repository_failure_does_not_crash_the_turn():
    class BrokenFeedbackRepository(FeedbackRepository):
        async def create(self, submission: FeedbackSubmission):
            raise RuntimeError("db is down")

        async def get(self, feedback_id):
            raise NotImplementedError

        async def list_by_status(self, status, *, user_id=None):
            raise NotImplementedError

        async def list_by_user(self, user_id):
            raise NotImplementedError

        async def update(self, record):
            raise NotImplementedError

        async def delete(self, feedback_id):
            raise NotImplementedError

        async def delete_by_user(self, user_id, *, statuses=None):
            raise NotImplementedError

    response = LLMResponse(
        content="", intent="X", slots={}, metadata={"confidence": {"intent": 0.1}}
    )
    agent = _agent(response, feedback_repository=BrokenFeedbackRepository())
    action = await agent.handle_input(user_id="u1", text="test", conversation_id="c1")
    assert action.payload["turn_count"] == 1  # the turn still completed normally


async def test_no_feedback_repository_configured_is_a_no_op():
    response = LLMResponse(
        content="", intent="X", slots={}, metadata={"confidence": {"intent": 0.1}}
    )
    agent = _agent(response)  # feedback_repository=None, the default
    action = await agent.handle_input(user_id="u1", text="test", conversation_id="c1")
    assert action.payload["turn_count"] == 1


async def test_high_confidence_set_context_action_activates_a_profile():
    ctx_repo = InMemoryContextProfileRepository()
    response = LLMResponse(
        content="",
        intent="SET_CONTEXT",
        slots={"action": "SET_CONTEXT", "context_mode": "MEETING"},
        metadata={"confidence": {"intent": 0.95, "action": 0.9, "context_mode": 0.92}},
    )
    agent = _agent(response, context_profile_repository=ctx_repo)
    action = await agent.handle_input(
        user_id="u1", text="I'm in a meeting, handle my calls", conversation_id="c1"
    )
    assert action.payload["policy_decision"] == "allow"
    assert action.payload["tool_results"] == [
        {"tool": "set_context", "success": True, "error": None}
    ]
    assert ctx_repo.active_name(user_id="u1") == "MEETING"


async def test_set_context_action_captures_the_full_turn_text_as_user_instructions():
    ctx_repo = InMemoryContextProfileRepository()
    response = LLMResponse(
        content="",
        intent="SET_CONTEXT",
        slots={"action": "SET_CONTEXT", "context_mode": "SLEEPING"},
        metadata={"confidence": {"intent": 0.95, "action": 0.9, "context_mode": 0.92}},
    )
    agent = _agent(response, context_profile_repository=ctx_repo)
    text = "I am sleeping. Ask why they called, take a message, only mark it urgent if necessary."

    await agent.handle_input(user_id="u1", text=text, conversation_id="c1")

    assert ctx_repo.active_user_instructions(user_id="u1") == text


async def test_confirmed_set_context_captures_the_original_turn_s_text_not_the_confirmation_word():
    """The turn that actually confirms a clarified SET_CONTEXT just says
    "yes" - the caller's real instructions were on the *first* turn. The
    tool must receive that original wording, not the word "yes"."""
    ctx_repo = InMemoryContextProfileRepository()
    response = LLMResponse(
        content="",
        intent="SET_CONTEXT",
        slots={"action": "SET_CONTEXT", "context_mode": "MEETING"},
        metadata={"confidence": {"intent": 0.9, "action": 0.5, "context_mode": 0.9}},
    )
    agent = _agent(response, context_profile_repository=ctx_repo)
    original_text = "I'm in a meeting, take a message and only interrupt me if it's urgent"

    await agent.handle_input(user_id="u1", text=original_text, conversation_id="c1")
    await agent.handle_input(user_id="u1", text="yes", conversation_id="c1")

    assert ctx_repo.active_user_instructions(user_id="u1") == original_text


async def test_set_context_action_without_a_context_mode_fails_cleanly():
    ctx_repo = InMemoryContextProfileRepository()
    response = LLMResponse(
        content="",
        intent="SET_CONTEXT",
        slots={"action": "SET_CONTEXT"},  # no context_mode slot predicted
        metadata={"confidence": {"intent": 0.95, "action": 0.9}},
    )
    agent = _agent(response, context_profile_repository=ctx_repo)
    action = await agent.handle_input(user_id="u1", text="set my context", conversation_id="c1")
    assert action.payload["tool_results"] == [
        {"tool": "set_context", "success": False, "error": "no_context_mode"}
    ]
    assert ctx_repo.active_name(user_id="u1") is None


async def test_high_confidence_collect_message_action_saves_it():
    memory_store = InMemoryMemoryStore()
    response = LLMResponse(
        content="",
        intent="MESSAGE_FOR_USER",
        slots={"action": "COLLECT_MESSAGE"},
        metadata={"confidence": {"intent": 0.9, "action": 0.9}},
    )
    agent = _agent(response, memory_store=memory_store)
    action = await agent.handle_input(
        user_id="u1", text="Tell him I'll call back tonight", conversation_id="c1"
    )
    assert action.payload["tool_results"] == [
        {"tool": "collect_message", "success": True, "error": None}
    ]
    assert memory_store.records[0]["content"] == "Tell him I'll call back tonight"


async def test_high_confidence_enable_call_assistant_action_sets_the_flag():
    user_settings = InMemoryUserSettingsRepository()
    response = LLMResponse(
        content="",
        intent="HANDLE_CALLS",
        slots={"action": "ENABLE_CALL_ASSISTANT"},
        metadata={"confidence": {"intent": 0.9, "action": 0.9}},
    )
    agent = _agent(response, user_settings_repository=user_settings)
    action = await agent.handle_input(
        user_id="u1", text="Please handle my calls from now on", conversation_id="c1"
    )
    assert action.payload["tool_results"] == [
        {"tool": "enable_call_assistant", "success": True, "error": None}
    ]
    assert user_settings.is_enabled(user_id="u1") is True


async def test_ask_caller_reason_action_gets_a_real_question_not_a_generic_fallback():
    response = LLMResponse(
        content="",  # LocalWOWModelProvider-shaped: predicts structure, not free text
        intent="GENERAL_CONVERSATION",
        slots={"action": "ASK_CALLER_REASON"},
        metadata={"confidence": {"intent": 0.9, "action": 0.9}},
    )
    agent = _agent(response)
    action = await agent.handle_input(user_id="u1", text="Hello?", conversation_id="c1")
    assert action.payload["policy_decision"] == "allow"
    assert action.payload["tool_results"] == []  # no tool - purely conversational
    assert action.payload["reply"] == "Could you tell me the reason for your call?"


async def test_low_confidence_actionable_prediction_is_confirmed_on_the_next_turn():
    ctx_repo = InMemoryContextProfileRepository()
    response = LLMResponse(
        content="",
        intent="SET_CONTEXT",
        slots={"action": "SET_CONTEXT", "context_mode": "MEETING"},
        # action confidence (0.5) is below the 0.6 threshold - triggers CLARIFY.
        metadata={"confidence": {"intent": 0.9, "action": 0.5, "context_mode": 0.9}},
    )
    agent = _agent(response, context_profile_repository=ctx_repo)

    first = await agent.handle_input(
        user_id="u1", text="I'm in a meeting", conversation_id="c1"
    )
    assert first.payload["policy_decision"] == "clarify"
    assert first.payload["tool_results"] == []
    assert ctx_repo.active_name(user_id="u1") is None  # not executed yet

    second = await agent.handle_input(user_id="u1", text="yes", conversation_id="c1")
    assert second.payload["policy_decision"] == "allow"
    assert second.payload["tool_results"] == [
        {"tool": "set_context", "success": True, "error": None}
    ]
    assert second.payload["reply"] == "Got it - I've taken care of that."
    assert ctx_repo.active_name(user_id="u1") == "MEETING"


async def test_low_confidence_actionable_prediction_is_cancelled_on_the_next_turn():
    ctx_repo = InMemoryContextProfileRepository()
    response = LLMResponse(
        content="",
        intent="SET_CONTEXT",
        slots={"action": "SET_CONTEXT", "context_mode": "MEETING"},
        metadata={"confidence": {"intent": 0.9, "action": 0.5, "context_mode": 0.9}},
    )
    agent = _agent(response, context_profile_repository=ctx_repo)

    await agent.handle_input(user_id="u1", text="I'm in a meeting", conversation_id="c1")
    second = await agent.handle_input(user_id="u1", text="no", conversation_id="c1")

    assert second.type == "clarification_cancelled"
    assert second.payload["reply"] == "Okay, I won't do that."
    assert second.payload["tool_results"] == []
    assert ctx_repo.active_name(user_id="u1") is None  # never executed


async def test_cancelling_a_pending_action_does_not_reach_the_brain_again():
    call_count = {"n": 0}
    response = LLMResponse(
        content="",
        intent="SET_CONTEXT",
        slots={"action": "SET_CONTEXT", "context_mode": "MEETING"},
        metadata={"confidence": {"intent": 0.9, "action": 0.5, "context_mode": 0.9}},
    )

    class CountingLLMProvider:
        async def generate(self, messages, *, context=None):
            call_count["n"] += 1
            return response

    memory_store = InMemoryMemoryStore()
    tools = build_default_tool_registry(
        memory_store,
        InMemorySummaryRepository(),
        InMemoryContextProfileRepository(),
        InMemoryUserSettingsRepository(),
    )
    agent = WowAgent(
        CountingLLMProvider(), FakeContextEngine(), InMemoryStateRepository(), tools
    )

    await agent.handle_input(user_id="u1", text="I'm in a meeting", conversation_id="c1")
    assert call_count["n"] == 1
    await agent.handle_input(user_id="u1", text="no", conversation_id="c1")
    assert call_count["n"] == 1  # the cancel fast path never called generate() again


async def test_unrelated_reply_to_a_pending_action_reprocesses_fresh_instead_of_guessing():
    ctx_repo = InMemoryContextProfileRepository()
    response = LLMResponse(
        content="",
        intent="SET_CONTEXT",
        slots={"action": "SET_CONTEXT", "context_mode": "MEETING"},
        metadata={"confidence": {"intent": 0.9, "action": 0.5, "context_mode": 0.9}},
    )
    agent = _agent(response, context_profile_repository=ctx_repo)

    await agent.handle_input(user_id="u1", text="I'm in a meeting", conversation_id="c1")
    # Not a yes/no - the stale suggestion is abandoned and this is processed
    # as its own fresh turn (still CLARIFY here, since the fake LLM always
    # returns the same low-confidence response - the point is it went back
    # through the brain rather than being force-matched as a confirmation).
    second = await agent.handle_input(
        user_id="u1", text="also tell John I called", conversation_id="c1"
    )
    assert second.type != "clarification_cancelled"
    assert second.payload["policy_decision"] == "clarify"
    assert second.payload["tool_results"] == []
    assert ctx_repo.active_name(user_id="u1") is None


async def test_unknown_caller_transfer_request_hands_off():
    response = LLMResponse(
        content="",
        intent="TRANSFER_TO_USER",
        slots={"action": "TRANSFER_CALL"},
        metadata={"confidence": {"intent": 0.95, "action": 0.95}},
    )
    agent = _agent(response, context=ConversationContext(user_id="u1", contact=None))
    action = await agent.handle_input(
        user_id="u1", text="put me through to him now", conversation_id="c1"
    )
    assert action.payload["policy_decision"] == "handoff"


# --- Context instructions actually influence caller handling (real, not
# just stored - see app/agent/response.py's _compose_contextual_reply) ---


async def _general_conversation_agent(context_profile: dict | None):
    """A caller's ordinary turn with no specific classified action (Brain
    v3-shaped: empty content, GENERAL_CONVERSATION intent, no action
    slot) while `context_profile` is active - the real scenario this
    round's context-instructions-execution fix targets."""
    response = LLMResponse(content="", intent="GENERAL_CONVERSATION", slots={}, metadata={})
    context = ConversationContext(user_id="u1", contact=None, context_profile=context_profile)
    return _agent(response, context=context)


async def test_active_context_with_literal_instructions_changes_the_reply():
    """The whole point of this round: the SAME caller turn gets a
    DIFFERENT reply depending on the owner's literal instructions -
    proving they actually drive behavior, not just sit in Postgres."""
    with_ask_reason = await _general_conversation_agent(
        {
            "name": "SLEEPING",
            "instructions": "User is asleep and does not want to be disturbed.",
            "user_instructions": "Ask why they called, take a message, only mark urgent if necessary.",
        }
    )
    plain = await _general_conversation_agent(
        {
            "name": "SLEEPING",
            "instructions": "User is asleep and does not want to be disturbed.",
            "user_instructions": None,
        }
    )

    reply_with_instructions = (
        await with_ask_reason.handle_input(user_id="u1", text="Hi, is Aniket there?", conversation_id="c1")
    ).payload["reply"]
    reply_plain = (
        await plain.handle_input(user_id="u1", text="Hi, is Aniket there?", conversation_id="c1")
    ).payload["reply"]

    assert reply_with_instructions != reply_plain
    assert "what this is about" in reply_with_instructions.lower()
    assert "asleep" in reply_with_instructions.lower()


async def test_no_active_context_still_uses_the_old_generic_fallback():
    """Regression check: when there's genuinely no active context, behavior
    is unchanged from before this round."""
    agent = await _general_conversation_agent(None)
    reply = (
        await agent.handle_input(user_id="u1", text="Hi, is Aniket there?", conversation_id="c1")
    ).payload["reply"]
    assert "not sure how to respond" in reply.lower()


# --- Multilingual response selection (new this round) ---


async def test_hindi_language_produces_a_real_hindi_reply():
    agent = await _general_conversation_agent({"name": "SLEEPING", "user_instructions": None})
    action = await agent.handle_input(
        user_id="u1", text="नमस्ते, अनिकेत से बात हो सकती है?", conversation_id="c1", language="hi"
    )
    assert action.payload["language"] == "hi"
    assert "सो रहे" in action.payload["reply"]


async def test_hinglish_language_produces_a_real_hinglish_reply():
    agent = await _general_conversation_agent({"name": "SLEEPING", "user_instructions": None})
    action = await agent.handle_input(
        user_id="u1",
        text="Hi, Aniket se baat karni thi",
        conversation_id="c1",
        language="hi-Latn",
    )
    assert action.payload["language"] == "hi-Latn"
    assert "so rahe" in action.payload["reply"].lower()


async def test_english_language_produces_a_real_english_reply():
    agent = await _general_conversation_agent({"name": "SLEEPING", "user_instructions": None})
    action = await agent.handle_input(
        user_id="u1", text="Can you ask Aniket to call me back?", conversation_id="c1", language="en"
    )
    assert action.payload["language"] == "en"
    assert "asleep" in action.payload["reply"].lower()


async def test_language_switches_mid_call_turn_by_turn():
    """The same conversation, same ConversationState/session, must follow
    the caller's language turn by turn - never locked to the first turn's
    language."""
    agent = await _general_conversation_agent({"name": "MEETING", "user_instructions": None})

    hindi_turn = await agent.handle_input(
        user_id="u1", text="अनिकेत से बात हो सकती है?", conversation_id="c1", language="hi"
    )
    english_turn = await agent.handle_input(
        user_id="u1", text="Can you ask him to call me back?", conversation_id="c1", language="en"
    )
    hinglish_turn = await agent.handle_input(
        user_id="u1", text="Achha, theek hai, bol dena", conversation_id="c1", language="hi-Latn"
    )

    assert hindi_turn.payload["language"] == "hi"
    assert english_turn.payload["language"] == "en"
    assert hinglish_turn.payload["language"] == "hi-Latn"
    replies = {hindi_turn.payload["reply"], english_turn.payload["reply"], hinglish_turn.payload["reply"]}
    assert len(replies) == 3  # genuinely different text per language, not one fixed reply
