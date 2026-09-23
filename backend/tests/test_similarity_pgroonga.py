"""PGroonga similar-search repository — replaces the old pg_trgm search."""

from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import update

from app.features.chat.models.conversation import Message
from app.core.repositories import connection_log as connection_log_repo
from app.features.chat.repositories import conversation as conversation_repo
from app.features.chat.repositories import message as message_repo
from app.features.chat.repositories import similarity as similarity_repo

pytestmark = pytest.mark.asyncio


async def test_pgroonga_similar_search_finds_prior_question(db_session):
    conv = await conversation_repo.create(db_session, status="success", title="t")
    await message_repo.create(
        db_session, conversation_id=conv.id, role="user", content="ขอข้อมูลภาษี"
    )
    await db_session.flush()
    cutoff = datetime.now(timezone.utc) - timedelta(hours=1)

    match = await similarity_repo.find_similar(db_session, "ข้อมูลภาษี", cutoff)

    assert match is not None
    assert "ภาษี" in match.content


async def test_pgroonga_similar_search_ignores_messages_outside_window(db_session):
    conv = await conversation_repo.create(db_session, status="success", title="t")
    user_msg = await message_repo.create(
        db_session, conversation_id=conv.id, role="user", content="ขอข้อมูลภาษี"
    )
    await db_session.flush()
    old_created_at = datetime.now(timezone.utc) - timedelta(hours=2)
    await db_session.execute(
        update(Message).where(Message.id == user_msg.id).values(created_at=old_created_at)
    )
    await db_session.flush()
    cutoff = datetime.now(timezone.utc) - timedelta(hours=1)

    match = await similarity_repo.find_similar(db_session, "ข้อมูลภาษี", cutoff)

    assert match is None


async def test_answer_for_returns_assistant_and_connection_log(db_session):
    conv = await conversation_repo.create(db_session, status="success", title="t")
    user_msg = await message_repo.create(
        db_session, conversation_id=conv.id, role="user", content="ขอข้อมูลภาษี"
    )
    asst_msg = await message_repo.create(
        db_session,
        conversation_id=conv.id,
        parent_id=user_msg.id,
        role="assistant",
        content="นี่คือข้อมูลภาษี",
    )
    conn_log = await connection_log_repo.create(
        db_session,
        connection_type="API",
        status="success",
        action="query",
        assistant_message_id=asst_msg.id,
    )
    await db_session.flush()

    answer = await similarity_repo.answer_for(db_session, user_msg)

    assert answer is not None
    got_asst, got_cl = answer
    assert got_asst.id == asst_msg.id
    assert got_cl.id == conn_log.id


async def test_answer_for_returns_none_for_non_success_conversation(db_session):
    conv = await conversation_repo.create(db_session, status="failed", title="t")
    user_msg = await message_repo.create(
        db_session, conversation_id=conv.id, role="user", content="ขอข้อมูลภาษี"
    )
    asst_msg = await message_repo.create(
        db_session,
        conversation_id=conv.id,
        parent_id=user_msg.id,
        role="assistant",
        content="นี่คือข้อมูลภาษี",
    )
    await connection_log_repo.create(
        db_session,
        connection_type="API",
        status="success",
        action="query",
        assistant_message_id=asst_msg.id,
    )
    await db_session.flush()

    answer = await similarity_repo.answer_for(db_session, user_msg)

    assert answer is None
