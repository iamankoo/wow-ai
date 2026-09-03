"""Real end-to-end voice media pipeline:

    audio in -> VAD -> STT -> WowAgent -> TTS -> audio out

Wires together, for the first time, every real provider built in Phase 2
Blocks 2-4 (a real SpeechToTextProvider, a real TextToSpeechProvider, a
real VoiceActivityDetector) with the pre-existing, already-real
AgentRuntime/WOW-Brain stack from Agent Core - none of these were
previously connected to each other, only exercised independently against
their own interfaces.

Deliberately does NOT touch call control (TelephonyProvider.answer_call/
end_call, Android CallScreeningService/InCallService) - that is Phase 2
Block 6. This module's only job is turning a continuous raw-audio stream
into agent replies (as audio), the media layer a real telephony
integration sits on top of. Every dependency here is the existing
provider interface (SpeechToTextProvider/TextToSpeechProvider/
VoiceActivityDetector/AgentRuntime) - callers may pass real
implementations (as this module's own integration test does) or the
Phase 1 simulators, with zero change to this module.
"""

from collections.abc import AsyncIterator, Awaitable, Callable, Iterable
from dataclasses import dataclass

from app.interfaces.agent_runtime import AgentAction, AgentRuntime
from app.interfaces.stt import SpeechToTextProvider
from app.interfaces.tts import TextToSpeechProvider
from app.interfaces.vad import VoiceActivityDetector, VoiceActivityEvent

VoiceResolver = Callable[[str], Awaitable[str | None]]


@dataclass
class PipelineTurn:
    """One complete caller-utterance -> agent-reply round trip."""

    transcript: str
    agent_action: AgentAction
    reply_audio: bytes
    reply_sample_rate: int


class MediaPipeline:
    def __init__(
        self,
        *,
        vad: VoiceActivityDetector,
        stt: SpeechToTextProvider,
        agent: AgentRuntime,
        tts: TextToSpeechProvider,
        sample_rate: int = 16000,
        frame_duration_ms: int = 30,
        tts_voice: str | None = None,
        voice_resolver: VoiceResolver | None = None,
    ):
        self._vad = vad
        self._stt = stt
        self._agent = agent
        self._tts = tts
        self._sample_rate = sample_rate
        self._frame_duration_ms = frame_duration_ms
        self._tts_voice = tts_voice
        # Phase 6 Part F: when set, resolves the real Piper voice for this
        # specific user's real preferred_language/voice_gender (see
        # app.media.voice_selection) on every turn - takes priority over
        # the fixed `tts_voice` default, since that default applies the
        # same voice to every caller regardless of who they are.
        self._voice_resolver = voice_resolver

    async def process_call_audio(
        self,
        *,
        user_id: str,
        audio_chunks: Iterable[bytes] | AsyncIterator[bytes],
        conversation_id: str | None = None,
        caller_number: str | None = None,
    ) -> list[PipelineTurn]:
        """Feeds `audio_chunks` (raw PCM16 mono, any chunk size) through
        VAD; each time VAD confirms the caller's turn ended, transcribes
        everything captured since the previous turn via the real STT
        provider, sends the transcript to the real agent, and synthesizes
        the agent's reply via the real TTS provider. Returns one
        PipelineTurn per completed utterance, in order."""
        vad_session = self._vad.start_session(
            sample_rate=self._sample_rate, frame_duration_ms=self._frame_duration_ms
        )
        turns: list[PipelineTurn] = []
        caller_buffer = bytearray()

        async for chunk in _as_async_iter(audio_chunks):
            result = await vad_session.feed(chunk)
            if result.is_speech:
                caller_buffer.extend(chunk)
            if result.event == VoiceActivityEvent.SPEECH_END and caller_buffer:
                turn = await self._finalize_turn(
                    bytes(caller_buffer),
                    user_id=user_id,
                    conversation_id=conversation_id,
                    caller_number=caller_number,
                )
                caller_buffer = bytearray()
                if turn is not None:
                    turns.append(turn)

        # The stream ended without a trailing silence long enough to
        # trigger SPEECH_END (e.g. a fixture that just stops mid- or
        # right-after speech) - finalize whatever was captured rather than
        # silently discarding a real utterance.
        if caller_buffer:
            turn = await self._finalize_turn(
                bytes(caller_buffer),
                user_id=user_id,
                conversation_id=conversation_id,
                caller_number=caller_number,
            )
            if turn is not None:
                turns.append(turn)

        return turns

    async def _finalize_turn(
        self,
        caller_audio: bytes,
        *,
        user_id: str,
        conversation_id: str | None,
        caller_number: str | None,
    ) -> PipelineTurn | None:
        transcription = await self._stt.transcribe(caller_audio, sample_rate=self._sample_rate)
        if not transcription.text.strip():
            return None  # VAD heard speech-shaped audio but STT found no real words - nothing to act on

        action = await self._agent.handle_input(
            user_id=user_id,
            text=transcription.text,
            conversation_id=conversation_id,
            caller_number=caller_number,
        )

        voice = self._tts_voice
        if self._voice_resolver is not None:
            resolved = await self._voice_resolver(user_id)
            if resolved:
                voice = resolved

        reply_text = (action.payload or {}).get("reply") or ""
        reply_audio = b""
        if reply_text.strip():
            reply_audio = await self._tts.synthesize(reply_text, voice=voice)

        return PipelineTurn(
            transcript=transcription.text,
            agent_action=action,
            reply_audio=reply_audio,
            reply_sample_rate=await self._resolve_tts_sample_rate(voice),
        )

    async def _resolve_tts_sample_rate(self, voice: str | None) -> int:
        # get_sample_rate() is an additive convenience some real providers
        # (e.g. LocalPiperTTSProvider) expose beyond the TextToSpeechProvider
        # ABC, since the interface's synthesize() returns raw bytes with no
        # format field - use it opportunistically, never require it.
        get_sample_rate = getattr(self._tts, "get_sample_rate", None)
        if get_sample_rate is None:
            return self._sample_rate
        return await get_sample_rate(voice=voice)


async def _as_async_iter(
    source: Iterable[bytes] | AsyncIterator[bytes],
) -> AsyncIterator[bytes]:
    if hasattr(source, "__anext__"):
        async for item in source:  # type: ignore[union-attr]
            yield item
        return
    for item in source:  # type: ignore[union-attr]
        yield item


def chunk_pcm16(
    audio: bytes, *, sample_rate: int, frame_duration_ms: int = 30
) -> Iterable[bytes]:
    """Splits one complete raw-PCM16-mono buffer into frame-sized chunks
    for MediaPipeline.process_call_audio's `audio_chunks`. Required, not
    optional, for a caller handing over one whole pre-recorded utterance
    (e.g. the real voice-command HTTP endpoint) rather than a live chunk
    stream: VadStreamSession.feed() deliberately surfaces at most one
    state-transition event per call and leaves the rest of a large chunk
    buffered for "the next feed() call" (see WebRtcVadStreamSession.feed's
    docstring) - handing the whole recording over as a single chunk would
    silently strand its trailing SPEECH_END event with no further feed()
    call ever coming to surface it, and the real speech in it would be
    dropped as if nothing had been said."""
    frame_bytes = int(sample_rate * frame_duration_ms / 1000) * 2  # 16-bit PCM
    for i in range(0, len(audio), frame_bytes):
        yield audio[i : i + frame_bytes]
