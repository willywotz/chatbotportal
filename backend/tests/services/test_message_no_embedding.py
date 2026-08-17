import pytest

from app.models.conversation import Message


@pytest.mark.asyncio
async def test_message_has_no_embedding_field(db):
    assert "embedding" not in Message._meta.fields_map
    from app.models.conversation import Conversation
    conv = await Conversation.create(status="success")
    msg = await Message.create(conversation=conv, role="user", content="hi")
    assert msg.id is not None
