"""WowAgent (opt-in orchestrator) end-to-end tests using fakes for every
provider - no database required. See app/agent/orchestrator.py."""

from app.agent.orchestrator import WowAgent, build_default_tool_registry
from app.agent.summary_repository import InMemorySummaryRepository
from app.brain.state_repository import InMemoryStateRepository
from app.interfaces.context_engine import ContextEngine, ConversationContext
from app.interfaces.llm import LanguageModelProvider, LLMResponse
from app.interfaces.memory_store import MemoryRecord, MemoryStatus, MemoryStore, MemoryType


class FakeContextEngine(ContextEngine):
    def __init__(self, context: ConversationContext | None = None):
        self._context = context or ConversationContext(user_id="u1")

    async def build_context(self, *, user_id, caller_number=None, conversation_id=None):
        return self._context


class InMemoryMemoryStore(MemoryStore):
    """Test double - no database required."""

    def __init__(self):
        self.records: list[dict] = []

    async def add(
        self,
        *,
        user_id,
        content,
        contact_id=None,
        embedding=None,
        source_type="manual",
        source_id=None,
        memory_type=MemoryType.SEMANTIC,
        status=MemoryStatus.OBSERVED,
        confidence=None,
    ) -> str:
        record_id = str(len(self.records) + 1)
        self.records.append(
            {
                "id": record_id,
                "user_id": user_id,
                "content": content,
                "contact_id": contact_id,
                "source_type": source_type,
                "memory_type": memory_type,
                "status": status,
                "confidence": confidence,
                "deleted": False,
            }
        )
        return record_id

    async def search(
        self,
        *,
        user_id,
        query,
        query_embedding=None,
        top_k=5,
        memory_type=None,
        include_deleted=False,
    ):
        matches = [
            r
            for r in self.records
            if r["user_id"] == user_id
            and (include_deleted or not r["deleted"])
            and (memory_type is None or r["memory_type"] == memory_type)
        ]
        return [MemoryRecord(id=r["id"], content=r["content"]) for r in matches[:top_k]]

    async def delete(self, *, user_id, memory_id) -> bool:
        for r in self.records:
            if r["id"] == memory_id and r["user_id"] == user_id and not r["deleted"]:
                r["deleted"] = True
                return True
        return False

    async def approve(self, *, user_id, memory_id, status=MemoryStatus.USER_APPROVED) -> bool:
        for r in self.records:
            if r["id"] == memory_id and r["user_id"] == user_id:
                r["status"] = status
                return True
        return False


class FakeLLMProvider(LanguageModelProvider):
    def __init__(self, response: LLMResponse):
        self._response = response

    async def generate(self, messages, *, context=None) -> LLMResponse:
        return self._response


def _agent(
    response: LLMResponse,
    *,
    memory_store: InMemoryMemoryStore | None = None,
    context: ConversationContext | None = None,
) -> WowAgent:
    memory_store = memory_store or InMemoryMemoryStore()
    summary_repo = InMemorySummaryRepository()
    tools = build_default_tool_registry(memory_store, summary_repo)
    return WowAgent(
        FakeLLMProvider(response),
        FakeContextEngine(context),
        InMemoryStateRepository(),
        tools,
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
