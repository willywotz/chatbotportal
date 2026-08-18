import pytest

from app.models.conversation import Conversation, Message
from app.repositories import message as repo
from app.utils import now


async def _conv():
    return await Conversation.create(title="t", agencies=[], status="active")


@pytest.mark.asyncio
async def test_by_id_present_and_absent(db):
    c = await _conv()
    m = await repo.create(conversation_id=c.id, role="user", content="hi")
    assert (await repo.by_id(m.id)).id == m.id
    assert await repo.by_id("00000000-0000-0000-0000-000000000000") is None


@pytest.mark.asyncio
async def test_list_for_conversation_orders_and_excludes_deleted(db):
    c = await _conv()
    await repo.create(conversation_id=c.id, role="user", content="first")
    await repo.create(conversation_id=c.id, role="assistant", content="second")
    await repo.create(conversation_id=c.id, role="user", content="gone", deleted_at=now())
    rows = await repo.list_for_conversation(c.id)
    assert [m.content for m in rows] == ["first", "second"]          # deleted excluded, created_at order
    rows_all = await repo.list_for_conversation(c.id, include_deleted=True)
    assert len(rows_all) == 3


@pytest.mark.asyncio
async def test_first_user_message(db):
    c = await _conv()
    await repo.create(conversation_id=c.id, role="assistant", content="a")
    await repo.create(conversation_id=c.id, role="user", content="u1")
    await repo.create(conversation_id=c.id, role="user", content="u2")
    first = await repo.first_user_message(c.id)
    assert first.content == "u1"                                     # earliest user message
    assert await repo.first_user_message("00000000-0000-0000-0000-000000000000") is None


@pytest.mark.asyncio
async def test_set_category_by_id(db):
    c = await _conv()
    m = await repo.create(conversation_id=c.id, role="user", content="q")
    await repo.set_category(m.id, "travel")
    assert (await repo.by_id(m.id)).category == "travel"


@pytest.mark.asyncio
async def test_bulk_create_ignore_conflicts(db):
    c = await _conv()
    rows = [
        Message(conversation_id=c.id, role="user", content="b1"),
        Message(conversation_id=c.id, role="assistant", content="b2"),
    ]
    await repo.bulk_create(rows, ignore_conflicts=True)
    assert len(await repo.list_for_conversation(c.id)) == 2


@pytest.mark.asyncio
async def test_save_partial(db):
    c = await _conv()
    m = await repo.create(conversation_id=c.id, role="assistant", content="a")
    m.rating = "up"
    await repo.save(m, update_fields=["rating"])
    assert (await repo.by_id(m.id)).rating == "up"
