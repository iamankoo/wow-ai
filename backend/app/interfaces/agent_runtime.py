"""Top-level agent orchestration abstraction ("WOW Brain").

Concrete implementations wire together a LanguageModelProvider, a
ContextEngine, a MemoryStore and a state repository into a stateful
graph-like flow (LangGraph-style: classify -> update state -> act).
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field


@dataclass
class AgentAction:
    type: str
    payload: dict = field(default_factory=dict)


class AgentRuntime(ABC):
    @abstractmethod
    async def handle_input(
        self,
        *,
        user_id: str,
        text: str,
        conversation_id: str | None = None,
        caller_number: str | None = None,
    ) -> AgentAction:
        """Process one turn of input and return a structured action."""
