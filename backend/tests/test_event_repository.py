import pytest

from app.core.repositories import event as event_repo

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


async def test_pending_skips_rows_locked_by_another_txn(_engine):
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
    from app.core.repositories import event as event_repo

    factory = async_sessionmaker(_engine, class_=AsyncSession, expire_on_commit=False)

    async with factory() as seed, seed.begin():
        e = await event_repo.add(seed, "probe.evt", {"n": 1})
        seed_id = e.id

    conn_a = await _engine.connect()
    trans_a = await conn_a.begin()
    sess_a = AsyncSession(bind=conn_a, expire_on_commit=False)
    try:
        locked = await event_repo.pending(sess_a, 10)
        assert seed_id in [x.id for x in locked]

        async with factory() as sess_b, sess_b.begin():
            others = await event_repo.pending(sess_b, 10)
            assert seed_id not in [x.id for x in others]
    finally:
        await sess_a.close()
        await trans_a.rollback()
        await conn_a.close()
        async with factory() as cleanup, cleanup.begin():
            row = await event_repo.get(cleanup, seed_id) if hasattr(event_repo, "get") else None
            if row is not None:
                await cleanup.delete(row)
            else:
                from app.core.models.event import DomainEvent
                obj = await cleanup.get(DomainEvent, seed_id)
                if obj:
                    await cleanup.delete(obj)
