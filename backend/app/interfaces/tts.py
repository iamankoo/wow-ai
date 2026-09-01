"""Text-to-speech abstraction.

Phase 1 defines the contract only. Phase 2 should implement this with a
self-hostable engine (e.g. Coqui/Piper) so speech synthesis never depends on
a hosted vendor API.
"""

from abc import ABC, abstractmethod
from collections.abc import AsyncIterator


class TextToSpeechProvider(ABC):
    @abstractmethod
    async def synthesize(self, text: str, *, voice: str | None = None) -> bytes:
        """Synthesize the full utterance and return complete audio bytes."""

    @abstractmethod
    async def stream_synthesize(
        self, text: str, *, voice: str | None = None
    ) -> AsyncIterator[bytes]:
        """Synthesize incrementally, yielding audio chunks as they're ready."""
