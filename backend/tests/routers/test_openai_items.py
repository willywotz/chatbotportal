from httpx import ASGITransport, AsyncClient

from app.auth.security import generate_api_key, hash_api_key
from app.main import app
from app.models.conversation import Message
from app.models.user import User, UserAPIKey


async def _auth_headers(email: str) -> dict:
    user = await User.create(email=email, hashed_password="h", is_active=True)
    raw = generate_api_key()
    await UserAPIKey.create(
        user_id=user.id, name="n", key_hash=hash_api_key(raw), key_prefix=raw[:12]
    )
    return {"Authorization": f"Bearer {raw}"}


async def _owned_conv(c: AsyncClient, email: str) -> tuple[str, dict]:
    h = await _auth_headers(email)
    created = await c.post("/api/v1/conversations", json={}, headers=h)
    return created.json()["id"], h


async def test_items_crud(db):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
        cid, h = await _owned_conv(c, "crud@x.com")
        made = await c.post(f"/api/v1/conversations/{cid}/items",
                             json={"items": [{"role": "user", "content": "one"},
                                             {"role": "assistant", "content": "two"}]}, headers=h)
        assert made.status_code == 200
        data = made.json()["data"]
        assert data[0]["content"][0]["type"] == "input_text"
        assert data[1]["content"][0]["type"] == "output_text"
        item_id = data[0]["id"]

        listed = await c.get(f"/api/v1/conversations/{cid}/items?order=asc&limit=1", headers=h)
        assert listed.json()["has_more"] is True and len(listed.json()["data"]) == 1

        got = await c.get(f"/api/v1/conversations/{cid}/items/{item_id}", headers=h)
        assert got.json()["id"] == item_id

        dele = await c.delete(f"/api/v1/conversations/{cid}/items/{item_id}", headers=h)
        assert dele.json() == {"id": item_id, "object": "conversation.item.deleted", "deleted": True}

        gone = await c.get(f"/api/v1/conversations/{cid}/items/{item_id}", headers=h)
        assert gone.status_code == 404 and gone.json()["error"]["code"] == "item_not_found"


async def test_items_conversation_not_found(db):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
        h = await _auth_headers("notfound@x.com")
        r = await c.get(
            "/api/v1/conversations/conv_00000000-0000-0000-0000-000000000000/items", headers=h,
        )
        assert r.status_code == 404 and r.json()["error"]["code"] == "conversation_not_found"


async def test_list_items_paginates_past_tied_created_at(db):
    """A created_at tie (e.g. one bulk create_items call) must not drop items."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
        cid, h = await _owned_conv(c, "paginate@x.com")
        made = await c.post(
            f"/api/v1/conversations/{cid}/items",
            json={"items": [{"role": "user", "content": str(i)} for i in range(4)]},
            headers=h,
        )
        ids = {item["id"] for item in made.json()["data"]}
        assert len(ids) == 4

        # Force every row to the same created_at so keyset pagination must break the
        # tie on a secondary key (id), not silently drop rows across a page boundary.
        # Reuse a value already round-tripped through the ORM (rather than a fresh
        # `now()`) so every row's stored representation is byte-for-byte identical.
        raw_cid = cid.removeprefix("conv_")
        tied_at = (await Message.filter(conversation_id=raw_cid).first()).created_at
        await Message.filter(conversation_id=raw_cid).update(created_at=tied_at)

        seen: set[str] = set()
        after = None
        for _ in range(10):
            query = "order=asc&limit=2" + (f"&after={after}" if after else "")
            page = await c.get(f"/api/v1/conversations/{cid}/items?{query}", headers=h)
            page_data = page.json()["data"]
            if not page_data:
                break
            seen.update(item["id"] for item in page_data)
            after = page_data[-1]["id"]
            if not page.json()["has_more"]:
                break
        assert seen == ids


async def test_create_items_rejects_too_many(db):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
        cid, h = await _owned_conv(c, "rejects@x.com")
        r = await c.post(f"/api/v1/conversations/{cid}/items",
                          json={"items": [{"role": "user", "content": "x"}] * 21}, headers=h)
        assert r.status_code == 400 and r.json()["error"]["param"] == "items"
