"""Service-layer tests for message rating (moved out of the router)."""

import uuid

import pytest

from app.errors import ApiError
from app.models.agency import Agency
from app.models.conversation import Conversation, Message
from app.schemas.conversation import RatingUpdate
from app.services import message as message_service


async def _agency(short_name="DOPA"):
    return await Agency.create(name=f"name-{short_name}", short_name=short_name)


async def _message(agency_ids=None):
    conv = await Conversation.create()
    return await Message.create(
        conversation=conv, role="assistant", content="a", agency_ids=agency_ids or [],
    )


async def test_update_rating_increments_agency_metrics(db):
    ag = await _agency()
    msg = await _message(agency_ids=[str(ag.id)])

    updated = await message_service.update_rating(msg.id, RatingUpdate(rating="up"))

    assert updated.rating == "up"
    ag = await Agency.get(id=ag.id)
    assert ag.rating_up == 1


async def test_update_rating_missing_message_raises_404(db):
    with pytest.raises(ApiError) as exc:
        await message_service.update_rating(uuid.uuid4(), RatingUpdate(rating="up"))
    assert exc.value.status == 404
