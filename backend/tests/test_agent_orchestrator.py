"""WowAgent (opt-in orchestrator) end-to-end tests using fakes for every
provider - no database required. See app/agent/orchestrator.py."""

from app.agent.orchestrator import WowAgent, build_default_tool_registry
from app.agent.summary_repository import InMemorySummaryRepository
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
) -> WowAgent:
    memory_store = memory_store or InMemoryMemoryStore()
    summary_repo = InMemorySummaryRepository()
    tools = build_default_tool_registry(memory_store, summary_repo)
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
