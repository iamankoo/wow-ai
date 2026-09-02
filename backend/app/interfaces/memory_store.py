"""Memory storage/recall abstraction, backed by pgvector in Phase 1 (see
docs/ARCHITECTURE.md "Memory system" / "Memory safety").

`MemoryType`/`MemoryStatus` are re-exported from `app.models.memory` (the
single source of truth for the vocabulary, same pattern as
`app.brain.taxonomy`) so callers of this interface never need to import the
ORM layer directly.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field

from app.models.memory import MemoryStatus, MemoryType

__all__ = ["MemoryRecord", "MemoryStore", "MemoryStatus", "MemoryType"]


@dataclass
class MemoryRecord:
    id: str
    content: str
    score: float | None = None
    memory_type: MemoryType = MemoryType.SEMANTIC
    status: MemoryStatus = MemoryStatus.OBSERVED
    confidence: float | None = None
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
        memory_type: MemoryType = MemoryType.SEMANTIC,
        status: MemoryStatus = MemoryStatus.OBSERVED,
        confidence: float | None = None,
    ) -> str:
        """Persist a memory fact and return its id.

        `status` defaults to OBSERVED, never CONFIRMED/USER_APPROVED - a
        caller that has an explicit user confirmation must say so
        explicitly (see docs "Memory safety": WOW must not silently treat
        every statement as a permanent fact).
        """

    @abstractmethod
    async def search(
        self,
        *,
        user_id: str,
        query: str,
        query_embedding: list[float] | None = None,
        top_k: int = 5,
        memory_type: MemoryType | None = None,
        include_deleted: bool = False,
    ) -> list[MemoryRecord]:
        """Return the most relevant memories for a user, ranked by similarity
        when an embedding is supplied, falling back to recency/text match
        otherwise. Selective by design (docs "Memory system": never dump the
        entire store into a prompt) - always bounded by `top_k`, optionally
        narrowed to one `memory_type`. Soft-deleted rows are excluded unless
        `include_deleted=True`."""

    @abstractmethod
    async def delete(self, *, user_id: str, memory_id: str) -> bool:
        """Soft-delete one memory (sets `deleted_at`) so a user can remove a
        stored memory (docs "Memory safety" / data-subject rights). Returns
        False if no matching, not-already-deleted row exists for that user -
        never raises for a missing id, since "already gone" is a success
        state for a delete request."""

    @abstractmethod
    async def approve(
        self, *, user_id: str, memory_id: str, status: MemoryStatus = MemoryStatus.USER_APPROVED
    ) -> bool:
        """Promote a memory's trust status (e.g. OBSERVED -> USER_APPROVED)
        after explicit user confirmation. Returns False if no matching row
        exists for that user."""
