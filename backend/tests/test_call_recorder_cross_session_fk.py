"""Regression for a bug the Phase 1 live-validation rehearsal found on real
Postgres: WowAgent writes through its OWN session (agent_states,
feedback_events, memories - all with a foreign key to `conversations`), while
CallRecorder creates the Conversation in a different session whose
transaction used to stay open until the end of the call. The Conversation was
therefore invisible to the agent's session -> ForeignKeyViolation on the very
first turn, the agent session was poisoned (PendingRollbackError), and after 3
failed turns the live call ended. SQLite/in-memory tests cannot see this
(no cross-transaction FK visibility), so this one needs real Postgres."""

import os
import uuid

import pytest
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.agent.call_recorder import CallRecorder
from app.db.base import Base
from app.models.agent_state import AgentState
from app.models.call import CallDirection
from app.models.user import User

URL = os.environ.get("TEST_DATABASE_URL")
pytestmark = pytest.mark.skipif(not URL, reason="TEST_DATABASE_URL not set; skipping DB integration")


@pytest.fixture
async def factory():
    from sqlalchemy import text

    engine = create_async_engine(URL, future=True)
    async with engine.begin() as conn:
        await conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
        await conn.run_sync(Base.metadata.create_all)
    yield async_sessionmaker(bind=engine, expire_on_commit=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await engine.dispose()


async def _user(factory) -> uuid.UUID:
    uid = uuid.uuid4()
    async with factory() as s:
        s.add(User(id=uid, display_name="T", phone_number="+910000000000"))
        await s.commit()
    return uid


async def _agent_write(factory, user_id, conversation_id):
    async with factory() as agent_session:  # a different session, like WowAgent's
        agent_session.add(
            AgentState(user_id=user_id, conversation_id=conversation_id, state_key="k", state_value={})
        )
        await agent_session.commit()


async def test_uncommitted_conversation_is_invisible_to_the_agent_session(factory):
    """Documents the hazard: without a commit the agent's write fails."""
    uid = await _user(factory)
    async with factory() as recorder_session:
        _, conv = await CallRecorder(recorder_session).start_call(
            user_id=str(uid), caller_number="+911", direction=CallDirection.INBOUND
        )
        with pytest.raises(IntegrityError):
            await _agent_write(factory, uid, conv.id)


async def test_committing_after_start_call_lets_the_agent_session_write(factory):
    uid = await _user(factory)
    async with factory() as recorder_session:
        recorder = CallRecorder(recorder_session)
        _, conv = await recorder.start_call(
            user_id=str(uid), caller_number="+911", direction=CallDirection.INBOUND
        )
        await recorder.commit()  # what the Plivo route now does right after start_call
        await _agent_write(factory, uid, conv.id)  # must not raise
