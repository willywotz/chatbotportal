from app.models.conversation import Conversation, Message
from app.models.user import User


async def test_new_fields_exist_with_defaults(db):
    u = await User.create(email="a@b.c", hashed_password="!")
    assert u.is_ephemeral is False
    c = await Conversation.create(title="t", user_id=u.id)
    assert c.metadata == {}
    assert c.deleted_at is None
    m = await Message.create(conversation_id=c.id, role="user", content="hi")
    assert m.deleted_at is None
