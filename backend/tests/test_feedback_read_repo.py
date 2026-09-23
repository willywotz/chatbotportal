from datetime import timedelta

import pytest

from app.models.agency import Agency
from app.models.conversation import Conversation, Message
from app.repositories import feedback_read as repo
from app.utils import now

pytestmark = pytest.mark.asyncio


async def _conversation(session):
    conv = Conversation()
    session.add(conv)
    await session.flush()
    return conv


async def _message(session, conv, **fields):
    msg = Message(conversation_id=conv.id, role=fields.pop("role", "assistant"),
                  content=fields.pop("content", "hi"), **fields)
    session.add(msg)
    await session.flush()
    return msg


async def test_rating_totals(db_session):
    conv = await _conversation(db_session)
    await _message(db_session, conv, rating="up")
    await _message(db_session, conv, rating="up")
    await _message(db_session, conv, rating="down")
    await _message(db_session, conv, rating=None)

    totals = await repo.rating_totals(db_session)

    assert totals["total_rating"] == 3
    assert totals["rating_up"] == 2
    assert totals["rating_down"] == 1
    assert totals["rate"] == pytest.approx(200 / 3)


async def test_rating_totals_empty(db_session):
    totals = await repo.rating_totals(db_session)

    assert totals["total_rating"] == 0
    assert totals["rating_up"] is None
    assert totals["rate"] is None


async def test_rating_daily_trend(db_session):
    conv = await _conversation(db_session)
    ts = now()
    await _message(db_session, conv, rating="up", created_at=ts)
    await _message(db_session, conv, rating="down", created_at=ts)

    since = now() - timedelta(days=14)
    rows = await repo.rating_daily_trend(db_session, since)

    assert len(rows) == 1
    assert rows[0]["up"] == 1
    assert rows[0]["down"] == 1


async def test_agency_rating_counts(db_session):
    ag = Agency(name="Agency A")
    db_session.add(ag)
    await db_session.flush()
    conv = await _conversation(db_session)
    await _message(db_session, conv, rating="up", agency_ids=[str(ag.id)])
    await _message(db_session, conv, rating="down", agency_ids=[str(ag.id)])
    await _message(db_session, conv, rating="up", agency_ids=["other-id"])

    counts = await repo.agency_rating_counts(db_session, ag.id)

    assert counts["rating_up"] == 1
    assert counts["rating_down"] == 1


async def test_list_agencies_short_names(db_session):
    ag = Agency(name="Agency A", short_name="AA")
    db_session.add(ag)
    await db_session.flush()

    rows = await repo.list_agencies_short_names(db_session)

    assert {"id": ag.id, "short_name": "AA"} in rows


async def test_low_rated_assistant_messages(db_session):
    conv = await _conversation(db_session)
    await _message(db_session, conv, role="assistant", rating="down", feedback_text="bad")
    await _message(db_session, conv, role="assistant", rating="up")
    await _message(db_session, conv, role="user", rating="down")

    rows = await repo.low_rated_assistant_messages(db_session, 5)

    assert len(rows) == 1
    assert rows[0].feedback_text == "bad"
