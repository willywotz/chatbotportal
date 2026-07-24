from httpx import ASGITransport, AsyncClient

from app.main import app


async def _c():
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://t")


async def test_create_conversation_anonymous(db):
    async with await _c() as c:
        r = await c.post("/api/v1/conversations", json={"metadata": {"topic": "demo"}})
        assert r.status_code == 200
        body = r.json()
        assert body["object"] == "conversation" and body["id"].startswith("conv_")
        assert body["metadata"] == {"topic": "demo"}
        assert "X-Portal-Session" in r.headers


async def test_create_persists_items(db):
    from app.models.conversation import Message
    async with await _c() as c:
        r = await c.post("/api/v1/conversations",
                          json={"items": [{"role": "user", "content": "one"},
                                          {"role": "assistant", "content": "two"}]})
        cid = r.json()["id"].removeprefix("conv_")
        assert await Message.filter(conversation_id=cid).count() == 2


async def test_create_rejects_too_many_items(db):
    async with await _c() as c:
        r = await c.post("/api/v1/conversations",
                          json={"items": [{"role": "user", "content": "x"}] * 21})
        assert r.status_code == 400 and r.json()["error"]["param"] == "items"


async def test_create_rejects_bad_metadata(db):
    async with await _c() as c:
        r = await c.post("/api/v1/conversations",
                          json={"metadata": {f"k{i}": "v" for i in range(17)}})
        assert r.status_code == 400 and r.json()["error"]["param"] == "metadata"
