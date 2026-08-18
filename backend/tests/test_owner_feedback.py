import uuid

from app.models import Agency
from app.models.conversation import Conversation, Message
from app.routers.feedback import agency_low_rated


async def test_returns_only_down_rated_for_agency(db):
    ag = await Agency.create(name="A", status="active")
    conv = await Conversation.create(title="t", user_id=uuid.uuid4())
    await Message.create(conversation_id=conv.id, role="assistant", content="bad",
                         rating="down", agency_ids=[str(ag.id)])
    await Message.create(conversation_id=conv.id, role="assistant", content="good",
                         rating="up", agency_ids=[str(ag.id)])

    rows = await agency_low_rated(str(ag.id))

    assert len(rows) == 1 and rows[0]["content"] == "bad"
