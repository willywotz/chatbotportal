from httpx import ASGITransport, AsyncClient

from app.auth.security import create_access_token
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


async def test_get_update_delete_roundtrip(db):
    async with await _c() as c:
        created = await c.post("/api/v1/conversations", json={"metadata": {"a": "1"}})
        cid = created.json()["id"]
        token = created.headers["X-Portal-Session"]
        h = {"Authorization": f"Bearer {token}"}

        got = await c.get(f"/api/v1/conversations/{cid}", headers=h)
        assert got.status_code == 200 and got.json()["metadata"] == {"a": "1"}

        upd = await c.post(f"/api/v1/conversations/{cid}", json={"metadata": {"b": "2"}}, headers=h)
        assert upd.json()["metadata"] == {"b": "2"}   # replace, not merge

        dele = await c.delete(f"/api/v1/conversations/{cid}", headers=h)
        assert dele.json() == {"id": cid, "object": "conversation.deleted", "deleted": True}

        gone = await c.get(f"/api/v1/conversations/{cid}", headers=h)
        assert gone.status_code == 404 and gone.json()["error"]["code"] == "conversation_not_found"


async def test_foreign_conversation_is_404_not_403(db):
    async with await _c() as c:
        cid = (await c.post("/api/v1/conversations", json={})).json()["id"]
        # a different anonymous caller (no session token) must not read it
        r = await c.get(f"/api/v1/conversations/{cid}")
        assert r.status_code == 404 and r.json()["error"]["code"] == "conversation_not_found"


async def test_malformed_conversation_id_is_404(db):
    async with await _c() as c:
        r = await c.get("/api/v1/conversations/conv_not-a-uuid")
        assert r.status_code == 404
