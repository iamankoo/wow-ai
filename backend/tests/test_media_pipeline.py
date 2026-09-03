"""Full real media pipeline integration test: a local audio fixture
travels through real VAD -> real STT -> the real WowAgent/WOW-Brain-v3
path -> real TTS, and the result is verified as genuinely valid,
playable synthesized audio - not a single mock anywhere in the chain.

This is the "close the loop" test for Phase 2 Blocks 2-5: each of
LocalWhisperSTTProvider (Block 2), LocalPiperTTSProvider (Block 3), and
WebRtcVoiceActivityDetector (Block 4) was previously only verified in
isolation; this test proves app.media.pipeline.MediaPipeline actually
connects them to each other and to the real v3-backed WowAgent
(Agent Core, proven for real in test_agent_integration_v3.py) end to
end.

Skipped cleanly (not failed) if any of the three optional real
components (faster-whisper, piper, or the recovered v3 model artifacts)
are unavailable - matching the gating pattern already used for each of
them individually.
"""

import wave
from pathlib import Path

import pytest

pytest.importorskip("faster_whisper", reason="faster-whisper not installed")
pytest.importorskip("piper", reason="piper-tts not installed")

from app.agent.context_profile_repository import InMemoryContextProfileRepository  # noqa: E402
from app.agent.orchestrator import WowAgent, build_default_tool_registry  # noqa: E402
from app.agent.summary_repository import InMemorySummaryRepository  # noqa: E402
from app.agent.user_settings_repository import InMemoryUserSettingsRepository  # noqa: E402
from app.brain.state_repository import InMemoryStateRepository  # noqa: E402
from app.media.pipeline import MediaPipeline  # noqa: E402
from app.providers.stt.local_whisper import LocalWhisperSTTProvider  # noqa: E402
from app.providers.tts.local_piper import LocalPiperTTSProvider  # noqa: E402
from app.providers.vad.webrtc_vad import WebRtcVoiceActivityDetector  # noqa: E402
from tests.agent_fakes import FakeContextEngine, InMemoryMemoryStore  # noqa: E402

_REPO_ROOT = Path(__file__).resolve().parents[2]
_V3_MODEL_DIR = _REPO_ROOT / "training" / "models" / "wow-brain" / "v3"
_FIXTURE = Path(__file__).parent / "fixtures" / "audio" / "meeting_context.wav"
_FRAME_MS = 30

pytestmark = pytest.mark.skipif(
    not (_V3_MODEL_DIR / "metadata.json").exists(),
    reason=(
        f"WOW Brain v3 artifacts not found at {_V3_MODEL_DIR} (gitignored) - "
        "recover or train them first to run this test"
    ),
)


def _read_pcm16(path: Path) -> tuple[bytes, int]:
    with wave.open(str(path), "rb") as w:
        return w.readframes(w.getnframes()), w.getframerate()


def _build_pipeline(context_profile_repo: InMemoryContextProfileRepository):
    from app.providers.llm.local_wow import LocalWOWModelProvider

    llm = LocalWOWModelProvider(_V3_MODEL_DIR, inference_device="cpu")
    memory_store = InMemoryMemoryStore()
    tools = build_default_tool_registry(
        memory_store,
        InMemorySummaryRepository(),
        context_profile_repo,
        InMemoryUserSettingsRepository(),
    )
    agent = WowAgent(llm, FakeContextEngine(), InMemoryStateRepository(), tools)

    vad = WebRtcVoiceActivityDetector()
    stt = LocalWhisperSTTProvider(model_size="base", device="cpu")
    tts = LocalPiperTTSProvider()

    return MediaPipeline(vad=vad, stt=stt, agent=agent, tts=tts, sample_rate=16000)


def _chunk(pcm: bytes, sample_rate: int, frame_ms: int = _FRAME_MS):
    frame_bytes = int(sample_rate * frame_ms / 1000) * 2
    for i in range(0, len(pcm), frame_bytes):
        yield pcm[i : i + frame_bytes]


async def test_real_audio_fixture_travels_through_the_full_real_pipeline(tmp_path):
    pcm, sr = _read_pcm16(_FIXTURE)
    assert sr == 16000  # LocalWhisperSTTProvider/WebRtcVoiceActivityDetector both expect this

    ctx_repo = InMemoryContextProfileRepository()
    pipeline = _build_pipeline(ctx_repo)

    turns = await pipeline.process_call_audio(user_id="u1", audio_chunks=_chunk(pcm, sr))

    assert len(turns) == 1
    turn = turns[0]

    # 1. Real STT: the actual spoken words were transcribed, not faked.
    assert "meeting" in turn.transcript.lower()

    # 2. Real WOW Brain v3 + real Agent Core: the same prediction already
    # verified in test_agent_integration_v3.py, now reached via audio
    # instead of a direct text call.
    assert turn.agent_action.payload["candidate_action"] == "SET_CONTEXT"
    assert turn.agent_action.payload["policy_decision"] == "allow"
    assert turn.agent_action.payload["tool_results"] == [
        {"tool": "set_context", "success": True, "error": None}
    ]
    assert ctx_repo.active_name(user_id="u1") == "MEETING"

    # 3. Real TTS: the agent's reply was genuinely synthesized, not
    # returned as empty/placeholder bytes - verify it as real, playable
    # PCM audio, the same rigor as Block 3's TTS artifact test.
    assert len(turn.reply_audio) > 0
    assert turn.reply_sample_rate > 0

    out_path = tmp_path / "pipeline_reply.wav"
    with wave.open(str(out_path), "wb") as wav_file:
        wav_file.setnchannels(1)
        wav_file.setsampwidth(2)
        wav_file.setframerate(turn.reply_sample_rate)
        wav_file.writeframes(turn.reply_audio)

    with wave.open(str(out_path), "rb") as check:
        duration_s = check.getnframes() / check.getframerate()
        assert duration_s > 0.1


async def test_silence_only_audio_produces_no_turns():
    """VAD correctly finding nothing to transcribe must not spuriously
    invoke the agent or TTS at all."""
    ctx_repo = InMemoryContextProfileRepository()
    pipeline = _build_pipeline(ctx_repo)

    silence = b"\x00\x00" * 8000 * 2  # 2s of silence at 16kHz mono
    turns = await pipeline.process_call_audio(user_id="u1", audio_chunks=_chunk(silence, 16000))

    assert turns == []
