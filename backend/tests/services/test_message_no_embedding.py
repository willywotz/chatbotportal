import pytest

from app.models.conversation import Message
from app.repositories import conversation as conversation_repo
from app.repositories import message as message_repo

pytestmark = pytest.mark.asyncio


async def test_message_has_no_embedding_field(db_session):
    assert "embedding" not in Message.__table__.columns
    conv = await conversation_repo.create(
        db_session, id="00000000-0000-0000-0000-0000000000f1", title="t", preview="p",
        agencies=[], status="success", message_count=0, response_time="0",
    )
    msg = await message_repo.create(db_session, conversation_id=conv.id, role="user", content="hi")
    await db_session.flush()
    assert msg.id is not None
