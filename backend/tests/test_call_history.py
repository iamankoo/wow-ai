"""Phase 6 Part M - real call-history routes, verified against real Call/
Conversation/TranscriptSegment/Summary rows written by the same
CallRecorder + run_simulated_call path Block 5/6/7 already use, against a
real Postgres instance. Requires TEST_DATABASE_URL - skipped otherwise.
"""

import os
import uuid

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.agent.call_recorder import CallRecorder
from app.agent.context_profile_repository import SqlContextProfileRepository
from app.agent.orchestrator import WowAgent, build_default_tool_registry
from app.agent.summary_repository import SqlSummaryRepository
from app.agent.user_settings_repository import SqlUserSettingsRepository
from app.api.deps import get_db
from app.api.routes import calls
from app.brain.context_engine import DefaultContextEngine
from app.brain.state_repository import SqlStateRepository
from app.db.base import Base
from app.models.contact import Contact
from app.models.user import User
from app.providers.llm.rule_based import RuleBasedLanguageModelProvider
from app.providers.memory.pgvector_store import PgVectorMemoryStore
from app.providers.stt.simulated import SimulatedSTTProvider
from app.providers.telephony.simulated import SimulatedTelephonyProvider
from app.providers.tts.simulated import SimulatedTTSProvider
from app.simulation.call_simulator import run_simulated_call

TEST_DATABASE_URL = os.environ.get("TEST_DATABASE_URL")

pytestmark = pytest.mark.skipif(
    not TEST_DATABASE_URL, reason="TEST_DATABASE_URL not set; skipping DB integration"
)


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


async def _make_client(session) -> AsyncClient:
    app = FastAPI()
    app.include_router(calls.router)
    app.dependency_overrides[get_db] = lambda: session
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://test")


async def test_call_list_and_detail_reflect_a_real_handled_call(session):
    user = User(display_name="Aniket", phone_number="+10000000020")
    session.add(user)
    await session.flush()
    contact = Contact(user_id=user.id, name="Priya", phone_number="+19999999997")
    session.add(contact)
    await session.commit()

    memory_store = PgVectorMemoryStore(session)
    context_engine = DefaultContextEngine(session, memory_store)
    state_repo = SqlStateRepository(session)
    tools = build_default_tool_registry(
        memory_store,
        SqlSummaryRepository(session),
        SqlContextProfileRepository(session),
        SqlUserSettingsRepository(session),
    )
    agent = WowAgent(RuleBasedLanguageModelProvider(), context_engine, state_repo, tools)
    recorder = CallRecorder(session, SqlSummaryRepository(session))

    result = await run_simulated_call(
        agent=agent,
        stt=SimulatedSTTProvider(),
        tts=SimulatedTTSProvider(),
        telephony=SimulatedTelephonyProvider(),
        user_id=str(user.id),
        caller_number="+19999999997",
        contact_id=str(contact.id),  # real caller of this API resolves this itself -
        # see app.brain.context_engine.DefaultContextEngine._find_contact
        script=["Hi there!", "Can you take a message for him?", "Thanks, bye!"],
        recorder=recorder,
    )
    await session.commit()

    client = await _make_client(session)
    async with client:
        list_resp = await client.get(f"/users/{user.id}/calls")
        assert list_resp.status_code == 200
        items = list_resp.json()
        assert len(items) == 1
        assert items[0]["id"] == result.call_id
        assert items[0]["caller_number"] == "+19999999997"
        assert items[0]["caller_name"] == "Priya"  # real contact join, not guessed
        assert items[0]["status"] == "completed"
        assert items[0]["has_summary"] is True

        detail_resp = await client.get(f"/calls/{result.call_id}")
        assert detail_resp.status_code == 200
        detail = detail_resp.json()
        assert len(detail["transcript"]) == 6  # 3 script turns x (caller + assistant)
        assert detail["summary"] is not None
        assert "Caller" in detail["summary"]["summary_text"]

        summary_resp = await client.get(f"/users/{user.id}/calls/today-summary")
        assert summary_resp.status_code == 200
        today = summary_resp.json()
        assert today["calls_handled"] == 1
        assert today["unique_callers"] == 1


async def test_call_detail_404_for_unknown_id(session):
    client = await _make_client(session)
    async with client:
        resp = await client.get(f"/calls/{uuid.uuid4()}")
    assert resp.status_code == 404


async def test_empty_call_list_for_user_with_no_calls(session):
    user = User(display_name="Aniket", phone_number="+10000000021")
    session.add(user)
    await session.flush()
    await session.commit()

    client = await _make_client(session)
    async with client:
        resp = await client.get(f"/users/{user.id}/calls")
        assert resp.status_code == 200
        assert resp.json() == []

        today_resp = await client.get(f"/users/{user.id}/calls/today-summary")
        assert today_resp.json() == {
            "calls_handled": 0,
            "unique_callers": 0,
            "total_seconds": 0,
        }


async def test_real_incoming_call_via_brain_command_route_is_recorded(session):
    """The real path WowCallScreeningService.kt hits - proves the actual
    production /brain/command route (not just run_simulated_call) now
    writes a real, honest Call row: no fabricated transcript (Android
    doesn't let this app capture live call audio), just the real caller
    number, real timestamp, and a factual summary of what really
    happened (WOW screened it)."""
    from app.api.routes import brain

    user = User(display_name="Aniket", phone_number="+10000000022")
    session.add(user)
    await session.flush()
    await session.commit()

    app = FastAPI()
    app.include_router(brain.router)

    async def _get_call_recorder():
        from app.agent.call_recorder import CallRecorder
        from app.agent.summary_repository import SqlSummaryRepository

        yield CallRecorder(session, SqlSummaryRepository(session))
        await session.commit()

    from app.api.deps import get_brain, get_call_recorder
    from app.brain.context_engine import DefaultContextEngine
    from app.brain.wow_brain import WowBrain

    async def _get_brain():
        memory_store = PgVectorMemoryStore(session)
        context_engine = DefaultContextEngine(session, memory_store)
        state_repo = SqlStateRepository(session)
        yield WowBrain(RuleBasedLanguageModelProvider(), context_engine, state_repo)
        await session.commit()

    app.dependency_overrides[get_brain] = _get_brain
    app.dependency_overrides[get_call_recorder] = _get_call_recorder

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post(
            "/brain/command",
            json={
                "user_id": str(user.id),
                "text": "[system] incoming call",
                "caller_number": "+18885551234",
            },
        )
    assert resp.status_code == 200

    calls_client = await _make_client(session)
    async with calls_client:
        list_resp = await calls_client.get(f"/users/{user.id}/calls")
    items = list_resp.json()
    assert len(items) == 1
    assert items[0]["caller_number"] == "+18885551234"
    assert items[0]["status"] == "completed"

    detail_resp_client = await _make_client(session)
    async with detail_resp_client:
        detail_resp = await detail_resp_client.get(f"/calls/{items[0]['id']}")
    detail = detail_resp.json()
    assert detail["transcript"] == []  # no fabricated dialogue
    assert "+18885551234" in detail["summary"]["summary_text"]
