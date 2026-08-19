import uuid

from app.models.conversation import Conversation, Message


async def test_new_fields_exist_with_defaults(db):
    c = await Conversation.create(title="t", user_id=uuid.uuid4())
    assert c.metadata == {}
    assert c.deleted_at is None
    m = await Message.create(conversation_id=c.id, role="user", content="hi")
    assert m.deleted_at is None
