import pytest

from app.repositories import event as event_repo

pytestmark = pytest.mark.asyncio


async def test_add_and_pending(db_session):
    e1 = await event_repo.add(db_session, "user.created", {"id": "1"})
    e2 = await event_repo.add(db_session, "user.created", {"id": "2"})
    await db_session.flush()

    pending = await event_repo.pending(db_session, 10)
    assert [e.id for e in pending] == [e1.id, e2.id]


async def test_mark_dispatched_excludes_from_pending(db_session):
    e1 = await event_repo.add(db_session, "user.created", {"id": "1"})
    await db_session.flush()

    await event_repo.mark_dispatched(db_session, e1)
    await db_session.flush()

    pending = await event_repo.pending(db_session, 10)
    assert pending == []
    assert e1.dispatched_at is not None
