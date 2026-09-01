"""Telephony abstraction.

Represents the seam between the backend brain and whatever is actually
carrying call audio - in Phase 2 that's the Android device (via a platform
channel / foreground service acting as the real endpoint). Defined here so
the orchestration layer never assumes a specific carrier/VoIP SDK.
"""

from abc import ABC, abstractmethod
from collections.abc import Awaitable, Callable


class TelephonyProvider(ABC):
    @abstractmethod
    async def answer_call(self, call_id: str) -> None: ...

    @abstractmethod
    async def end_call(self, call_id: str) -> None: ...

    @abstractmethod
    async def send_audio(self, call_id: str, audio_chunk: bytes) -> None:
        """Send synthesized audio out to the caller."""

    @abstractmethod
    async def on_audio_received(
        self, call_id: str, handler: Callable[[bytes], Awaitable[None]]
    ) -> None:
        """Register a handler invoked with each inbound audio chunk from the caller."""
