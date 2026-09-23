"""Tests for app.features.analytics.services.feedback."""
import uuid

import pytest

from app.core.errors import ApiError
from app.features.agency.models.agency import Agency
from app.features.chat.models.conversation import Conversation, Message
from app.features.analytics.services.feedback import agency_low_rated, agency_low_rated_or_404, get_feedback_stats

pytestmark = pytest.mark.asyncio


async def test_agency_low_rated_returns_only_down_rated(db_session):
    ag = Agency(name="A", status="active")
    db_session.add(ag)
    await db_session.flush()
    conv = Conversation(title="t", user_id=uuid.uuid4())
    db_session.add(conv)
    await db_session.flush()
    db_session.add_all([
        Message(conversation_id=conv.id, role="assistant", content="bad",
                rating="down", agency_ids=[str(ag.id)]),
        Message(conversation_id=conv.id, role="assistant", content="good",
                rating="up", agency_ids=[str(ag.id)]),
    ])
    await db_session.flush()

    rows = await agency_low_rated(db_session, str(ag.id))

    assert len(rows) == 1 and rows[0]["content"] == "bad"


async def test_agency_low_rated_or_404_raises_for_missing_agency(db_session):
    with pytest.raises(ApiError) as exc:
        await agency_low_rated_or_404(db_session, "00000000-0000-0000-0000-000000000000")
    assert exc.value.status == 404


async def test_agency_low_rated_or_404_returns_rows_for_existing_agency(db_session):
    ag = Agency(name="B", status="active")
    db_session.add(ag)
    await db_session.flush()
    conv = Conversation(title="t", user_id=uuid.uuid4())
    db_session.add(conv)
    await db_session.flush()
    db_session.add(Message(conversation_id=conv.id, role="assistant", content="bad",
                           rating="down", agency_ids=[str(ag.id)]))
    await db_session.flush()

    rows = await agency_low_rated_or_404(db_session, str(ag.id))

    assert len(rows) == 1


async def test_get_feedback_stats_shape_and_daily_trend_rate_default(db_session):
    """rating_daily_trend (repo) drops the `rate` key — the service must re-inject rate=0."""
    ag = Agency(name="Agency A", short_name="AA", status="active")
    db_session.add(ag)
    await db_session.flush()
    conv = Conversation(title="t", user_id=uuid.uuid4())
    db_session.add(conv)
    await db_session.flush()
    db_session.add_all([
        Message(conversation_id=conv.id, role="assistant", content="good",
                rating="up", agency_ids=[str(ag.id)]),
        Message(conversation_id=conv.id, role="assistant", content="bad",
                rating="down", feedback_text="no", agency_ids=[str(ag.id)]),
    ])
    await db_session.flush()

    stats = await get_feedback_stats(db_session)

    assert stats.total_ratings == 2
    assert stats.up_count == 1
    assert stats.down_count == 1
    assert all(item.rate == 0 for item in stats.daily_trend)
    assert {"agency": "AA", "up": 1, "down": 1, "rate": 0} in [b.model_dump() for b in stats.agency_breakdown]
    assert stats.low_rated_questions[0].feedback_text == "no"
