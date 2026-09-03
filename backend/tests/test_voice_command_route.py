"""Phase 6 Part E/J - the real POST /brain/voice-command route, proven
end to end against a real Postgres instance and the real faster-whisper/
piper/webrtcvad providers (not mocks) - the same rigor
test_media_pipeline.py already applies to MediaPipeline itself, now
proving the actual HTTP route built on top of it (request parsing,
frame-chunking, response shape) is wired correctly.

Skipped cleanly (not failed) if faster-whisper/piper aren't installed or
TEST_DATABASE_URL isn't set - matching the gating pattern already used
throughout this test suite.
"""

import os
import wave
from pathlib import Path

import pytest

pytest.importorskip("faster_whisper", reason="faster-whisper not installed")
pytest.importorskip("piper", reason="piper-tts not installed")

import base64  # noqa: E402
import functools  # noqa: E402

from fastapi import FastAPI  # noqa: E402
from httpx import ASGITransport, AsyncClient  # noqa: E402
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine  # noqa: E402

from app.agent.context_profile_repository import InMemoryContextProfileRepository  # noqa: E402
from app.agent.orchestrator import WowAgent, build_default_tool_registry  # noqa: E402
from app.agent.summary_repository import InMemorySummaryRepository  # noqa: E402
from app.agent.user_settings_repository import InMemoryUserSettingsRepository  # noqa: E402
from app.api.deps import get_media_pipeline  # noqa: E402
from app.brain.state_repository import InMemoryStateRepository  # noqa: E402
from app.db.base import Base  # noqa: E402
from app.media.pipeline import MediaPipeline  # noqa: E402
from app.media.voice_selection import resolve_user_voice  # noqa: E402
from app.models.user import PreferredLanguage, User, VoiceGender  # noqa: E402
from app.providers.llm.rule_based import RuleBasedLanguageModelProvider  # noqa: E402
from app.providers.stt.local_whisper import LocalWhisperSTTProvider  # noqa: E402
from app.providers.tts.local_piper import LocalPiperTTSProvider  # noqa: E402
from app.providers.vad.webrtc_vad import WebRtcVoiceActivityDetector  # noqa: E402
from tests.agent_fakes import FakeContextEngine, InMemoryMemoryStore  # noqa: E402

TEST_DATABASE_URL = os.environ.get("TEST_DATABASE_URL")

pytestmark = pytest.mark.skipif(
    not TEST_DATABASE_URL, reason="TEST_DATABASE_URL not set; skipping DB integration"
)

_FIXTURE = Path(__file__).parent / "fixtures" / "audio" / "meeting_context.wav"


def _read_pcm16(path: Path) -> tuple[bytes, int]:
    with wave.open(str(path), "rb") as w:
        return w.readframes(w.getnframes()), w.getframerate()


@pytest.fixture
async def session():
    engine = create_async_engine(TEST_DATABASE_URL, future=True)
    async with engine.begin() as conn:
        from sqlalchemy import text

        await conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
        await conn.run_sync(Base.metadata.create_all)

    session_factory = async_sessionmaker(bind=engine, expire_on_commit=False)
    async with session_factory() as s:
        yield s

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await engine.dispose()


async def _make_client(session, *, voice_resolver=None) -> AsyncClient:
    from app.api.routes import brain

    app = FastAPI()
    app.include_router(brain.router)

    async def _get_media_pipeline():
        tools = build_default_tool_registry(
            InMemoryMemoryStore(),
            InMemorySummaryRepository(),
            InMemoryContextProfileRepository(),
            InMemoryUserSettingsRepository(),
        )
        agent = WowAgent(
            RuleBasedLanguageModelProvider(), FakeContextEngine(), InMemoryStateRepository(), tools
        )
        yield MediaPipeline(
            vad=WebRtcVoiceActivityDetector(),
            stt=LocalWhisperSTTProvider(model_size="base", device="cpu"),
            agent=agent,
            tts=LocalPiperTTSProvider(),
            voice_resolver=voice_resolver or functools.partial(resolve_user_voice, session),
        )

    app.dependency_overrides[get_media_pipeline] = _get_media_pipeline
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://test")


async def test_real_audio_recording_travels_through_the_full_real_route(session):
    user = User(
        display_name="Aniket",
        phone_number="+10000000040",
        preferred_language=PreferredLanguage.ENGLISH,
        voice_gender=VoiceGender.FEMALE,
    )
    session.add(user)
    await session.flush()
    await session.commit()

    pcm, sr = _read_pcm16(_FIXTURE)
    assert sr == 16000

    client = await _make_client(session)
    async with client:
        resp = await client.post(
            f"/brain/voice-command?user_id={user.id}&sample_rate={sr}",
            content=pcm,
            headers={"content-type": "application/octet-stream"},
        )

    assert resp.status_code == 200
    body = resp.json()

    # 1. Real STT: the actual spoken words were transcribed.
    assert "meeting" in body["transcript"].lower()

    # 2. Real agent reply text, non-empty.
    assert body["reply_text"].strip() != ""

    # 3. Real TTS: genuinely synthesized, playable audio, not empty/fake bytes.
    reply_audio = base64.b64decode(body["reply_audio_base64"])
    assert len(reply_audio) > 0
    assert body["reply_sample_rate"] > 0


async def test_silence_only_recording_is_an_honest_no_op(session):
    user = User(display_name="Aniket", phone_number="+10000000041")
    session.add(user)
    await session.flush()
    await session.commit()

    silence = b"\x00\x00" * 8000 * 2  # 2s of silence at 16kHz mono

    client = await _make_client(session)
    async with client:
        resp = await client.post(
            f"/brain/voice-command?user_id={user.id}&sample_rate=16000",
            content=silence,
            headers={"content-type": "application/octet-stream"},
        )

    assert resp.status_code == 200
    body = resp.json()
    assert body["transcript"] == ""
    assert body["reply_audio_base64"] == ""
    assert body["action_type"] == "none"


async def test_empty_body_is_rejected(session):
    user = User(display_name="Aniket", phone_number="+10000000042")
    session.add(user)
    await session.flush()
    await session.commit()

    client = await _make_client(session)
    async with client:
        resp = await client.post(f"/brain/voice-command?user_id={user.id}", content=b"")

    assert resp.status_code == 400
