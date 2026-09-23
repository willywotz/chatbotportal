from datetime import timedelta

import pytest

from app.features.agency.repositories import agency as agency_repo
from app.features.chat.repositories import conversation as conversation_repo
from app.features.chat.repositories import message as message_repo
from app.features.analytics.repositories import popular_question as pq_repo
from app.core.utils import now

pytestmark = pytest.mark.asyncio


async def test_create_and_text_key_exists(db_session):
    pq = await pq_repo.create(db_session, text="Q1", text_key="q1")
    assert pq.text == "Q1"
    assert await pq_repo.text_key_exists(db_session, "q1") is True
    assert await pq_repo.text_key_exists(db_session, "nope") is False


async def test_visible_with_agency_excludes_hidden_and_loads_agency(db_session):
    agency = await agency_repo.create(db_session, name="Agency A")
    await pq_repo.create(db_session, text="visible", text_key="v1", agency_id=agency.id)
    await pq_repo.create(db_session, text="hidden", text_key="h1", hidden=True)
    await db_session.flush()

    rows = await pq_repo.visible_with_agency(db_session)
    assert [r.text for r in rows] == ["visible"]
    assert rows[0].agency.name == "Agency A"


async def test_all_with_agency_includes_hidden(db_session):
    await pq_repo.create(db_session, text="visible", text_key="v2")
    await pq_repo.create(db_session, text="hidden", text_key="h2", hidden=True)
    await db_session.flush()
    rows = await pq_repo.all_with_agency(db_session)
    assert {r.text for r in rows} == {"visible", "hidden"}


async def test_update_and_delete(db_session):
    pq = await pq_repo.create(db_session, text="Q1", text_key="q3")
    await pq_repo.update(db_session, pq, {"text": "Q1 edited"})
    assert pq.text == "Q1 edited"
    await pq_repo.delete(db_session, pq)
    await db_session.flush()
    assert await pq_repo.text_key_exists(db_session, "q3") is False


async def test_bulk_create_ignore_conflicts(db_session):
    import uuid
    shared_id = uuid.uuid4()
    rows = [
        {"id": shared_id, "text": "a", "text_key": "bk1"},
        {"id": shared_id, "text": "b", "text_key": "bk2"},
    ]
    await pq_repo.bulk_create(db_session, rows, ignore_conflicts=True)
    all_rows = await pq_repo.all_with_agency(db_session)
    assert len(all_rows) == 1


async def test_by_id_present_and_absent(db_session):
    pq = await pq_repo.create(db_session, text="Q1", text_key="byid1")
    await db_session.flush()
    assert (await pq_repo.by_id(db_session, pq.id)).text == "Q1"
    import uuid
    assert await pq_repo.by_id(db_session, uuid.uuid4()) is None


async def test_text_key_exists_excludes_given_id(db_session):
    pq = await pq_repo.create(db_session, text="Q1", text_key="exkey")
    await db_session.flush()
    assert await pq_repo.text_key_exists(db_session, "exkey") is True
    assert await pq_repo.text_key_exists(db_session, "exkey", exclude_id=pq.id) is False


async def test_delete_stale_auto_keeps_pinned_and_hidden(db_session):
    stale = await pq_repo.create(db_session, text="stale", text_key="stale1", source="auto")
    pinned = await pq_repo.create(db_session, text="pinned", text_key="pinned1", source="auto", pinned=True)
    hidden = await pq_repo.create(db_session, text="hidden", text_key="hidden1", source="auto", hidden=True)
    manual = await pq_repo.create(db_session, text="manual", text_key="manual1", source="manual")
    await db_session.flush()

    await pq_repo.delete_stale_auto(db_session)

    remaining = {r.id for r in await pq_repo.all_with_agency(db_session)}
    assert remaining == {pinned.id, hidden.id, manual.id}
    assert stale.id not in remaining


async def _successful_conversation_with_turn(db_session, *, question="q", agency_ids=None):
    conv = await conversation_repo.create(db_session, status="success")
    user_msg = await message_repo.create(db_session, conversation_id=conv.id, role="user", content=question)
    await message_repo.create(
        db_session, conversation_id=conv.id, role="assistant", parent_id=user_msg.id,
        content="a", agency_ids=agency_ids or [],
    )
    return user_msg


async def test_recent_successful_turn_count_excludes_failed_and_old(db_session):
    cutoff = now() - timedelta(days=7)
    await _successful_conversation_with_turn(db_session)
    failed_conv = await conversation_repo.create(db_session, status="failed")
    await message_repo.create(db_session, conversation_id=failed_conv.id, role="user", content="q2")
    await db_session.flush()

    count = await pq_repo.recent_successful_turn_count(db_session, cutoff)
    assert count == 1


async def test_recent_successful_user_messages_orders_newest_first(db_session):
    cutoff = now() - timedelta(days=7)
    first = await _successful_conversation_with_turn(db_session, question="first")
    second = await _successful_conversation_with_turn(db_session, question="second")
    # Postgres now() is constant within a transaction; force distinct timestamps.
    first.created_at = now() - timedelta(minutes=1)
    second.created_at = now()
    await db_session.flush()

    rows = await pq_repo.recent_successful_user_messages(db_session, cutoff, 10)
    assert [r["content"] for r in rows] == ["second", "first"]


async def test_assistant_replies_for_matches_parent_ids(db_session):
    user_msg = await _successful_conversation_with_turn(db_session, agency_ids=["a1"])
    await db_session.flush()

    replies = await pq_repo.assistant_replies_for(db_session, [user_msg.id])
    assert len(replies) == 1
    assert replies[0]["parent_id"] == user_msg.id
    assert replies[0]["agency_ids"] == ["a1"]
