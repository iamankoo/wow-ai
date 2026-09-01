"""Speech-to-text abstraction.

Phase 1 defines the contract only. Phase 2 should implement this with a
self-hostable engine (e.g. faster-whisper / whisper.cpp) so transcription
never depends on a hosted vendor API.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass
class TranscriptionResult:
    text: str
    is_final: bool = True
    confidence: float | None = None


class STTStreamSession(ABC):
    """A live, chunked transcription session for one call leg."""

    @abstractmethod
    async def feed(self, audio_chunk: bytes) -> TranscriptionResult | None:
        """Feed raw audio bytes in; returns a partial/final result when ready."""

    @abstractmethod
    async def close(self) -> TranscriptionResult | None:
        """Flush and finalize the session, returning any trailing result."""


class SpeechToTextProvider(ABC):
    @abstractmethod
    async def transcribe(
        self, audio: bytes, *, sample_rate: int = 16000
    ) -> TranscriptionResult:
        """Transcribe a complete, already-recorded audio buffer."""

    @abstractmethod
    async def start_stream(self, *, sample_rate: int = 16000) -> STTStreamSession:
        """Start a streaming session for real-time call audio."""
