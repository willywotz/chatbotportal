import pytest

from app.repositories import agency as agency_repo

pytestmark = pytest.mark.asyncio


async def test_increment_calls_is_atomic(db_session):
    a = await agency_repo.create(db_session, name="A", total_calls=0)
    await db_session.flush()
    await agency_repo.increment_calls(db_session, a)
    assert a.total_calls == 1


async def test_list_and_count_filters_search(db_session):
    await agency_repo.create(db_session, name="Alpha")
    await agency_repo.create(db_session, name="Beta")
    await db_session.flush()
    rows, total = await agency_repo.list_and_count(
        db_session, status="all", connection_type=None, search_text="alph")
    assert total == 1 and rows[0].name == "Alpha"
