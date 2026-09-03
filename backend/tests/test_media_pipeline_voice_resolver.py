"""Phase 6 Part F - proves MediaPipeline actually resolves and uses a
per-user real Piper voice, rather than applying the same fixed voice to
every caller regardless of their real preferred_language/voice_gender.

Uses simulated STT/TTS/VAD (not the real heavy audio models) so this test
runs unconditionally and fast - the *fact* that each specific Piper voice
id is real and actually downloads/synthesizes is separately, live-verified
in test_voice_selection.py and test_local_piper_tts.py. This test only
proves MediaPipeline wires a resolved voice through to
tts.synthesize()/get_sample_rate() correctly, and that different users
genuinely get different voices.
"""

from app.agent.context_profile_repository import InMemoryContextProfileRepository
from app.agent.orchestrator import WowAgent, build_default_tool_registry
from app.agent.summary_repository import InMemorySummaryRepository
from app.agent.user_settings_repository import InMemoryUserSettingsRepository
from app.brain.state_repository import InMemoryStateRepository
from app.interfaces.vad import (
    VadResult,
    VadStreamSession,
    VoiceActivityDetector,
    VoiceActivityEvent,
)
from app.media.pipeline import MediaPipeline
from app.providers.llm.rule_based import RuleBasedLanguageModelProvider
from app.providers.stt.simulated import SimulatedSTTProvider
from app.providers.tts.simulated import SimulatedTTSProvider
from tests.agent_fakes import FakeContextEngine, InMemoryMemoryStore


class _OneShotVadSession(VadStreamSession):
    """Every fed chunk is treated as one complete, immediately-ended
    utterance - real turn-detection timing is WebRtcVoiceActivityDetector's
    job (see test_webrtc_vad.py), not what this test is about."""

    async def feed(self, audio_chunk: bytes) -> VadResult:
        return VadResult(event=VoiceActivityEvent.SPEECH_END, is_speech=True)

    async def notify_playback_started(self) -> None:
        pass

    async def notify_playback_stopped(self) -> None:
        pass

    async def reset(self) -> None:
        pass


class _OneShotVad(VoiceActivityDetector):
    def start_session(self, *, sample_rate: int = 16000, frame_duration_ms: int = 30):
        return _OneShotVadSession()


class _SpyTTSProvider(SimulatedTTSProvider):
    """Records exactly which `voice` argument each call received, so tests
    can assert MediaPipeline passed through the resolved per-user voice
    rather than a fixed default."""

    def __init__(self):
        self.synthesize_voices: list[str | None] = []

    async def synthesize(self, text: str, *, voice: str | None = None) -> bytes:
        self.synthesize_voices.append(voice)
        return await super().synthesize(text, voice=voice)

    async def get_sample_rate(self, voice: str | None = None) -> int:
        return 22050


def _build_pipeline(tts: _SpyTTSProvider, *, tts_voice=None, voice_resolver=None) -> MediaPipeline:
    tools = build_default_tool_registry(
        InMemoryMemoryStore(),
        InMemorySummaryRepository(),
        InMemoryContextProfileRepository(),
        InMemoryUserSettingsRepository(),
    )
    agent = WowAgent(
        RuleBasedLanguageModelProvider(), FakeContextEngine(), InMemoryStateRepository(), tools
    )
    return MediaPipeline(
        vad=_OneShotVad(),
        stt=SimulatedSTTProvider(),
        agent=agent,
        tts=tts,
        tts_voice=tts_voice,
        voice_resolver=voice_resolver,
    )


async def test_voice_resolver_overrides_the_fixed_default_voice():
    tts = _SpyTTSProvider()

    async def resolver(user_id: str) -> str | None:
        return {"alice": "en_US-hfc_female-medium", "bob": "en_US-hfc_male-medium"}[user_id]

    pipeline = _build_pipeline(tts, tts_voice="en_US-lessac-medium", voice_resolver=resolver)

    await pipeline.process_call_audio(user_id="alice", audio_chunks=[b"Hi there."])
    await pipeline.process_call_audio(user_id="bob", audio_chunks=[b"Hi there."])

    assert tts.synthesize_voices == ["en_US-hfc_female-medium", "en_US-hfc_male-medium"]


async def test_no_resolver_falls_back_to_the_fixed_voice():
    tts = _SpyTTSProvider()
    pipeline = _build_pipeline(tts, tts_voice="en_US-lessac-medium")

    await pipeline.process_call_audio(user_id="alice", audio_chunks=[b"Hi there."])

    assert tts.synthesize_voices == ["en_US-lessac-medium"]


async def test_resolver_returning_none_falls_back_to_the_fixed_voice():
    """A resolver can legitimately have nothing to say (e.g. the user row
    is missing, or the resolver's own lookup fails) - MediaPipeline must
    fall back rather than pass a None voice through."""
    tts = _SpyTTSProvider()

    async def resolver(user_id: str) -> str | None:
        return None

    pipeline = _build_pipeline(tts, tts_voice="en_US-lessac-medium", voice_resolver=resolver)

    await pipeline.process_call_audio(user_id="alice", audio_chunks=[b"Hi there."])

    assert tts.synthesize_voices == ["en_US-lessac-medium"]
