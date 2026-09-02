"""A deterministic TextToSpeechProvider stand-in - not a real synthesis
engine (see docs "Engineering principle: do not fake functionality"). It
satisfies the exact interface a real engine (e.g. Piper/Coqui) would, so
the response -> "audio" -> telephony leg of the pipeline is real and
testable today; swapping in a real engine later requires no change above
this layer.

Simulation convention, stated explicitly: the "audio" this provider
produces is the UTF-8 bytes of the text itself (streamed word-by-word for
`stream_synthesize`) - inspectable and deterministic, not actual synthesized
waveform data.
"""

from collections.abc import AsyncIterator

from app.interfaces.tts import TextToSpeechProvider


class SimulatedTTSProvider(TextToSpeechProvider):
    async def synthesize(self, text: str, *, voice: str | None = None) -> bytes:
        return text.encode("utf-8")

    async def stream_synthesize(
        self, text: str, *, voice: str | None = None
    ) -> AsyncIterator[bytes]:
        words = text.split(" ")
        for i, word in enumerate(words):
            chunk = word if i == len(words) - 1 else f"{word} "
            yield chunk.encode("utf-8")
