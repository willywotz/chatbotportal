import uuid

import pytest

from app.repositories import conversation as conversation_repo
from app.utils import now

pytestmark = pytest.mark.asyncio


async def test_get_messages_404s_for_soft_deleted_conversation(client, db_session, as_principal):
    owner_id = str(uuid.uuid4())
    conv = await conversation_repo.create(
        db_session, id=str(uuid.uuid4()), title="t", preview="p", agencies=[],
        status="success", message_count=0, response_time="0",
        user_id=owner_id, deleted_at=now(),
    )
    await db_session.flush()

    as_principal(scopes={"conversation:read:own"}, role="user", sub=owner_id)
    resp = await client.get(f"/api/v1/history/{conv.id}/messages")
    assert resp.status_code == 404
