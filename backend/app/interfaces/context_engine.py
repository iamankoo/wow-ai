"""Context assembly abstraction: turns "who is calling / who is talking" into
the structured context the brain reasons over (contact, active persona,
relevant memories, recent conversation turns)."""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field


@dataclass
class ConversationContext:
    user_id: str
    contact: dict | None = None
    context_profile: dict | None = None
    recent_memories: list = field(default_factory=list)
    conversation_history: list = field(default_factory=list)


class ContextEngine(ABC):
    @abstractmethod
    async def build_context(
        self,
        *,
        user_id: str,
        caller_number: str | None = None,
        conversation_id: str | None = None,
    ) -> ConversationContext:
        """Assemble the full context for the brain to act on."""
