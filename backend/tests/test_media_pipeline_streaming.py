"""MediaPipeline.stream_call_audio - the live, incremental-reply entry
point a real bidirectional telephony bridge needs (see
docs/ARCHITECTURE.md "Real telephony"): a caller must hear WOW's reply
while the call is still open, not only after the whole call ends, which
process_call_audio's "collect a list, return once the source is
exhausted" shape cannot do for a live, indefinite audio source (e.g. an
open WebSocket to a telephony provider).

Uses simulated STT/TTS/VAD (not the real heavy audio models), matching
test_media_pipeline_voice_resolver.py's pattern, so this runs
unconditionally and fast - real audio fidelity is separately, live-verified
by test_media_pipeline.py against the real stack.
"""

import asyncio

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


def _build_pipeline() -> MediaPipeline:
    tools = build_default_tool_registry(
        InMemoryMemoryStore(),
        InMemorySummaryRepository(),
        InMemoryContextProfileRepository(),
        InMemoryUserSettingsRepository(),
    )
    agent = WowAgent(
        RuleBasedLanguageModelProvider(), FakeContextEngine(), InMemoryStateRepository(), tools
    )
    return MediaPipeline(vad=_OneShotVad(), stt=SimulatedSTTProvider(), agent=agent, tts=SimulatedTTSProvider())


async def test_stream_call_audio_yields_a_turn_without_the_source_ever_ending():
    """The whole reason stream_call_audio exists: a real live call's audio
    source never ends mid-call, so a caller that only gets a result after
    the source is exhausted (process_call_audio) could never receive a
    reply until the call was already over. This asserts the first turn is
    retrievable from the async generator well before its source's second
    chunk would ever be produced."""
    pipeline = _build_pipeline()

    async def never_ending_audio():
        yield b"Hi there."
        await asyncio.Event().wait()  # never resolves - a live call keeps sending audio forever
        yield b"unreachable"  # pragma: no cover

    turns = pipeline.stream_call_audio(user_id="alice", audio_chunks=never_ending_audio())
    first_turn = await asyncio.wait_for(turns.__anext__(), timeout=5.0)

    assert first_turn.transcript == "Hi there."
    assert first_turn.reply_audio


async def test_stream_call_audio_yields_multiple_turns_in_order():
    pipeline = _build_pipeline()

    async def two_utterances():
        yield b"Hi there."
        yield b"How are you?"

    turns = [t async for t in pipeline.stream_call_audio(user_id="alice", audio_chunks=two_utterances())]

    assert [t.transcript for t in turns] == ["Hi there.", "How are you?"]


async def test_process_call_audio_still_collects_every_turn_after_the_stream_refactor():
    """Regression check: process_call_audio is now a thin wrapper around
    stream_call_audio (see MediaPipeline) - its own pre-existing contract
    (collect every turn, return once the source ends) must be unchanged."""
    pipeline = _build_pipeline()

    turns = await pipeline.process_call_audio(
        user_id="alice", audio_chunks=[b"Hi there.", b"How are you?"]
    )

    assert [t.transcript for t in turns] == ["Hi there.", "How are you?"]
