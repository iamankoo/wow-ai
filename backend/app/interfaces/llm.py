"""Reasoning/language-model abstraction.

This is the seam that keeps WOW AI's "brain" independent of any specific
model provider. Phase 1 ships a rule-based implementation
(app/providers/llm/rule_based.py) so there is zero third-party AI API
dependency; a fine-tuned/self-hosted model can implement this same interface
later without touching the brain or API layers.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field


@dataclass
class LLMMessage:
    role: str  # "system" | "user" | "assistant"
    content: str


@dataclass
class LLMResponse:
    content: str
    intent: str | None = None
    slots: dict = field(default_factory=dict)
    metadata: dict = field(default_factory=dict)


class LanguageModelProvider(ABC):
    @abstractmethod
    async def generate(
        self, messages: list[LLMMessage], *, context: dict | None = None
    ) -> LLMResponse:
        """Produce a response (and, where applicable, an intent) for the given
        message history plus structured context (contact info, memories, etc)."""
