"""Scenario tests for the message-rating endpoint (the feedback workflow).

`PATCH /messages/{id}/rating` persists a thumbs up/down (plus optional free-text
feedback) and rolls the count into each involved agency's rating_up/rating_down
metrics. These run against the in-memory SQLite `db` fixture — the endpoint uses
only portable ORM operations.
"""

import uuid

import pytest
from fastapi import HTTPException

from app.models.agency import Agency
from app.models.conversation import Conversation, Message
from app.routers import messages as messages_router
from app.schemas.conversation import RatingUpdate


async def _agency(short_name="DOPA"):
    return await Agency.create(name=f"name-{short_name}", short_name=short_name)


async def _message(agency_ids=None):
    conv = await Conversation.create()
    return await Message.create(
        conversation=conv,
        role="assistant",
        content="คำตอบทดสอบจากระบบ",
        agency_ids=agency_ids or [],
    )


@pytest.mark.asyncio
async def test_up_rating_persists_and_increments_agency(db):
    ag = await _agency()
    msg = await _message(agency_ids=[str(ag.id)])

    res = await messages_router.update_rating(
        message_id=msg.id, body=RatingUpdate(rating="up")
    )

    assert res == {"success": True, "messageId": str(msg.id)}
    saved = await Message.get(id=msg.id)
    assert saved.rating == "up"
    ag = await Agency.get(id=ag.id)
    assert ag.rating_up == 1
    assert ag.rating_down == 0


@pytest.mark.asyncio
async def test_down_rating_stores_feedback_text_and_increments(db):
    ag = await _agency()
    msg = await _message(agency_ids=[str(ag.id)])

    await messages_router.update_rating(
        message_id=msg.id,
        body=RatingUpdate(rating="down", feedback_text="ไม่ตรงคำถาม"),
    )

    saved = await Message.get(id=msg.id)
    assert saved.rating == "down"
    assert saved.feedback_text == "ไม่ตรงคำถาม"
    ag = await Agency.get(id=ag.id)
    assert ag.rating_down == 1
    assert ag.rating_up == 0


@pytest.mark.asyncio
async def test_rating_increments_every_listed_agency(db):
    a1 = await _agency("A1")
    a2 = await _agency("A2")
    msg = await _message(agency_ids=[str(a1.id), str(a2.id)])

    await messages_router.update_rating(
        message_id=msg.id, body=RatingUpdate(rating="up")
    )

    a1 = await Agency.get(id=a1.id)
    a2 = await Agency.get(id=a2.id)
    assert a1.rating_up == 1
    assert a2.rating_up == 1


@pytest.mark.asyncio
async def test_rating_handles_comma_joined_agency_ids(db):
    """A legacy comma-joined agency_ids element must not crash the query and
    must still credit both agencies (on Postgres the raw value is an invalid
    UUID; here we assert the resolved behavior)."""
    a1 = await _agency("A1")
    a2 = await _agency("A2")
    msg = await _message(agency_ids=[f"{a1.id},{a2.id}"])

    await messages_router.update_rating(
        message_id=msg.id, body=RatingUpdate(rating="up")
    )

    a1 = await Agency.get(id=a1.id)
    a2 = await Agency.get(id=a2.id)
    assert a1.rating_up == 1
    assert a2.rating_up == 1


@pytest.mark.asyncio
async def test_rating_without_feedback_leaves_feedback_text_none(db):
    msg = await _message()

    await messages_router.update_rating(
        message_id=msg.id, body=RatingUpdate(rating="up")
    )

    saved = await Message.get(id=msg.id)
    assert saved.rating == "up"
    assert saved.feedback_text is None


@pytest.mark.asyncio
async def test_rating_skips_unknown_agency_id_without_failing(db):
    msg = await _message(agency_ids=[str(uuid.uuid4())])

    res = await messages_router.update_rating(
        message_id=msg.id, body=RatingUpdate(rating="down")
    )

    assert res["success"] is True
    saved = await Message.get(id=msg.id)
    assert saved.rating == "down"


@pytest.mark.asyncio
async def test_rating_missing_message_returns_404(db):
    with pytest.raises(HTTPException) as exc:
        await messages_router.update_rating(
            message_id=uuid.uuid4(), body=RatingUpdate(rating="up")
        )

    assert exc.value.status_code == 404
