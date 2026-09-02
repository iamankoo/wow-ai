"""Shared test doubles for app/agent/* and app/simulation/* tests - no
database required. Not a test module itself (no test_ prefix); imported by
test_agent_orchestrator.py and test_call_simulation.py.
"""

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
