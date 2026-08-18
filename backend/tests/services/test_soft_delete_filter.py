import pytest

from app.errors import ApiError
from app.models.conversation import Conversation
from app.models.user import User
from app.routers.conversations import get_conversation_messages
from app.utils import now


@pytest.mark.asyncio
async def test_get_messages_404s_for_soft_deleted_conversation(db):
    owner = await User.create(email="owner-soft-del@x.com", hashed_password="h", role="user")
    conv = await Conversation.create(
        title="t", status="active", user_id=owner.id, deleted_at=now()
    )
    with pytest.raises(ApiError) as exc:
        await get_conversation_messages(conv.id, owner)
    assert exc.value.status == 404
