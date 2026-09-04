"""A deterministic, self-contained SpeechToTextProvider stand-in - not a
real ASR engine (see docs "Engineering principle: do not fake
functionality"). Real audio hardware/telephony isn't available in this
environment, so this is the honest alternative: a provider that satisfies
the exact same interface a real engine (e.g. faster-whisper) would, so the
rest of the pipeline (VAD/turn detection, WowAgent, response generation,
TTS) can be built and tested end-to-end today, and swapped for a real
engine later with zero changes above this layer.

Simulation convention, stated explicitly: an "audio chunk" fed to this
provider is UTF-8 text bytes standing in for what a real STT engine would
have already transcribed from actual audio. `feed()` treats each chunk as
one partial transcript update; `close()` (or a chunk ending in punctuation)
produces the final result. This is deliberately simple and inspectable,
not a signal-processing simulation.

Production note: when STT_PROVIDER=simulated is deployed behind
/brain/voice-command (see docs/DEPLOYMENT.md - the zero-dependency default
for a Render free-tier deployment), real callers send real raw PCM16
microphone bytes, not UTF-8 text - decoding those as UTF-8 fails for
almost any real audio (confirmed live: UnicodeDecodeError on byte 0xa9).
That's expected - this provider never claims to transcribe real speech -
but it must fail *honestly* (no transcript, same as "STT heard nothing"),
never with an unhandled 500. Real speech transcription requires actually
switching STT_PROVIDER to local_whisper (already implemented, see
local_whisper.py) on a plan with enough RAM.
"""

from app.interfaces.stt import STTStreamSession, SpeechToTextProvider, TranscriptionResult

_SENTENCE_ENDINGS = (".", "?", "!")


class SimulatedSTTStreamSession(STTStreamSession):
    def __init__(self):
        self._buffer: list[str] = []
        self._closed = False

    async def feed(self, audio_chunk: bytes) -> TranscriptionResult | None:
        if self._closed:
            raise RuntimeError("feed() called after close()")
        try:
            text = audio_chunk.decode("utf-8").strip()
        except UnicodeDecodeError:
            # Real (non-simulated) audio bytes, not the fake "text-as-audio"
            # convention this provider expects - honestly "no words heard",
            # never a crash. See module doc's production note.
            return None
        if not text:
            return None
        self._buffer.append(text)
        combined = " ".join(self._buffer)
        is_final = text.endswith(_SENTENCE_ENDINGS)
        result = TranscriptionResult(text=combined, is_final=is_final, confidence=0.99)
        if is_final:
            self._buffer = []
        return result

    async def close(self) -> TranscriptionResult | None:
        self._closed = True
        if not self._buffer:
            return None
        combined = " ".join(self._buffer)
        self._buffer = []
        return TranscriptionResult(text=combined, is_final=True, confidence=0.99)


class SimulatedSTTProvider(SpeechToTextProvider):
    async def transcribe(self, audio: bytes, *, sample_rate: int = 16000) -> TranscriptionResult:
        try:
            text = audio.decode("utf-8").strip()
        except UnicodeDecodeError:
            # See module doc's production note - real mic audio isn't valid
            # UTF-8; that's an honest "no words heard", never a crash.
            text = ""
        return TranscriptionResult(text=text, is_final=True, confidence=0.99)

    async def start_stream(self, *, sample_rate: int = 16000) -> STTStreamSession:
        _ = sample_rate
        return SimulatedSTTStreamSession()
