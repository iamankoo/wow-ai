"""Real end-to-end test of the Plivo telephony bridge (app/api/routes/
telephony_plivo.py, app/providers/telephony/plivo.py): a real WebSocket
connection, carrying real mu-law-8kHz-encoded audio (the real
meeting_context.wav fixture, downsampled and mu-law-encoded exactly as a
real Plivo call would deliver it), driven through the real route ->
PlivoTelephonyProvider -> MediaPipeline.stream_call_audio() -> real
faster-whisper STT -> WowAgent -> real Piper TTS -> back out as real
mu-law `playAudio` messages, with a real CallRecorder writing real rows
to a real (temp file-backed) SQLite database (no mocked persistence).

This is the closest thing to a real Plivo call this environment can prove
without an actual Plivo account/credentials - see docs/ARCHITECTURE.md
"Real telephony" for what a live call would still need to confirm (the
exact inbound JSON field nesting in particular).

Skipped cleanly (not failed) if faster-whisper/piper aren't installed -
matching the gating pattern used throughout this test suite.
"""

import base64
import json
import wave
from pathlib import Path

import pytest

from tests.conftest import authorized_stream_path

pytest.importorskip("faster_whisper", reason="faster-whisper not installed")
pytest.importorskip("piper", reason="piper-tts not installed")

from fastapi import FastAPI  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import select  # noqa: E402
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine  # noqa: E402
from sqlalchemy.pool import NullPool  # noqa: E402

from app.agent.call_recorder import CallRecorder  # noqa: E402
from app.agent.context_profile_repository import InMemoryContextProfileRepository  # noqa: E402
from app.agent.orchestrator import WowAgent, build_default_tool_registry  # noqa: E402
from app.agent.summary_repository import InMemorySummaryRepository, SqlSummaryRepository  # noqa: E402
from app.agent.user_settings_repository import InMemoryUserSettingsRepository  # noqa: E402
from app.api.deps import get_call_recorder, get_media_pipeline  # noqa: E402
from app.brain.state_repository import InMemoryStateRepository  # noqa: E402
from app.db.base import Base  # noqa: E402
from app.media.audio_codec import pcm16_to_mulaw, resample_pcm16  # noqa: E402
from app.media.pipeline import MediaPipeline  # noqa: E402
from app.models.call import Call  # noqa: E402
from app.models.conversation import Conversation  # noqa: E402
from app.models.summary import Summary  # noqa: E402
from app.models.transcript import Speaker, TranscriptSegment  # noqa: E402
from app.providers.llm.rule_based import RuleBasedLanguageModelProvider  # noqa: E402
from app.providers.stt.local_whisper import LocalWhisperSTTProvider  # noqa: E402
from app.providers.tts.local_piper import LocalPiperTTSProvider  # noqa: E402
from app.providers.vad.webrtc_vad import WebRtcVoiceActivityDetector  # noqa: E402
from tests.agent_fakes import FakeContextEngine  # noqa: E402

_FIXTURE = Path(__file__).parent / "fixtures" / "audio" / "meeting_context.wav"


def _read_pcm16(path: Path) -> tuple[bytes, int]:
    with wave.open(str(path), "rb") as w:
        return w.readframes(w.getnframes()), w.getframerate()


def _build_app_and_engine(db_path: Path, *, tts=None, voice_resolver=None):
    """A real file-backed SQLite database (not `:memory:`) - deliberately,
    not for lack of trying: TestClient runs the ASGI app, and every
    dependency it resolves, in its own background thread/event loop,
    separate from wherever this test function's own assertions run
    afterward, and an in-memory SQLite connection is bound to the specific
    thread/loop that created it - a file on disk has no such restriction,
    any thread can open its own fresh connection to the same real file.
    Real SQL either way, not a fake CallRecorder. Only the tables
    CallRecorder actually touches (not the full Base.metadata - `memories`
    needs a pgvector column type SQLite can't represent, and isn't used by
    this test's in-memory tool registry anyway)."""
    # NullPool: every checkout opens a brand-new connection rather than
    # reusing a pooled one - necessary because this engine's connections
    # get used from two different threads/event loops (this test
    # function's own, and TestClient's internal one), and an
    # asyncio-backed DBAPI connection (aiosqlite) checked out on one loop
    # is not safe to reuse from another.
    engine = create_async_engine(f"sqlite+aiosqlite:///{db_path}", future=True, poolclass=NullPool)
    session_factory = async_sessionmaker(bind=engine, expire_on_commit=False)

    async def _get_call_recorder():
        async with session_factory() as session:
            yield CallRecorder(session, SqlSummaryRepository(session))
            await session.commit()

    async def _get_media_pipeline():
        tools = build_default_tool_registry(
            InMemoryMemoryStoreForTest(),
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
            tts=tts if tts is not None else LocalPiperTTSProvider(),
            voice_resolver=voice_resolver,
        )

    from app.api.routes import telephony_plivo

    app = FastAPI()
    app.include_router(telephony_plivo.router)
    app.dependency_overrides[get_call_recorder] = _get_call_recorder
    app.dependency_overrides[get_media_pipeline] = _get_media_pipeline
    return app, engine, session_factory


class InMemoryMemoryStoreForTest:
    """RuleBasedLanguageModelProvider's SET_CONTEXT path doesn't touch
    memory, but build_default_tool_registry requires a MemoryStore -
    matches tests/agent_fakes.InMemoryMemoryStore's shape without
    importing it just for an unused dependency."""

    async def add(self, **kwargs):
        return "mem-1"

    async def search(self, **kwargs):
        return []


def _plivo_media_message(mulaw_chunk: bytes) -> str:
    return json.dumps(
        {"event": "media", "media": {"payload": base64.b64encode(mulaw_chunk).decode("ascii")}}
    )


async def _create_tables(engine):
    from app.models.user import User

    async with engine.begin() as conn:
        await conn.run_sync(
            Base.metadata.create_all,
            tables=[
                User.__table__,
                Call.__table__,
                Conversation.__table__,
                TranscriptSegment.__table__,
                Summary.__table__,
            ],
        )


def test_real_call_audio_travels_through_the_full_plivo_bridge(tmp_path):
    db_path = tmp_path / "test_telephony_plivo.db"
    app, engine, session_factory = _build_app_and_engine(db_path)

    import asyncio

    asyncio.run(_create_tables(engine))

    pcm16_16k, sr = _read_pcm16(_FIXTURE)
    assert sr == 16000

    # Simulate exactly what a real Plivo call actually delivers: telephony-
    # quality 8kHz mu-law, not our fixture's native 16kHz - the real
    # degradation path a live call goes through, not a shortcut.
    pcm16_8k = resample_pcm16(pcm16_16k, from_rate=16000, to_rate=8000)
    wire_mulaw = pcm16_to_mulaw(pcm16_8k)

    chunk_size = max(1, len(wire_mulaw) // 10)
    chunks = [wire_mulaw[i : i + chunk_size] for i in range(0, len(wire_mulaw), chunk_size)]

    client = TestClient(app)
    received: list[dict] = []
    with client.websocket_connect(authorized_stream_path()) as ws:
        ws.send_text(json.dumps({"event": "start", "start": {"from": "+919876543210"}}))
        for chunk in chunks:
            ws.send_text(_plivo_media_message(chunk))
        ws.send_text(json.dumps({"event": "stop"}))

        while True:
            try:
                raw = ws.receive_text()
            except Exception:
                break
            received.append(json.loads(raw))

    # 1. The real greeting was sent first, as real synthesized audio.
    assert received, "expected at least the greeting message"
    assert received[0]["event"] == "playAudio"
    greeting_mulaw = base64.b64decode(received[0]["media"]["payload"])
    assert len(greeting_mulaw) > 0

    # 2. A real reply to the real transcribed speech was sent back too.
    assert len(received) >= 2, f"expected a greeting + a real reply, got {received}"
    reply_mulaw = base64.b64decode(received[1]["media"]["payload"])
    assert len(reply_mulaw) > 0
    assert received[1]["media"]["contentType"] == "audio/x-mulaw"
    assert received[1]["media"]["sampleRate"] == 8000

    async def _fetch_rows():
        # A brand-new engine/connection to the same real file, not the
        # `engine`/`session_factory` TestClient's own background
        # thread/event loop already used above - see _build_app_and_engine's
        # docstring for why reusing those here would be unsafe.
        fetch_engine = create_async_engine(f"sqlite+aiosqlite:///{db_path}", future=True)
        fetch_session_factory = async_sessionmaker(bind=fetch_engine, expire_on_commit=False)
        async with fetch_session_factory() as session:
            calls = (await session.execute(select(Call))).scalars().all()
            conversations = (await session.execute(select(Conversation))).scalars().all()
            segments = (await session.execute(select(TranscriptSegment))).scalars().all()
            summaries = (await session.execute(select(Summary))).scalars().all()
        await fetch_engine.dispose()
        return calls, conversations, segments, summaries

    calls, conversations, segments, summaries = asyncio.run(_fetch_rows())
    # Dispose explicitly rather than rely on GC: an undisposed engine's
    # background aiosqlite thread can outlive this test's own event loop
    # (torn down by pytest-asyncio once this function returns) and then
    # warn/error trying to call back into an already-closed loop from a
    # later test - a test-infra timing artifact, not a production concern,
    # but real to fix rather than leave noisy.
    asyncio.run(engine.dispose())

    # 3. Real CallRecorder wiring: a real Call/Conversation row exists,
    # the real caller number was captured from the "start" event, and the
    # call is marked completed once the WebSocket closed.
    assert len(calls) == 1
    assert calls[0].caller_number == "+919876543210"
    assert calls[0].status.value == "completed"
    assert len(conversations) == 1

    # 4. Real transcript: the greeting, the real transcribed caller
    # speech (the actual fixture's real spoken words), and the real
    # agent's reply were all recorded - not fabricated placeholder rows.
    assert any(
        s.speaker == Speaker.ASSISTANT and s.text == "Hello." for s in segments
    )
    caller_segments = [s for s in segments if s.speaker == Speaker.CALLER]
    assert caller_segments, "expected the real transcribed caller utterance to be recorded"
    assert "meeting" in caller_segments[0].text.lower()
    assistant_replies = [s for s in segments if s.speaker == Speaker.ASSISTANT and s.text != "Hello."]
    assert assistant_replies, "expected a real recorded assistant reply"

    # 5. A real summary was written at call end.
    assert len(summaries) == 1
    assert "1 conversational turn" in summaries[0].summary_text


def test_multiple_sequential_turns_in_one_call_are_all_handled(tmp_path):
    """Real proof the bridge isn't a one-shot: two real, distinct
    utterances (hello.wav then meeting_context.wav, separated by real
    silence) sent over the same WebSocket connection must both be
    transcribed and replied to, not just the first."""
    db_path = tmp_path / "test_telephony_plivo_multiturn.db"
    app, engine, session_factory = _build_app_and_engine(db_path)

    import asyncio

    asyncio.run(_create_tables(engine))

    hello_pcm, sr1 = _read_pcm16(Path(__file__).parent / "fixtures" / "audio" / "hello.wav")
    meeting_pcm, sr2 = _read_pcm16(_FIXTURE)
    assert sr1 == 16000 and sr2 == 16000

    silence_gap = b"\x00\x00" * 16000  # 1s of real silence at 16kHz - lets VAD close turn 1
    combined_16k = hello_pcm + silence_gap + meeting_pcm

    combined_8k = resample_pcm16(combined_16k, from_rate=16000, to_rate=8000)
    wire_mulaw = pcm16_to_mulaw(combined_8k)
    chunk_size = max(1, len(wire_mulaw) // 40)
    chunks = [wire_mulaw[i : i + chunk_size] for i in range(0, len(wire_mulaw), chunk_size)]

    client = TestClient(app)
    received: list[dict] = []
    with client.websocket_connect(authorized_stream_path()) as ws:
        ws.send_text(json.dumps({"event": "start", "start": {"from": "+919876543210"}}))
        for chunk in chunks:
            ws.send_text(_plivo_media_message(chunk))
        ws.send_text(json.dumps({"event": "stop"}))

        while True:
            try:
                raw = ws.receive_text()
            except Exception:
                break
            received.append(json.loads(raw))

    # Greeting + at least 2 real replies (one per real utterance).
    assert len(received) >= 3, f"expected greeting + 2 replies, got {len(received)} messages"

    async def _fetch_segments():
        fetch_engine = create_async_engine(f"sqlite+aiosqlite:///{db_path}", future=True)
        fetch_session_factory = async_sessionmaker(bind=fetch_engine, expire_on_commit=False)
        async with fetch_session_factory() as session:
            segments = (await session.execute(select(TranscriptSegment))).scalars().all()
            summaries = (await session.execute(select(Summary))).scalars().all()
        await fetch_engine.dispose()
        return segments, summaries

    segments, summaries = asyncio.run(_fetch_segments())
    asyncio.run(engine.dispose())

    caller_segments = [s for s in segments if s.speaker == Speaker.CALLER]
    assert len(caller_segments) >= 2, (
        f"expected 2 separate real transcribed turns, got {[s.text for s in caller_segments]}"
    )
    combined_caller_text = " ".join(s.text.lower() for s in caller_segments)
    assert "hear" in combined_caller_text or "hello" in combined_caller_text
    assert "meeting" in combined_caller_text

    # Real VAD may legitimately split a fixture's own internal pause into
    # an extra turn beyond the 2 source utterances - the point proven here
    # is "more than one turn works in a single call", not a fragile exact
    # count tied to these specific fixtures' silence timing.
    assert len(summaries) == 1
    assert len(caller_segments) == turns_in_summary(summaries[0].summary_text)
    assert turns_in_summary(summaries[0].summary_text) >= 2


def turns_in_summary(summary_text: str) -> int:
    return int(summary_text.split(" conversational turn")[0].rsplit("(", 1)[-1])


def test_female_piper_voice_is_actually_resolved_and_sent_back(tmp_path):
    """Real proof the per-user female voice selection (already proven at
    the MediaPipeline layer in test_media_pipeline_voice_resolver.py, and
    wired into get_media_pipeline for every real route in app/api/deps.py)
    genuinely reaches the Plivo route too: a real User row with
    voice_gender=FEMALE, a real voice_resolver, and a spy on the real
    LocalPiperTTSProvider proving the actual resolved female voice id was
    used for the real greeting synthesis - not just that some voice was
    used."""
    import functools

    from app.media.voice_selection import resolve_user_voice
    from app.models.user import PreferredLanguage, User, VoiceGender

    db_path = tmp_path / "test_telephony_plivo_voice.db"

    class _SpyTTS(LocalPiperTTSProvider):
        def __init__(self):
            super().__init__()
            self.synthesize_voices: list[str | None] = []

        async def synthesize(self, text: str, *, voice: str | None = None) -> bytes:
            self.synthesize_voices.append(voice)
            return await super().synthesize(text, voice=voice)

    spy_tts = _SpyTTS()

    engine = create_async_engine(f"sqlite+aiosqlite:///{db_path}", future=True, poolclass=NullPool)
    session_factory = async_sessionmaker(bind=engine, expire_on_commit=False)

    async def _setup():
        async with engine.begin() as conn:
            await conn.run_sync(
                Base.metadata.create_all,
                tables=[User.__table__, Call.__table__, Conversation.__table__,
                        TranscriptSegment.__table__, Summary.__table__],
            )
        async with session_factory() as session:
            import uuid as uuid_module

            from app.config import get_settings

            session.add(
                User(
                    id=uuid_module.UUID(get_settings().demo_user_id),
                    display_name="Aniket",
                    phone_number="+910000000099",
                    preferred_language=PreferredLanguage.ENGLISH,
                    voice_gender=VoiceGender.FEMALE,
                )
            )
            await session.commit()

    import asyncio

    asyncio.run(_setup())

    voice_resolve_session_factory = async_sessionmaker(bind=engine, expire_on_commit=False)

    async def _voice_resolver(user_id: str) -> str | None:
        async with voice_resolve_session_factory() as session:
            return await resolve_user_voice(session, user_id)

    app, _, _ = _build_app_and_engine(db_path, tts=spy_tts, voice_resolver=_voice_resolver)

    client = TestClient(app)
    with client.websocket_connect(authorized_stream_path()) as ws:
        ws.send_text(json.dumps({"event": "start", "start": {"from": "+919876543210"}}))
        ws.send_text(json.dumps({"event": "stop"}))
        received_any = False
        while True:
            try:
                ws.receive_text()
                received_any = True
            except Exception:
                break

    asyncio.run(engine.dispose())

    assert received_any, "expected at least the real greeting to be sent"
    # The real female English Piper voice - see app/media/voice_selection.py -
    # not the generic DEFAULT_VOICE fallback, proving profile-based
    # resolution genuinely drove what was synthesized for this call.
    assert "en_US-hfc_female-medium" in spy_tts.synthesize_voices
