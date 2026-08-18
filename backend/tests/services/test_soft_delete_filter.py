import uuid

import pytest

from app.auth.keycloak import Principal
from app.errors import ApiError
from app.models.conversation import Conversation
from app.routers.conversations import get_conversation_messages
from app.utils import now


@pytest.mark.asyncio
async def test_get_messages_404s_for_soft_deleted_conversation(db):
    owner_id = str(uuid.uuid4())
    conv = await Conversation.create(
        title="t", status="active", user_id=owner_id, deleted_at=now()
    )
    owner = Principal(id=owner_id, email=None, display_name=None, role="user",
                       scopes=frozenset({"conversation:read:own"}))
    with pytest.raises(ApiError) as exc:
        await get_conversation_messages(conv.id, owner)
    assert exc.value.status == 404
