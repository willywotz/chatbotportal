import uuid
from datetime import datetime, timedelta

import pytest

from app.repositories import connection_log as cl_repo

pytestmark = pytest.mark.asyncio


async def test_create_and_get(db_session):
    log = await cl_repo.create(db_session, connection_type="MCP", status="success")
    fetched = await cl_repo.get(db_session, log.id)
    assert fetched.id == log.id
    assert await cl_repo.get(db_session, uuid.uuid4()) is None


async def test_delete_older_than(db_session):
    old = await cl_repo.create(db_session, connection_type="MCP", status="success")
    recent = await cl_repo.create(db_session, connection_type="MCP", status="success")
    await db_session.flush()
    await db_session.execute(
        cl_repo.ConnectionLog.__table__.update()
        .where(cl_repo.ConnectionLog.id == old.id)
        .values(created_at=datetime.now() - timedelta(days=30))
    )
    await db_session.flush()

    deleted = await cl_repo.delete_older_than(db_session, datetime.now() - timedelta(days=1))
    assert deleted == 1
    assert await cl_repo.get(db_session, old.id) is None
    assert await cl_repo.get(db_session, recent.id) is not None
