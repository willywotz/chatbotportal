import uuid

from app.repositories import conversation as conversation_repo
from app.repositories import message as message_repo


async def test_new_fields_exist_with_defaults(db_session):
    c = await conversation_repo.create(db_session, title="t", user_id=uuid.uuid4())
    assert c.meta == {}
    assert c.deleted_at is None
    m = await message_repo.create(db_session, conversation_id=c.id, role="user", content="hi")
    assert m.deleted_at is None
