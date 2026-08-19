"""Outbox transactionality: a chat turn + its domain event share one caller-owned transaction."""
import uuid

import pytest

from app.repositories import event as event_repo
from app.repositories import message as message_repo

pytestmark = pytest.mark.asyncio


async def test_turn_and_event_share_one_transaction(db_session):
    from app.services.chat import turn
    from app.services.events import publish

    conv_id = str(uuid.uuid4())
    await turn.save_turn(
        session=db_session, query="q", conversation_id=conv_id, answer="a",
        references=[], category=None, agency_ids=[], response_time=1,
        user=None, succeeded=True,
    )
    await publish(db_session, "chat.turn_saved", {"conversation_id": conv_id})
    await db_session.flush()
    assert len(await message_repo.list_for_conversation(db_session, conv_id)) == 2
    assert len(await event_repo.pending(db_session, 10)) == 1  # same transaction


async def test_dispatch_pending_marks_events_dispatched(db_session, monkeypatch):
    """dispatch_pending opens its own session; bind it to the test's connection
    (same DB transaction) so the row it wrote is visible without a real commit."""
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

    from app.services import events

    await events.publish(db_session, "thing.happened", {"a": 1})
    await db_session.flush()

    conn = await db_session.connection()
    factory = async_sessionmaker(
        bind=conn, class_=AsyncSession, expire_on_commit=False,
        join_transaction_mode="create_savepoint",
    )
    monkeypatch.setattr(events, "AsyncSessionLocal", factory)

    handled = await events.dispatch_pending()

    assert handled == 1
    assert len(await event_repo.pending(db_session, 10)) == 0
