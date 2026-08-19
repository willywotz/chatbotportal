"""HTTP-level scope enforcement for PATCH /api/v1/messages/{id}/rating."""
import pytest
from httpx import ASGITransport, AsyncClient

from app.main import app
from app.models.conversation import Conversation, Message


async def _client():
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://t")


async def _message():
    conv = await Conversation.create()
    return await Message.create(conversation=conv, role="assistant", content="answer")


@pytest.mark.usefixtures("db")
async def test_update_rating_allowed_with_message_rate_scope(as_principal):
    as_principal(role="user", scopes=["message:rate"])
    msg = await _message()
    async with await _client() as c:
        r = await c.patch(f"/api/v1/messages/{msg.id}/rating", json={"rating": "up"})
    assert r.status_code == 200


@pytest.mark.usefixtures("db")
async def test_update_rating_forbidden_without_message_rate_scope(as_principal):
    as_principal(role="user", scopes=["conversation:read:own"])
    msg = await _message()
    async with await _client() as c:
        r = await c.patch(f"/api/v1/messages/{msg.id}/rating", json={"rating": "up"})
    assert r.status_code == 403
