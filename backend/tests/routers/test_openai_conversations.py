from httpx import ASGITransport, AsyncClient

from app.auth.security import generate_api_key, hash_api_key
from app.main import app
from app.models.user import User, UserAPIKey


async def _c():
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://t")


async def _auth_headers(email: str) -> dict:
    user = await User.create(email=email, hashed_password="h", is_active=True)
    raw = generate_api_key()
    await UserAPIKey.create(
        user_id=user.id, name="n", key_hash=hash_api_key(raw), key_prefix=raw[:12]
    )
    return {"Authorization": f"Bearer {raw}"}


async def test_create_conversation_anonymous_is_401(db):
    async with await _c() as c:
        r = await c.post("/api/v1/conversations", json={"metadata": {"topic": "demo"}})
        assert r.status_code == 401


async def test_create_conversation_authenticated(db):
    h = await _auth_headers("owner@x.com")
    async with await _c() as c:
        r = await c.post(
            "/api/v1/conversations", json={"metadata": {"topic": "demo"}}, headers=h,
        )
        assert r.status_code == 200
        body = r.json()
        assert body["object"] == "conversation" and body["id"].startswith("conv_")
        assert body["metadata"] == {"topic": "demo"}
        assert "X-Portal-Session" not in r.headers


async def test_create_persists_items(db):
    from app.models.conversation import Message

    h = await _auth_headers("items@x.com")
    async with await _c() as c:
        r = await c.post(
            "/api/v1/conversations",
            json={"items": [{"role": "user", "content": "one"},
                             {"role": "assistant", "content": "two"}]},
            headers=h,
        )
        cid = r.json()["id"].removeprefix("conv_")
        assert await Message.filter(conversation_id=cid).count() == 2


async def test_create_rejects_too_many_items(db):
    h = await _auth_headers("toomany@x.com")
    async with await _c() as c:
        r = await c.post(
            "/api/v1/conversations",
            json={"items": [{"role": "user", "content": "x"}] * 21}, headers=h,
        )
        assert r.status_code == 400 and r.json()["error"]["param"] == "items"


async def test_create_rejects_bad_metadata(db):
    h = await _auth_headers("badmeta@x.com")
    async with await _c() as c:
        r = await c.post(
            "/api/v1/conversations",
            json={"metadata": {f"k{i}": "v" for i in range(17)}}, headers=h,
        )
        assert r.status_code == 400 and r.json()["error"]["param"] == "metadata"


async def test_get_update_delete_roundtrip(db):
    h = await _auth_headers("roundtrip@x.com")
    async with await _c() as c:
        created = await c.post("/api/v1/conversations", json={"metadata": {"a": "1"}}, headers=h)
        cid = created.json()["id"]

        got = await c.get(f"/api/v1/conversations/{cid}", headers=h)
        assert got.status_code == 200 and got.json()["metadata"] == {"a": "1"}

        upd = await c.post(
            f"/api/v1/conversations/{cid}", json={"metadata": {"b": "2"}}, headers=h,
        )
        assert upd.json()["metadata"] == {"b": "2"}   # replace, not merge

        dele = await c.delete(f"/api/v1/conversations/{cid}", headers=h)
        assert dele.json() == {"id": cid, "object": "conversation.deleted", "deleted": True}

        gone = await c.get(f"/api/v1/conversations/{cid}", headers=h)
        assert gone.status_code == 404 and gone.json()["error"]["code"] == "conversation_not_found"


async def test_foreign_conversation_is_404_not_403(db):
    owner_h = await _auth_headers("owner2@x.com")
    other_h = await _auth_headers("other@x.com")
    async with await _c() as c:
        cid = (await c.post("/api/v1/conversations", json={}, headers=owner_h)).json()["id"]
        # a different authenticated caller must not read someone else's conversation
        r = await c.get(f"/api/v1/conversations/{cid}", headers=other_h)
        assert r.status_code == 404 and r.json()["error"]["code"] == "conversation_not_found"


async def test_malformed_conversation_id_is_404(db):
    h = await _auth_headers("malformed@x.com")
    async with await _c() as c:
        r = await c.get("/api/v1/conversations/conv_not-a-uuid", headers=h)
        assert r.status_code == 404
