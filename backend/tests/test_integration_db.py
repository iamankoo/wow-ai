"""End-to-end integration test against a real Postgres + pgvector instance.

Requires TEST_DATABASE_URL (e.g. from `docker compose up db`). Skipped
automatically when that's not set, so the rest of the suite stays
DB-independent.
"""

import os
import uuid

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker

from datetime import datetime, timedelta, timezone

from app.agent.call_recorder import CallRecorder
from app.agent.context_profile_repository import SqlContextProfileRepository
from app.agent.orchestrator import WowAgent, build_default_tool_registry
from app.agent.summary_repository import SqlSummaryRepository
from app.agent.user_settings_repository import SqlUserSettingsRepository
from app.db.base import Base
from app.interfaces.memory_store import MemoryStatus, MemoryType
from app.learning.call_retention import CallRetentionPolicy, cleanup_expired_calls
from app.models.call import Call, CallDirection, CallStatus
from app.models.contact import Contact
from app.models.context import ContextProfile
from app.models.conversation import Conversation, ConversationStatus
from app.models.summary import Summary
from app.models.transcript import Speaker, TranscriptSegment
from app.models.user import User
from app.brain.context_engine import DefaultContextEngine
from app.brain.state_repository import SqlStateRepository
from app.brain.wow_brain import WowBrain
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


async def test_full_brain_flow_against_real_db(session):
    user = User(display_name="Aniket", phone_number="+10000000000")
    session.add(user)
    await session.flush()

    contact = Contact(
        user_id=user.id,
        name="Priya",
        phone_number="+19999999999",
        relationship="friend",
    )
    session.add(contact)

    profile = ContextProfile(
        user_id=user.id,
        contact_id=None,
        name="default",
        instructions="Be polite and take a message if I'm unavailable.",
        is_active=True,
    )
    session.add(profile)
    await session.commit()

    memory_store = PgVectorMemoryStore(session)
    await memory_store.add(
        user_id=str(user.id),
        content="Priya mentioned she's visiting next month.",
    )
    await session.commit()

    context_engine = DefaultContextEngine(session, memory_store)
    state_repo = SqlStateRepository(session)
    brain = WowBrain(RuleBasedLanguageModelProvider(), context_engine, state_repo)

    action = await brain.handle_input(
        user_id=str(user.id),
        text="Is he available right now?",
        caller_number="+19999999999",
    )
    await session.commit()

    assert action.type == "check_availability"
    assert action.payload["contact"]["name"] == "Priya"
    assert action.payload["context_profile"]["name"] == "default"

    results = await memory_store.search(user_id=str(user.id), query="visiting")
    assert any("visiting" in r.content for r in results)


async def test_memory_type_filter_status_approve_and_soft_delete(session):
    user = User(display_name="Aniket", phone_number="+10000000001")
    session.add(user)
    await session.flush()

    memory_store = PgVectorMemoryStore(session)
    semantic_id = await memory_store.add(
        user_id=str(user.id), content="Prefers tea over coffee.", memory_type=MemoryType.SEMANTIC
    )
    episodic_id = await memory_store.add(
        user_id=str(user.id),
        content="Called about the March invoice.",
        memory_type=MemoryType.EPISODIC,
    )
    await session.commit()

    only_episodic = await memory_store.search(
        user_id=str(user.id), query="", memory_type=MemoryType.EPISODIC
    )
    assert {r.id for r in only_episodic} == {episodic_id}

    all_records = await memory_store.search(user_id=str(user.id), query="")
    stored = {r.id: r for r in all_records}
    assert stored[semantic_id].status == MemoryStatus.OBSERVED

    approved = await memory_store.approve(user_id=str(user.id), memory_id=semantic_id)
    assert approved is True
    await session.commit()
    refreshed = {r.id: r for r in await memory_store.search(user_id=str(user.id), query="")}
    assert refreshed[semantic_id].status == MemoryStatus.USER_APPROVED

    deleted = await memory_store.delete(user_id=str(user.id), memory_id=episodic_id)
    assert deleted is True
    await session.commit()
    remaining = await memory_store.search(user_id=str(user.id), query="")
    assert episodic_id not in {r.id for r in remaining}

    # Deleting again is not an error - "already gone" is a success state.
    assert await memory_store.delete(user_id=str(user.id), memory_id=episodic_id) is False
    # Deleting/approving another user's memory (or a nonexistent id) never
    # succeeds - this is the cross-user isolation check.
    assert await memory_store.delete(user_id=str(uuid.uuid4()), memory_id=semantic_id) is False


async def test_simulated_call_persists_call_history_via_recorder(session):
    user = User(display_name="Aniket", phone_number="+10000000002")
    session.add(user)
    await session.flush()
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
        caller_number="+19999999998",
        script=["Hi there!", "Can you take a message for him?", "Thanks, bye!"],
        recorder=recorder,
    )
    await session.commit()

    call_row = await session.get(Call, uuid.UUID(result.call_id))
    assert call_row is not None
    assert call_row.status == CallStatus.COMPLETED
    assert call_row.ended_at is not None
    assert call_row.caller_number == "+19999999998"

    conv_stmt = select(Conversation).where(Conversation.call_id == call_row.id)
    conversation = (await session.execute(conv_stmt)).scalars().first()
    assert conversation is not None
    assert conversation.status == ConversationStatus.COMPLETED

    segments_stmt = select(TranscriptSegment).where(
        TranscriptSegment.conversation_id == conversation.id
    )
    segments = (await session.execute(segments_stmt)).scalars().all()
    # 3 script turns x (caller + assistant) = 6 transcript segments.
    assert len(segments) == 6

    summary_stmt = select(Summary).where(Summary.conversation_id == conversation.id)
    summary = (await session.execute(summary_stmt)).scalars().first()
    assert summary is not None
    assert "Caller" in summary.summary_text and "WOW" in summary.summary_text


async def test_set_context_tool_writes_a_profile_default_context_engine_can_read(session):
    """Proves the ContextProfile write path (SqlContextProfileRepository /
    set_context tool) and the pre-existing read path (DefaultContextEngine)
    agree against a real database: a SET_CONTEXT action executed through the
    full WowAgent stack must be visible to the very next turn's context
    lookup, not just to a direct row query."""
    user = User(display_name="Aniket", phone_number="+10000000004")
    session.add(user)
    await session.flush()
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

    from app.interfaces.llm import LLMResponse

    class _StubLLM:
        async def generate(self, messages, *, context=None):
            return LLMResponse(
                content="",
                intent="SET_CONTEXT",
                slots={"action": "SET_CONTEXT", "context_mode": "MEETING"},
                metadata={"confidence": {"intent": 0.97, "action": 0.95, "context_mode": 0.95}},
            )

    agent._llm = _StubLLM()  # swap the provider only - everything else is the real stack

    action = await agent.handle_input(
        user_id=str(user.id), text="I'm in a meeting, handle my calls", conversation_id="conv-ctx"
    )
    await session.commit()

    assert action.payload["policy_decision"] == "allow"
    assert action.payload["tool_results"] == [
        {"tool": "set_context", "success": True, "error": None}
    ]

    stmt = select(ContextProfile).where(
        ContextProfile.user_id == user.id, ContextProfile.is_active.is_(True)
    )
    row = (await session.execute(stmt)).scalars().first()
    assert row is not None
    assert row.name == "MEETING"

    # The read side (already pre-existing) must independently see the same row.
    built_context = await context_engine.build_context(user_id=str(user.id))
    assert built_context.context_profile is not None
    assert built_context.context_profile["name"] == "MEETING"


async def test_user_settings_repository_persists_call_assistant_flag(session):
    user = User(display_name="Aniket", phone_number="+10000000005")
    session.add(user)
    await session.flush()
    await session.commit()

    repo = SqlUserSettingsRepository(session)
    assert await repo.set_call_assistant_enabled(user_id=str(user.id), enabled=True) is True
    await session.commit()

    await session.refresh(user)
    assert user.call_assistant_enabled is True

    assert await repo.set_call_assistant_enabled(user_id=str(uuid.uuid4()), enabled=True) is False


async def test_run_simulated_call_rejects_explicit_ids_when_recorder_given(session):
    user = User(display_name="Aniket", phone_number="+10000000003")
    session.add(user)
    await session.flush()
    await session.commit()

    memory_store = PgVectorMemoryStore(session)
    context_engine = DefaultContextEngine(session, memory_store)
    tools = build_default_tool_registry(
        memory_store,
        SqlSummaryRepository(session),
        SqlContextProfileRepository(session),
        SqlUserSettingsRepository(session),
    )
    agent = WowAgent(
        RuleBasedLanguageModelProvider(), context_engine, SqlStateRepository(session), tools
    )
    recorder = CallRecorder(session, SqlSummaryRepository(session))

    with pytest.raises(ValueError):
        await run_simulated_call(
            agent=agent,
            stt=SimulatedSTTProvider(),
            tts=SimulatedTTSProvider(),
            telephony=SimulatedTelephonyProvider(),
            user_id=str(user.id),
            caller_number=None,
            script=["Hi!"],
            recorder=recorder,
            conversation_id="not-allowed",
        )


async def test_cleanup_expired_calls_only_removes_old_completed_calls(session):
    user = User(display_name="Aniket", phone_number="+10000000004")
    session.add(user)
    await session.flush()

    now = datetime.now(timezone.utc)
    old_completed = Call(
        user_id=user.id,
        caller_number="+1111111111",
        direction=CallDirection.INBOUND,
        status=CallStatus.COMPLETED,
        started_at=now - timedelta(days=20, minutes=5),
        ended_at=now - timedelta(days=20),
    )
    recent_completed = Call(
        user_id=user.id,
        caller_number="+2222222222",
        direction=CallDirection.INBOUND,
        status=CallStatus.COMPLETED,
        started_at=now - timedelta(days=5, minutes=5),
        ended_at=now - timedelta(days=5),
    )
    old_active = Call(
        user_id=user.id,
        caller_number="+3333333333",
        direction=CallDirection.INBOUND,
        status=CallStatus.ACTIVE,
        started_at=now - timedelta(days=20),
        ended_at=None,
    )
    session.add_all([old_completed, recent_completed, old_active])
    await session.flush()

    old_conversation = Conversation(
        user_id=user.id, call_id=old_completed.id, status=ConversationStatus.COMPLETED
    )
    session.add(old_conversation)
    await session.flush()
    session.add(TranscriptSegment(conversation_id=old_conversation.id, speaker=Speaker.CALLER, text="hi"))
    session.add(Summary(conversation_id=old_conversation.id, summary_text="old call summary"))
    await session.commit()

    deleted = await cleanup_expired_calls(session, CallRetentionPolicy(max_age_days=15), now=now)
    await session.commit()

    assert deleted == 1
    assert await session.get(Call, old_completed.id) is None
    assert await session.get(Conversation, old_conversation.id) is None
    assert await session.get(Call, recent_completed.id) is not None
    assert await session.get(Call, old_active.id) is not None  # never deleted regardless of age

    remaining_segments = (
        await session.execute(
            select(TranscriptSegment).where(TranscriptSegment.conversation_id == old_conversation.id)
        )
    ).scalars().all()
    assert remaining_segments == []
