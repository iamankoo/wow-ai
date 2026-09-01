"""End-to-end integration test for the feedback/self-learning loop against a
real Postgres instance - the SqlFeedbackRepository counterpart to
test_feedback_processor.py's InMemory-backed tests.

Requires TEST_DATABASE_URL (e.g. from `docker compose up db`). Skipped
automatically when that's not set, matching test_integration_db.py.
"""

import os

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.db.base import Base
from app.interfaces.feedback import FeedbackCategory, FeedbackSource, FeedbackStatus, FeedbackSubmission
from app.learning import personalization
from app.learning.candidate_builder import TrainingCandidateBuilder
from app.learning.feedback_processor import FeedbackProcessor
from app.learning.feedback_repository import SqlFeedbackRepository
from app.learning.privacy_filter import RegexPrivacyFilter
from app.learning.privacy_rights import PrivacyRightsService
from app.models.user import User

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


async def test_feedback_flows_from_submission_to_dataset_file(session, tmp_path):
    user = User(display_name="Aniket", phone_number="+10000000000", training_data_consent=True)
    session.add(user)
    await session.commit()

    repo = SqlFeedbackRepository(session)
    processor = FeedbackProcessor(repo, RegexPrivacyFilter())

    record = await repo.create(FeedbackSubmission(
        user_id=str(user.id),
        text="No, I'm actually in a meeting.",
        predicted_intent="SET_CONTEXT", predicted_context_mode="SLEEPING", predicted_action="SET_CONTEXT",
        corrected_context_mode="MEETING",
        source=FeedbackSource.EXPLICIT, category=FeedbackCategory.WRONG_CONTEXT,
        consent_for_training=True,
    ))
    await session.commit()

    candidate = await processor.process_one(record)
    await session.commit()
    assert candidate.status == FeedbackStatus.CANDIDATE

    approved = await processor.approve(candidate.id, reviewed_by="aniket")
    await session.commit()
    assert approved.status == FeedbackStatus.APPROVED

    result = await TrainingCandidateBuilder(repo, tmp_path).build("integration-batch")
    await session.commit()
    assert result.included_count == 1

    final = await repo.get(record.id)
    assert final.status == FeedbackStatus.INCLUDED


async def test_privacy_rights_operations_round_trip_through_sql(session):
    user = User(display_name="Priya", phone_number="+10000000001")
    session.add(user)
    await session.commit()

    repo = SqlFeedbackRepository(session)
    await repo.create(FeedbackSubmission(user_id=str(user.id), text="a", consent_for_training=True))
    await session.commit()

    rights = PrivacyRightsService(repo)
    export = await rights.export_feedback(str(user.id))
    assert len(export.events) == 1

    deleted = await rights.delete_feedback(str(user.id))
    await session.commit()
    assert deleted == 1


async def test_disable_learning_and_reset_personalization(session):
    from app.models.memory import Memory

    user = User(display_name="Rahul", phone_number="+10000000002", training_data_consent=True)
    session.add(user)
    await session.flush()
    session.add(Memory(user_id=user.id, content="Prefers family calls treated as high priority."))
    await session.commit()

    await personalization.set_training_data_consent(session, str(user.id), False)
    await session.commit()
    assert await personalization.get_training_data_consent(session, str(user.id)) is False

    deleted = await personalization.reset_personalization(session, str(user.id))
    await session.commit()
    assert deleted == 1
