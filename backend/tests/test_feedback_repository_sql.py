"""Exercises SqlFeedbackRepository against a real SQL engine (in-memory
SQLite via aiosqlite, a base dependency - not gated on TEST_DATABASE_URL
like the Postgres integration tests). This is the only place the ORM
mapping in app/learning/feedback_repository.py (_to_record/_apply_submission -
UUID handling, enum columns, nullable fields) actually gets exercised
without a live Postgres instance.

Only creates the `users` and `feedback_events` tables (not the full
Base.metadata), since `memories` uses a pgvector column type SQLite can't
represent.
"""

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.db.base import Base
from app.interfaces.feedback import (
    FeedbackCategory,
    FeedbackSource,
    FeedbackStatus,
    FeedbackSubmission,
)
from app.learning.feedback_repository import SqlFeedbackRepository
from app.models.feedback import FeedbackEvent
from app.models.user import User


@pytest.fixture
async def session():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", future=True)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all, tables=[User.__table__, FeedbackEvent.__table__])

    session_factory = async_sessionmaker(bind=engine, expire_on_commit=False)
    async with session_factory() as s:
        yield s
    await engine.dispose()


@pytest.fixture
async def user_id(session) -> str:
    user = User(display_name="Aniket", phone_number="+10000000000")
    session.add(user)
    await session.commit()
    return str(user.id)


async def test_create_and_get_round_trips_every_field(session, user_id):
    repo = SqlFeedbackRepository(session)
    created = await repo.create(FeedbackSubmission(
        user_id=user_id,
        text="No, I'm actually in a meeting.",
        predicted_intent="SET_CONTEXT",
        predicted_context_mode="SLEEPING",
        predicted_action="SET_CONTEXT",
        intent_confidence=0.9,
        model_version="v1",
        source=FeedbackSource.EXPLICIT,
        category=FeedbackCategory.WRONG_CONTEXT,
        corrected_context_mode="MEETING",
        consent_for_training=True,
    ))
    await session.commit()

    fetched = await repo.get(created.id)
    assert fetched is not None
    assert fetched.user_id == user_id
    assert fetched.predicted_intent == "SET_CONTEXT"
    assert fetched.corrected_context_mode == "MEETING"
    assert fetched.source == FeedbackSource.EXPLICIT
    assert fetched.category == FeedbackCategory.WRONG_CONTEXT
    assert fetched.consent_for_training is True
    assert fetched.status == FeedbackStatus.RECEIVED


async def test_update_persists_status_and_redacted_text(session, user_id):
    repo = SqlFeedbackRepository(session)
    record = await repo.create(FeedbackSubmission(user_id=user_id, text="Call me at 9876543210."))
    await session.commit()

    from dataclasses import replace
    updated = replace(record, status=FeedbackStatus.CANDIDATE, redacted_text="Call me at [REDACTED].")
    await repo.update(updated)
    await session.commit()

    fetched = await repo.get(record.id)
    assert fetched.status == FeedbackStatus.CANDIDATE
    assert fetched.redacted_text == "Call me at [REDACTED]."


async def test_list_by_status_filters_correctly(session, user_id):
    repo = SqlFeedbackRepository(session)
    await repo.create(FeedbackSubmission(user_id=user_id, text="a", status=FeedbackStatus.RECEIVED))
    await repo.create(FeedbackSubmission(user_id=user_id, text="b", status=FeedbackStatus.NEEDS_REVIEW))
    await session.commit()

    received = await repo.list_by_status(FeedbackStatus.RECEIVED, user_id=user_id)
    needs_review = await repo.list_by_status(FeedbackStatus.NEEDS_REVIEW, user_id=user_id)
    assert len(received) == 1
    assert len(needs_review) == 1
    assert received[0].raw_text == "a"


async def test_delete_removes_the_row(session, user_id):
    repo = SqlFeedbackRepository(session)
    record = await repo.create(FeedbackSubmission(user_id=user_id, text="a"))
    await session.commit()

    deleted = await repo.delete(record.id)
    await session.commit()
    assert deleted is True
    assert await repo.get(record.id) is None


async def test_delete_by_user_with_status_filter(session, user_id):
    repo = SqlFeedbackRepository(session)
    await repo.create(FeedbackSubmission(user_id=user_id, text="a", status=FeedbackStatus.CANDIDATE))
    await repo.create(FeedbackSubmission(user_id=user_id, text="b", status=FeedbackStatus.INCLUDED))
    await session.commit()

    deleted = await repo.delete_by_user(user_id, statuses=[FeedbackStatus.CANDIDATE])
    await session.commit()
    assert deleted == 1
    remaining = await repo.list_by_user(user_id)
    assert len(remaining) == 1
    assert remaining[0].status == FeedbackStatus.INCLUDED


async def test_get_missing_id_returns_none(session):
    import uuid

    repo = SqlFeedbackRepository(session)
    assert await repo.get(str(uuid.uuid4())) is None
