import pytest

from app.interfaces.feedback import FeedbackStatus, FeedbackSubmission
from app.learning.feedback_repository import InMemoryFeedbackRepository
from app.learning.privacy_rights import PrivacyRightsService


@pytest.fixture
def repo() -> InMemoryFeedbackRepository:
    return InMemoryFeedbackRepository()


@pytest.fixture
def rights(repo) -> PrivacyRightsService:
    return PrivacyRightsService(repo)


async def test_delete_all_feedback_for_a_user(repo, rights):
    await repo.create(FeedbackSubmission(user_id="u1", text="a"))
    await repo.create(FeedbackSubmission(user_id="u1", text="b"))
    await repo.create(FeedbackSubmission(user_id="u2", text="c"))

    deleted = await rights.delete_feedback("u1")
    assert deleted == 2
    assert await repo.list_by_user("u1") == []
    assert len(await repo.list_by_user("u2")) == 1


async def test_delete_one_feedback_event_by_id(repo, rights):
    r1 = await repo.create(FeedbackSubmission(user_id="u1", text="a"))
    await repo.create(FeedbackSubmission(user_id="u1", text="b"))

    deleted = await rights.delete_feedback("u1", feedback_id=r1.id)
    assert deleted == 1
    remaining = await repo.list_by_user("u1")
    assert len(remaining) == 1
    assert remaining[0].raw_text == "b"


async def test_cannot_delete_another_users_feedback_by_id(repo, rights):
    other = await repo.create(FeedbackSubmission(user_id="u2", text="not yours"))
    deleted = await rights.delete_feedback("u1", feedback_id=other.id)
    assert deleted == 0
    assert await repo.get(other.id) is not None


async def test_delete_training_candidates_only_removes_unincluded_statuses(repo, rights):
    candidate = await repo.create(FeedbackSubmission(user_id="u1", text="a", status=FeedbackStatus.CANDIDATE))
    included = await repo.create(FeedbackSubmission(user_id="u1", text="b", status=FeedbackStatus.INCLUDED))

    deleted = await rights.delete_training_candidates("u1")
    assert deleted == 1
    assert await repo.get(candidate.id) is None
    assert await repo.get(included.id) is not None  # already merged into a dataset - can't un-merge


async def test_export_feedback_returns_everything_for_the_user(repo, rights):
    await repo.create(FeedbackSubmission(user_id="u1", text="a"))
    await repo.create(FeedbackSubmission(user_id="u1", text="b"))
    export = await rights.export_feedback("u1")
    assert export.user_id == "u1"
    assert len(export.events) == 2


async def test_list_feedback_used_for_training_only_returns_included(repo, rights):
    await repo.create(FeedbackSubmission(user_id="u1", text="a", status=FeedbackStatus.CANDIDATE))
    await repo.create(FeedbackSubmission(user_id="u1", text="b", status=FeedbackStatus.INCLUDED))
    used = await rights.list_feedback_used_for_training("u1")
    assert len(used) == 1
    assert used[0].raw_text == "b"
