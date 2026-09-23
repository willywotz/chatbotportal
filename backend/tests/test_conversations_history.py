"""Characterization + new-param tests for GET /conversations history listing.

Auth is mocked via the as_principal fixture.
"""
import uuid
from datetime import timedelta

from app.auth.principal import Principal
from app.repositories import conversation as conversation_repo
from app.repositories import message as message_repo
from app.routers.conversations import get_conversation_messages
from app.utils import now


async def test_history_returns_full_list_when_no_params(client, db_session, as_principal):
    as_principal()
    for i in range(3):
        await conversation_repo.create(
            db_session, title=f"t{i}", preview="p", status="success", message_count=2,
        )
    r = await client.get("/api/v1/history")
    assert r.status_code == 200
    body = r.json()
    assert body["total"] == 3                 # CURRENT behavior — pinned
    assert len(body["data"]) == 3


async def test_history_search_filter_unchanged(client, db_session, as_principal):
    as_principal()
    await conversation_repo.create(
        db_session, title="visa renewal", preview="p", status="success", message_count=2,
    )
    await conversation_repo.create(
        db_session, title="tax return", preview="p", status="success", message_count=2,
    )
    r = await client.get("/api/v1/history", params={"search": "visa"})
    assert [d["title"] for d in r.json()["data"]] == ["visa renewal"]


async def test_history_paginates_and_reports_full_total(client, db_session, as_principal):
    as_principal()
    for i in range(5):
        await conversation_repo.create(
            db_session, title=f"t{i}", preview="p", status="success", message_count=2,
        )
    r = await client.get("/api/v1/history", params={"page": 1, "page_size": 2})
    body = r.json()
    assert len(body["data"]) == 2
    assert body["total"] == 5                 # full filtered count, not page length


async def test_history_date_range_filters_in_query(client, db_session, as_principal):
    as_principal()
    old = await conversation_repo.create(
        db_session, title="old", preview="p", status="success", message_count=2,
    )
    old.created_at = now() - timedelta(days=10)
    await db_session.flush()
    await conversation_repo.create(
        db_session, title="new", preview="p", status="success", message_count=2,
    )
    cutoff = (now() - timedelta(days=2)).strftime("%Y-%m-%d")
    r = await client.get("/api/v1/history", params={"date_from": cutoff})
    assert [d["title"] for d in r.json()["data"]] == ["new"]


async def test_history_own_scope_sees_only_own_conversations(client, db_session, as_principal):
    owner_id, other_id = str(uuid.uuid4()), str(uuid.uuid4())
    as_principal(role="user", scopes=["conversation:read:own"], sub=owner_id)
    await conversation_repo.create(
        db_session, title="mine", preview="p", status="success", message_count=1, user_id=owner_id,
    )
    await conversation_repo.create(
        db_session, title="other", preview="p", status="success", message_count=1, user_id=other_id,
    )
    r = await client.get("/api/v1/history")
    assert [d["title"] for d in r.json()["data"]] == ["mine"]


async def test_history_read_all_scope_sees_every_conversation(client, db_session, as_principal):
    as_principal(role="admin", scopes=["conversation:read:own", "conversation:read:all"])
    await conversation_repo.create(
        db_session, title="mine", preview="p", status="success", message_count=1,
    )
    await conversation_repo.create(
        db_session, title="other", preview="p", status="success", message_count=1,
    )
    r = await client.get("/api/v1/history")
    assert r.json()["total"] == 2


async def test_conversation_messages_expose_summary_fields(db_session):
    conv = await conversation_repo.create(db_session, status="success")
    await message_repo.create(
        db_session, conversation_id=conv.id, role="assistant", content="a",
        summary="สรุป [1]",
        summary_references=[{"number": 1, "agency_id": "land", "agency_name": "กรมที่ดิน", "url": None}],
    )

    # conversation:read:all bypasses the ownership check regardless of who owns conv.
    admin = Principal(id="anyone", email=None, display_name=None, role="admin",
                       scopes=frozenset({"conversation:read:all"}))
    rows = await get_conversation_messages(conv.id, db_session, admin)

    assert rows[0]["summary"] == "สรุป [1]"
    assert rows[0]["summary_references"][0]["number"] == 1
