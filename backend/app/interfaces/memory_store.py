"""Long-term memory storage/recall abstraction, backed by pgvector in Phase 1."""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field


@dataclass
class MemoryRecord:
    id: str
    content: str
    score: float | None = None
    metadata: dict = field(default_factory=dict)


class MemoryStore(ABC):
    @abstractmethod
    async def add(
        self,
        *,
        user_id: str,
        content: str,
        contact_id: str | None = None,
        embedding: list[float] | None = None,
        source_type: str = "manual",
        source_id: str | None = None,
    ) -> str:
        """Persist a memory fact and return its id."""

    @abstractmethod
    async def search(
        self,
        *,
        user_id: str,
        query: str,
        query_embedding: list[float] | None = None,
        top_k: int = 5,
    ) -> list[MemoryRecord]:
        """Return the most relevant memories for a user, ranked by similarity
        when an embedding is supplied, falling back to recency/text match
        otherwise."""
