"""Scenario tests for the message-rating endpoint (the feedback workflow).

`PATCH /messages/{id}/rating` persists a thumbs up/down (plus optional free-text
feedback) and rolls the count into each involved agency's rating_up/rating_down
metrics.
"""

import uuid

import pytest

from app.errors import ApiError
from app.repositories import agency as agency_repo
from app.repositories import conversation as conversation_repo
from app.repositories import message as message_repo
from app.routers import messages as messages_router
from app.schemas.conversation import RatingUpdate


async def _agency(session, short_name="DOPA"):
    return await agency_repo.create(session, name=f"name-{short_name}", short_name=short_name)


async def _message(session, agency_ids=None):
    conv = await conversation_repo.create(session)
    return await message_repo.create(
        session,
        conversation_id=conv.id,
        role="assistant",
        content="คำตอบทดสอบจากระบบ",
        agency_ids=agency_ids or [],
    )


async def test_up_rating_persists_and_increments_agency(db_session):
    ag = await _agency(db_session)
    msg = await _message(db_session, agency_ids=[str(ag.id)])

    res = await messages_router.update_rating(
        message_id=msg.id, body=RatingUpdate(rating="up"), session=db_session,
    )

    assert res == {"success": True, "messageId": str(msg.id)}
    saved = await message_repo.by_id(db_session, msg.id)
    assert saved.rating == "up"
    ag = await agency_repo.by_id(db_session, ag.id)
    assert ag.rating_up == 1
    assert ag.rating_down == 0


async def test_down_rating_stores_feedback_text_and_increments(db_session):
    ag = await _agency(db_session)
    msg = await _message(db_session, agency_ids=[str(ag.id)])

    await messages_router.update_rating(
        message_id=msg.id,
        body=RatingUpdate(rating="down", feedback_text="ไม่ตรงคำถาม"),
        session=db_session,
    )

    saved = await message_repo.by_id(db_session, msg.id)
    assert saved.rating == "down"
    assert saved.feedback_text == "ไม่ตรงคำถาม"
    ag = await agency_repo.by_id(db_session, ag.id)
    assert ag.rating_down == 1
    assert ag.rating_up == 0


async def test_rating_increments_every_listed_agency(db_session):
    a1 = await _agency(db_session, "A1")
    a2 = await _agency(db_session, "A2")
    msg = await _message(db_session, agency_ids=[str(a1.id), str(a2.id)])

    await messages_router.update_rating(
        message_id=msg.id, body=RatingUpdate(rating="up"), session=db_session,
    )

    a1 = await agency_repo.by_id(db_session, a1.id)
    a2 = await agency_repo.by_id(db_session, a2.id)
    assert a1.rating_up == 1
    assert a2.rating_up == 1


async def test_rating_handles_comma_joined_agency_ids(db_session):
    """A legacy comma-joined agency_ids element must not crash the query and
    must still credit both agencies (on Postgres the raw value is an invalid
    UUID; here we assert the resolved behavior)."""
    a1 = await _agency(db_session, "A1")
    a2 = await _agency(db_session, "A2")
    msg = await _message(db_session, agency_ids=[f"{a1.id},{a2.id}"])

    await messages_router.update_rating(
        message_id=msg.id, body=RatingUpdate(rating="up"), session=db_session,
    )

    a1 = await agency_repo.by_id(db_session, a1.id)
    a2 = await agency_repo.by_id(db_session, a2.id)
    assert a1.rating_up == 1
    assert a2.rating_up == 1


async def test_rating_without_feedback_leaves_feedback_text_none(db_session):
    msg = await _message(db_session)

    await messages_router.update_rating(
        message_id=msg.id, body=RatingUpdate(rating="up"), session=db_session,
    )

    saved = await message_repo.by_id(db_session, msg.id)
    assert saved.rating == "up"
    assert saved.feedback_text is None


async def test_rating_skips_unknown_agency_id_without_failing(db_session):
    msg = await _message(db_session, agency_ids=[str(uuid.uuid4())])

    res = await messages_router.update_rating(
        message_id=msg.id, body=RatingUpdate(rating="down"), session=db_session,
    )

    assert res["success"] is True
    saved = await message_repo.by_id(db_session, msg.id)
    assert saved.rating == "down"


async def test_rating_missing_message_returns_404(db_session):
    with pytest.raises(ApiError) as exc:
        await messages_router.update_rating(
            message_id=uuid.uuid4(), body=RatingUpdate(rating="up"), session=db_session,
        )

    assert exc.value.status == 404
