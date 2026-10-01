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

import logging
import time
from collections.abc import AsyncIterator, Awaitable, Callable, Iterable
from dataclasses import dataclass, field

from app.agent.language_detection import detect_language
from app.interfaces.agent_runtime import AgentAction, AgentRuntime
from app.interfaces.stt import SpeechToTextProvider
from app.interfaces.tts import TextToSpeechProvider
from app.interfaces.vad import VoiceActivityDetector, VoiceActivityEvent

logger = logging.getLogger("app.media.pipeline")

# See MediaPipeline.stream_call_audio._finalize_safely.
_MAX_CONSECUTIVE_TURN_FAILURES = 3

VoiceResolver = Callable[[str], Awaitable[str | None]]
# (user_id, language_code) -> a real Piper voice id for that language,
# preserving the user's own voice_gender - see
# app.media.voice_selection.resolve_voice_for_language. Optional,
# additive: when not given, every reply uses the fixed-language
# `voice_resolver`/`tts_voice` exactly as before this round.
LanguageVoiceResolver = Callable[[str, str], Awaitable[str | None]]


@dataclass
class PipelineTurn:
    """One complete caller-utterance -> agent-reply round trip."""

    transcript: str
    agent_action: AgentAction
    reply_audio: bytes
    reply_sample_rate: int
    # Real per-turn detected language ("en"/"hi"/"hi-Latn" - see
    # app.agent.language_detection), independent for every turn so a
    # caller switching languages mid-call is genuinely tracked, not
    # forced into whatever the first turn happened to be.
    language: str | None = None
    # Real, measured (never estimated) per-stage wall-clock latency for
    # this turn, in milliseconds: "stt" (STT.transcribe), "language_detection"
    # (app.agent.language_detection.detect_language - real but essentially
    # free, see that module's docstring), "agent" (the full WowAgent
    # turn - already broken down further into its own context/brain/
    # policy/tool/response stages inside agent_action.payload["durations_ms"]),
    # and "tts" (synthesize_reply). "total" is the sum actually observed
    # for this turn, not the sum of the parts (real end-to-end wall time,
    # including any scheduling overhead between stages).
    stage_durations_ms: dict = field(default_factory=dict)


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
        language_voice_resolver: LanguageVoiceResolver | None = None,
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
        # New this round: when set, and a turn has a real detected caller
        # language (see app.agent.language_detection), this takes priority
        # over `voice_resolver` for THAT turn's reply - the user's own
        # voice_gender preference is preserved, only which language-voice
        # pair is used changes per turn, so a caller switching between
        # Hindi/Hinglish/English mid-call actually hears the matching
        # female Piper voice each time, not one fixed language forever.
        # The opening greeting (no caller turn/language yet) still uses
        # `voice_resolver`/`tts_voice` unchanged.
        self._language_voice_resolver = language_voice_resolver

    async def process_call_audio(
        self,
        *,
        user_id: str,
        audio_chunks: Iterable[bytes] | AsyncIterator[bytes],
        conversation_id: str | None = None,
        caller_number: str | None = None,
    ) -> list[PipelineTurn]:
        """Batch entry point: feeds `audio_chunks` (raw PCM16 mono, any
        chunk size) through the full pipeline and returns every completed
        PipelineTurn only once `audio_chunks` is exhausted. Correct for one
        complete pre-recorded utterance (e.g. /brain/voice-command's one
        HTTP request body) where nothing needs to reach the caller until
        the whole thing has been processed. A live, indefinite call needs
        each reply the moment it's ready instead - see stream_call_audio."""
        return [
            turn
            async for turn in self.stream_call_audio(
                user_id=user_id,
                audio_chunks=audio_chunks,
                conversation_id=conversation_id,
                caller_number=caller_number,
            )
        ]

    async def stream_call_audio(
        self,
        *,
        user_id: str,
        audio_chunks: Iterable[bytes] | AsyncIterator[bytes],
        conversation_id: str | None = None,
        caller_number: str | None = None,
    ) -> AsyncIterator[PipelineTurn]:
        """Live entry point: yields each PipelineTurn as soon as VAD
        confirms that utterance's turn ended, instead of waiting for the
        whole stream to finish. This is the shape a real bidirectional
        telephony bridge needs - the caller must hear WOW's reply while
        the call is still open, not only after it ends - and is exactly
        what a real TelephonyProvider implementation (still not built; see
        docs/ARCHITECTURE.md "Real telephony") would drive: feed inbound
        audio frames in as they arrive over the provider's live connection,
        send each yielded turn's reply_audio back out over that same
        connection immediately. `audio_chunks` may be an async iterator
        that keeps producing chunks indefinitely (e.g. reading from an open
        WebSocket) - unlike process_call_audio, nothing here requires the
        source to end for the first reply to be produced."""
        vad_session = self._vad.start_session(
            sample_rate=self._sample_rate, frame_duration_ms=self._frame_duration_ms
        )
        caller_buffer = bytearray()
        consecutive_failures = 0

        async def _finalize_safely(audio: bytes) -> PipelineTurn | None:
            """One bad utterance (an STT/Brain/TTS exception) must not drop
            the whole live call: log (exception type only - never audio or
            transcript content), skip that turn, keep listening. After
            _MAX_CONSECUTIVE_TURN_FAILURES in a row the failure is treated as
            systemic and re-raised so the caller can end the call cleanly
            instead of sitting silent forever."""
            nonlocal consecutive_failures
            try:
                turn = await self._finalize_turn(
                    audio,
                    user_id=user_id,
                    conversation_id=conversation_id,
                    caller_number=caller_number,
                )
            except Exception as exc:  # noqa: BLE001
                consecutive_failures += 1
                logger.warning(
                    "media pipeline: turn failed (%s), %d consecutive",
                    type(exc).__name__,
                    consecutive_failures,
                )
                if consecutive_failures >= _MAX_CONSECUTIVE_TURN_FAILURES:
                    raise
                return None
            consecutive_failures = 0
            return turn

        async for chunk in _as_async_iter(audio_chunks):
            result = await vad_session.feed(chunk)
            if result.is_speech:
                caller_buffer.extend(chunk)
            if result.event == VoiceActivityEvent.SPEECH_END and caller_buffer:
                turn = await _finalize_safely(bytes(caller_buffer))
                caller_buffer = bytearray()
                if turn is not None:
                    yield turn

        # The stream ended without a trailing silence long enough to
        # trigger SPEECH_END (e.g. a fixture that just stops mid- or
        # right-after speech) - finalize whatever was captured rather than
        # silently discarding a real utterance.
        if caller_buffer:
            turn = await _finalize_safely(bytes(caller_buffer))
            if turn is not None:
                yield turn

    async def _finalize_turn(
        self,
        caller_audio: bytes,
        *,
        user_id: str,
        conversation_id: str | None,
        caller_number: str | None,
    ) -> PipelineTurn | None:
        turn_started = time.monotonic()
        durations_ms: dict[str, float] = {}

        stt_started = time.monotonic()
        transcription = await self._stt.transcribe(caller_audio, sample_rate=self._sample_rate)
        durations_ms["stt"] = (time.monotonic() - stt_started) * 1000
        if not transcription.text.strip():
            return None  # VAD heard speech-shaped audio but STT found no real words - nothing to act on

        # Real per-turn language detection (script + Whisper's own real
        # acoustic signal, when the active STT provider produces one +
        # a bounded Hindi-in-Latin-script lexicon) - see
        # app.agent.language_detection. Independent every turn, so a
        # caller switching languages mid-call is tracked turn by turn,
        # never forced into whatever the first turn happened to be.
        lang_started = time.monotonic()
        language = detect_language(
            transcription.text,
            whisper_language=transcription.language,
            whisper_language_probability=transcription.language_probability,
        ).code
        durations_ms["language_detection"] = (time.monotonic() - lang_started) * 1000

        agent_started = time.monotonic()
        action = await self._agent.handle_input(
            user_id=user_id,
            text=transcription.text,
            conversation_id=conversation_id,
            caller_number=caller_number,
            language=language,
        )
        durations_ms["agent"] = (time.monotonic() - agent_started) * 1000

        reply_text = (action.payload or {}).get("reply") or ""
        tts_started = time.monotonic()
        reply_audio, reply_sample_rate = await self.synthesize_reply(
            user_id=user_id, text=reply_text, language=language
        )
        durations_ms["tts"] = (time.monotonic() - tts_started) * 1000
        durations_ms["total"] = (time.monotonic() - turn_started) * 1000

        return PipelineTurn(
            transcript=transcription.text,
            agent_action=action,
            reply_audio=reply_audio,
            reply_sample_rate=reply_sample_rate,
            language=language,
            stage_durations_ms=durations_ms,
        )

    async def synthesize_reply(
        self, *, user_id: str, text: str, language: str | None = None
    ) -> tuple[bytes, int]:
        """Synthesizes `text` via the real TTS provider using this user's
        resolved voice - the same voice-resolution _finalize_turn already
        applies to every agent-generated reply, exposed here for a caller
        that needs a real synthesized reply with no caller utterance to
        respond to yet (e.g. a call's fixed opening greeting - see
        app/api/routes/telephony_plivo.py, which calls this with
        `language=None`, so the greeting always uses the user's static
        profile voice). Returns (audio_bytes, sample_rate); audio_bytes is
        empty (never fabricated) whenever `text` is blank."""
        voice = await self._resolve_voice(user_id, language)
        sample_rate = await self._resolve_tts_sample_rate(voice)
        if not text.strip():
            return b"", sample_rate
        audio = await self._tts.synthesize(text, voice=voice)
        return audio, sample_rate

    async def _resolve_voice(self, user_id: str, language: str | None = None) -> str | None:
        # A real per-turn detected language, with a real resolver able to
        # act on it, takes priority - see LanguageVoiceResolver's docstring
        # for why (preserves voice_gender, changes only the language).
        if language is not None and self._language_voice_resolver is not None:
            resolved = await self._language_voice_resolver(user_id, language)
            if resolved:
                return resolved
        voice = self._tts_voice
        if self._voice_resolver is not None:
            resolved = await self._voice_resolver(user_id)
            if resolved:
                voice = resolved
        return voice

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
