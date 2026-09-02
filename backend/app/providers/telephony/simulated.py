"""A deterministic TelephonyProvider stand-in - not a real carrier/VoIP
integration (see docs "Engineering principle: do not fake functionality").
Real call infrastructure (Android CallScreeningService/InCallService, or a
carrier SIP trunk) isn't available in this environment; this simulator
satisfies the exact same interface so the orchestration layer above it -
answer/end/send-audio/receive-audio - is real and testable today, and a
real provider is a drop-in replacement with zero change to callers.

`inject_caller_audio` is simulation-only (not part of the TelephonyProvider
contract): it stands in for "the carrier delivered this inbound audio
chunk", driving whatever handler a caller registered via
`on_audio_received` - this is how `app/simulation/call_simulator.py` feeds
a scripted conversation through the pipeline.
"""

from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field

from app.interfaces.telephony import TelephonyProvider


@dataclass
class SimulatedCallLog:
    call_id: str
    answered: bool = False
    ended: bool = False
    outbound_audio: list[bytes] = field(default_factory=list)
    inbound_audio: list[bytes] = field(default_factory=list)


class SimulatedTelephonyProvider(TelephonyProvider):
    def __init__(self):
        self._calls: dict[str, SimulatedCallLog] = {}
        self._handlers: dict[str, Callable[[bytes], Awaitable[None]]] = {}

    def _log(self, call_id: str) -> SimulatedCallLog:
        if call_id not in self._calls:
            self._calls[call_id] = SimulatedCallLog(call_id=call_id)
        return self._calls[call_id]

    async def answer_call(self, call_id: str) -> None:
        self._log(call_id).answered = True

    async def end_call(self, call_id: str) -> None:
        self._log(call_id).ended = True

    async def send_audio(self, call_id: str, audio_chunk: bytes) -> None:
        self._log(call_id).outbound_audio.append(audio_chunk)

    async def on_audio_received(
        self, call_id: str, handler: Callable[[bytes], Awaitable[None]]
    ) -> None:
        self._handlers[call_id] = handler

    async def inject_caller_audio(self, call_id: str, audio_chunk: bytes) -> None:
        """Simulation-only: deliver one inbound audio chunk as if the caller
        had spoken it, invoking whatever handler is registered for this call."""
        self._log(call_id).inbound_audio.append(audio_chunk)
        handler = self._handlers.get(call_id)
        if handler is not None:
            await handler(audio_chunk)

    def call_log(self, call_id: str) -> SimulatedCallLog:
        return self._log(call_id)
