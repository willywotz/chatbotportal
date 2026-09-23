import uuid

from app.repositories import agency as agency_repo
from app.repositories import conversation as conversation_repo
from app.repositories import message as message_repo
from app.routers.feedback import agency_low_rated


async def test_returns_only_down_rated_for_agency(db_session):
    ag = await agency_repo.create(db_session, name="A", status="active")
    conv = await conversation_repo.create(db_session, title="t", user_id=uuid.uuid4())
    await message_repo.create(db_session, conversation_id=conv.id, role="assistant", content="bad",
                              rating="down", agency_ids=[str(ag.id)])
    await message_repo.create(db_session, conversation_id=conv.id, role="assistant", content="good",
                              rating="up", agency_ids=[str(ag.id)])

    rows = await agency_low_rated(db_session, str(ag.id))

    assert len(rows) == 1 and rows[0]["content"] == "bad"
