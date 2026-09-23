import pytest

from app.features.analytics.repositories import executive_brief as brief_repo

pytestmark = pytest.mark.asyncio


async def test_latest_returns_none_when_empty(db_session):
    assert await brief_repo.latest(db_session) is None


async def test_create_and_latest_returns_most_recent(db_session):
    await brief_repo.create(db_session, "first", "ok")
    await db_session.flush()
    second = await brief_repo.create(db_session, "second", "ok")
    await db_session.flush()

    latest = await brief_repo.latest(db_session)
    assert latest.id == second.id
    assert latest.content == "second"
