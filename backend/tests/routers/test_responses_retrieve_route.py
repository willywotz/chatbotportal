import pytest
from httpx import ASGITransport, AsyncClient
from app.auth.security import generate_api_key, hash_api_key
from app.main import app
from app.models.conversation import Conversation, Message
from app.models.user import User, UserAPIKey


async def _owned():
    u = await User.create(email="r@x.y", hashed_password="!")
    c = await Conversation.create(title="t", user_id=u.id)
    await Message.create(conversation_id=c.id, role="user", content="q", user_id=u.id)
    a = await Message.create(conversation_id=c.id, role="assistant", content="ans", user_id=u.id)
    return u, a


async def _api_key_headers(user: User) -> dict:
    raw = generate_api_key()
    await UserAPIKey.create(
        user_id=user.id, name="n", key_hash=hash_api_key(raw), key_prefix=raw[:12]
    )
    return {"Authorization": f"Bearer {raw}"}


async def test_retrieve_delete_input_items(db):
    u, a = await _owned()
    h = await _api_key_headers(u)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
        got = await c.get(f"/api/v1/responses/resp_{a.id}", headers=h)
        assert got.status_code == 200 and got.json()["output_text"] == "ans"

        items = await c.get(f"/api/v1/responses/resp_{a.id}/input_items", headers=h)
        assert items.json()["data"][0]["content"][0]["text"] == "q"

        dele = await c.delete(f"/api/v1/responses/resp_{a.id}", headers=h)
        assert dele.json() == {"id": f"resp_{a.id}", "object": "response", "deleted": True}

        gone = await c.get(f"/api/v1/responses/resp_{a.id}", headers=h)
        assert gone.status_code == 404 and gone.json()["error"]["code"] == "response_not_found"


async def test_retrieve_foreign_is_404(db):
    u, a = await _owned()
    foreign = await User.create(email="foreign@x.y", hashed_password="!")
    other = await _api_key_headers(foreign)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
        r = await c.get(f"/api/v1/responses/resp_{a.id}", headers=other)
        # authenticated but not the owner → 404 (never 403)
        assert r.status_code == 404
