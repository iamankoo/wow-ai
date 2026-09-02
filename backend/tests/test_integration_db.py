"""End-to-end integration test against a real Postgres + pgvector instance.

Requires TEST_DATABASE_URL (e.g. from `docker compose up db`). Skipped
automatically when that's not set, so the rest of the suite stays
DB-independent.
"""

import os
import uuid

import pytest
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker

from app.db.base import Base
from app.interfaces.memory_store import MemoryStatus, MemoryType
from app.models.contact import Contact
from app.models.context import ContextProfile
from app.models.user import User
from app.brain.context_engine import DefaultContextEngine
from app.brain.state_repository import SqlStateRepository
from app.brain.wow_brain import WowBrain
from app.providers.llm.rule_based import RuleBasedLanguageModelProvider
from app.providers.memory.pgvector_store import PgVectorMemoryStore

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
