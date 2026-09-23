"""Service-layer tests for message rating (moved out of the router)."""

import uuid

import pytest

from app.errors import ApiError
from app.repositories import agency as agency_repo
from app.repositories import conversation as conversation_repo
from app.repositories import message as message_repo
from app.schemas.conversation import RatingUpdate
from app.services import message as message_service

pytestmark = pytest.mark.asyncio


async def _agency(db_session, short_name="DOPA"):
    agency = await agency_repo.create(db_session, name=f"name-{short_name}", short_name=short_name)
    await db_session.flush()
    return agency


async def _message(db_session, agency_ids=None):
    conv = await conversation_repo.create(
        db_session, id=str(uuid.uuid4()), title="t", preview="p", agencies=[],
        status="success", message_count=0, response_time="0",
    )
    msg = await message_repo.create(
        db_session, conversation_id=conv.id, role="assistant", content="a", agency_ids=agency_ids or [],
    )
    await db_session.flush()
    return msg


async def test_update_rating_increments_agency_metrics(db_session):
    ag = await _agency(db_session)
    msg = await _message(db_session, agency_ids=[str(ag.id)])

    updated = await message_service.update_rating(db_session, msg.id, RatingUpdate(rating="up"))

    assert updated.rating == "up"
    ag = await agency_repo.by_id(db_session, ag.id)
    assert ag.rating_up == 1


async def test_update_rating_missing_message_raises_404(db_session):
    with pytest.raises(ApiError) as exc:
        await message_service.update_rating(db_session, uuid.uuid4(), RatingUpdate(rating="up"))
    assert exc.value.status == 404
