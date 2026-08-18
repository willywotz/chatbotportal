"""Characterization + new-param tests for GET /conversations history listing.

SQLite-portable (db fixture). Auth is mocked via the as_principal fixture.
"""
import uuid
from datetime import timedelta

import pytest

from app.main import app
from app.models.conversation import Conversation
from app.utils import now
from httpx import ASGITransport, AsyncClient


async def _client():
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://t")


@pytest.mark.usefixtures("db")
async def test_history_returns_full_list_when_no_params(as_principal):
    as_principal()
    for i in range(3):
        await Conversation.create(title=f"t{i}", preview="p", status="success", message_count=2)
    async with await _client() as c:
        r = await c.get("/api/v1/history")
    assert r.status_code == 200
    body = r.json()
    assert body["total"] == 3                 # CURRENT behavior — pinned
    assert len(body["data"]) == 3


@pytest.mark.usefixtures("db")
async def test_history_search_filter_unchanged(as_principal):
    as_principal()
    await Conversation.create(title="visa renewal", preview="p", status="success", message_count=2)
    await Conversation.create(title="tax return", preview="p", status="success", message_count=2)
    async with await _client() as c:
        r = await c.get("/api/v1/history", params={"search": "visa"})
    assert [d["title"] for d in r.json()["data"]] == ["visa renewal"]


@pytest.mark.usefixtures("db")
async def test_history_paginates_and_reports_full_total(as_principal):
    as_principal()
    for i in range(5):
        await Conversation.create(title=f"t{i}", preview="p", status="success", message_count=2)
    async with await _client() as c:
        r = await c.get("/api/v1/history", params={"page": 1, "page_size": 2})
    body = r.json()
    assert len(body["data"]) == 2
    assert body["total"] == 5                 # full filtered count, not page length


@pytest.mark.usefixtures("db")
async def test_history_date_range_filters_in_query(as_principal):
    as_principal()
    old = await Conversation.create(title="old", preview="p", status="success", message_count=2)
    await Conversation.all().filter(id=old.id).update(created_at=now() - timedelta(days=10))
    await Conversation.create(title="new", preview="p", status="success", message_count=2)
    cutoff = (now() - timedelta(days=2)).strftime("%Y-%m-%d")
    async with await _client() as c:
        r = await c.get("/api/v1/history", params={"date_from": cutoff})
    assert [d["title"] for d in r.json()["data"]] == ["new"]


@pytest.mark.usefixtures("db")
async def test_history_own_scope_sees_only_own_conversations(as_principal):
    owner_id, other_id = str(uuid.uuid4()), str(uuid.uuid4())
    as_principal(role="user", scopes=["conversation:read:own"], sub=owner_id)
    await Conversation.create(title="mine", preview="p", status="success", message_count=1, user_id=owner_id)
    await Conversation.create(title="other", preview="p", status="success", message_count=1, user_id=other_id)
    async with await _client() as c:
        r = await c.get("/api/v1/history")
    assert [d["title"] for d in r.json()["data"]] == ["mine"]


@pytest.mark.usefixtures("db")
async def test_history_read_all_scope_sees_every_conversation(as_principal):
    as_principal(role="admin", scopes=["conversation:read:own", "conversation:read:all"])
    await Conversation.create(title="mine", preview="p", status="success", message_count=1)
    await Conversation.create(title="other", preview="p", status="success", message_count=1)
    async with await _client() as c:
        r = await c.get("/api/v1/history")
    assert r.json()["total"] == 2


@pytest.mark.usefixtures("db")
async def test_conversation_messages_expose_summary_fields():
    from app.auth.keycloak import Principal
    from app.models.conversation import Conversation, Message
    from app.routers.conversations import get_conversation_messages

    conv = await Conversation.create(status="success")
    await Message.create(
        conversation=conv, role="assistant", content="a",
        summary="สรุป [1]",
        summary_references=[{"number": 1, "agency_id": "land", "agency_name": "กรมที่ดิน", "url": None}],
    )

    # conversation:read:all bypasses the ownership check regardless of who owns conv.
    admin = Principal(id="anyone", email=None, display_name=None, role="admin",
                       scopes=frozenset({"conversation:read:all"}))
    rows = await get_conversation_messages(conv.id, admin)

    assert rows[0]["summary"] == "สรุป [1]"
    assert rows[0]["summary_references"][0]["number"] == 1
