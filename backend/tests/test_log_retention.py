from datetime import timedelta

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

import app.scheduler as scheduler
from app.models.connection_log import ConnectionLog
from app.repositories import connection_log as connection_log_repo
from app.scheduler import purge_old_connection_logs
from app.utils import now

pytestmark = pytest.mark.asyncio


async def test_purges_only_logs_older_than_retention(db_session, monkeypatch):
    # purge_old_connection_logs opens its own short-lived session; bind it to
    # the test's connection so it sees these rows and rolls back with them.
    conn = await db_session.connection()
    factory = async_sessionmaker(
        bind=conn, class_=AsyncSession, expire_on_commit=False,
        join_transaction_mode="create_savepoint",
    )
    monkeypatch.setattr(scheduler, "AsyncSessionLocal", factory)

    old = await connection_log_repo.create(
        db_session, connection_type="API", status="success", created_at=now() - timedelta(days=120),
    )
    fresh = await connection_log_repo.create(db_session, connection_type="API", status="success")
    await db_session.flush()

    deleted = await purge_old_connection_logs()

    assert deleted == 1
    remaining_ids = (await db_session.execute(
        select(ConnectionLog.id).where(ConnectionLog.id.in_([old.id, fresh.id]))
    )).scalars().all()
    assert remaining_ids == [fresh.id]
