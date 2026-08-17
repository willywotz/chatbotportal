"""Tests for app.services.feedback."""
import pytest
from fastapi import HTTPException

from app.models.agency import Agency
from app.models.conversation import Conversation, Message
from app.models.user import User
from app.services.feedback import agency_low_rated, agency_low_rated_or_404


async def test_agency_low_rated_returns_only_down_rated(db):
    ag = await Agency.create(name="A", status="active")
    user = await User.create(email="u@x.com", hashed_password="h")
    conv = await Conversation.create(title="t", user_id=user.id)
    await Message.create(conversation_id=conv.id, role="assistant", content="bad",
                         rating="down", agency_ids=[str(ag.id)])
    await Message.create(conversation_id=conv.id, role="assistant", content="good",
                         rating="up", agency_ids=[str(ag.id)])

    rows = await agency_low_rated(str(ag.id))

    assert len(rows) == 1 and rows[0]["content"] == "bad"


async def test_agency_low_rated_or_404_raises_for_missing_agency(db):
    with pytest.raises(HTTPException) as exc:
        await agency_low_rated_or_404("00000000-0000-0000-0000-000000000000")
    assert exc.value.status_code == 404


async def test_agency_low_rated_or_404_returns_rows_for_existing_agency(db):
    ag = await Agency.create(name="B", status="active")
    user = await User.create(email="u2@x.com", hashed_password="h")
    conv = await Conversation.create(title="t", user_id=user.id)
    await Message.create(conversation_id=conv.id, role="assistant", content="bad",
                         rating="down", agency_ids=[str(ag.id)])

    rows = await agency_low_rated_or_404(str(ag.id))

    assert len(rows) == 1
