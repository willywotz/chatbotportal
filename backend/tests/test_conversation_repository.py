import uuid
from datetime import datetime

import pytest

from app.features.chat.repositories import conversation as repo

pytestmark = pytest.mark.asyncio


async def test_by_id_present_and_absent(db_session):
    c = await repo.create(db_session, title="t", agencies=[], status="active")
    await db_session.flush()
    assert (await repo.by_id(db_session, c.id)).id == c.id
    assert await repo.by_id(db_session, uuid.uuid4()) is None


async def test_by_id_exclude_deleted(db_session):
    c = await repo.create(
        db_session, title="t", agencies=[], status="active", deleted_at=datetime.now())
    await db_session.flush()
    assert (await repo.by_id(db_session, c.id)) is not None                      # no filter -> found
    assert await repo.by_id(db_session, c.id, exclude_deleted=True) is None      # filtered out


async def test_list_and_count_filters_and_pages(db_session):
    u_id = uuid.uuid4()
    for i in range(3):
        await repo.create(
            db_session, title=f"keep {i}", agencies=["dga"], status="active", user_id=u_id)
    await repo.create(db_session, title="other", agencies=[], status="active", user_id=u_id)
    await db_session.flush()
    rows, total = await repo.list_and_count(
        db_session, user_id=u_id, title_contains="keep", agency_contains=None,
        created_from=None, created_to=None, offset=0, limit=2)
    assert total == 3 and len(rows) == 2                                          # total is pre-page count


async def test_list_and_count_agency_contains(db_session):
    await repo.create(db_session, title="a", agencies=["dga"], status="active")
    await repo.create(db_session, title="b", agencies=["other"], status="active")
    await db_session.flush()
    rows, total = await repo.list_and_count(
        db_session, user_id=None, title_contains=None, agency_contains="dga",
        created_from=None, created_to=None, offset=None, limit=None)
    assert total == 1 and rows[0].title == "a"


async def test_save_partial_and_delete(db_session):
    c = await repo.create(db_session, title="t", agencies=[], status="active")
    await db_session.flush()
    c.external_session_id = "sess-1"
    await repo.save(db_session, c, update_fields=["external_session_id"])
    assert (await repo.by_id(db_session, c.id)).external_session_id == "sess-1"
    await repo.delete(db_session, c)
    await db_session.flush()
    assert await repo.by_id(db_session, c.id) is None
