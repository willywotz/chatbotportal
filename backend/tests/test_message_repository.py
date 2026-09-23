import uuid
from datetime import datetime

import pytest

from app.repositories import conversation as conversation_repo
from app.repositories import message as repo

pytestmark = pytest.mark.asyncio


async def _conv(session):
    return await conversation_repo.create(session, title="t", agencies=[], status="active")


async def test_by_id_present_and_absent(db_session):
    c = await _conv(db_session)
    m = await repo.create(db_session, conversation_id=c.id, role="user", content="hi")
    await db_session.flush()
    assert (await repo.by_id(db_session, m.id)).id == m.id
    assert await repo.by_id(db_session, uuid.uuid4()) is None


async def test_list_for_conversation_orders_and_excludes_deleted(db_session):
    c = await _conv(db_session)
    await repo.create(db_session, conversation_id=c.id, role="user", content="first")
    await repo.create(db_session, conversation_id=c.id, role="assistant", content="second")
    await repo.create(
        db_session, conversation_id=c.id, role="user", content="gone",
        deleted_at=datetime.now())
    await db_session.flush()
    rows = await repo.list_for_conversation(db_session, c.id)
    assert [m.content for m in rows] == ["first", "second"]           # deleted excluded, created_at order
    rows_all = await repo.list_for_conversation(db_session, c.id, include_deleted=True)
    assert len(rows_all) == 3


async def test_first_user_message(db_session):
    c = await _conv(db_session)
    await repo.create(db_session, conversation_id=c.id, role="assistant", content="a")
    await repo.create(db_session, conversation_id=c.id, role="user", content="u1")
    await repo.create(db_session, conversation_id=c.id, role="user", content="u2")
    await db_session.flush()
    first = await repo.first_user_message(db_session, c.id)
    assert first.content == "u1"                                     # earliest user message
    assert await repo.first_user_message(db_session, uuid.uuid4()) is None


async def test_set_category_by_id(db_session):
    c = await _conv(db_session)
    m = await repo.create(db_session, conversation_id=c.id, role="user", content="q")
    await db_session.flush()
    await repo.set_category(db_session, m.id, "travel")
    await db_session.refresh(m)
    assert m.category == "travel"


async def test_bulk_create_ignore_conflicts(db_session):
    c = await _conv(db_session)
    await db_session.flush()
    shared_id = uuid.uuid4()
    rows = [
        {"id": shared_id, "conversation_id": c.id, "role": "user", "content": "b1"},
        {"id": shared_id, "conversation_id": c.id, "role": "assistant", "content": "b2"},
    ]
    await repo.bulk_create(db_session, rows, ignore_conflicts=True)
    assert len(await repo.list_for_conversation(db_session, c.id)) == 1


async def test_save_partial(db_session):
    c = await _conv(db_session)
    m = await repo.create(db_session, conversation_id=c.id, role="assistant", content="a")
    await db_session.flush()
    m.rating = "up"
    await repo.save(db_session, m, update_fields=["rating"])
    assert (await repo.by_id(db_session, m.id)).rating == "up"
