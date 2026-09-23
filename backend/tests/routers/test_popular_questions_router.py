"""Popular Questions API — anonymous public read, admin-gated writes."""
from unittest.mock import AsyncMock

import pytest
from sqlalchemy import literal, select

from app.models.popular_question import PopularQuestion
from app.repositories import agency as agency_repo
from app.repositories import popular_question as pq_repo


async def _exists(session, question_id) -> bool:
    """A `select` (unlike `session.get`) autoflushes, so a pending delete in
    the same session is visible — matching the original `.filter().exists()`."""
    stmt = select(literal(True)).where(PopularQuestion.id == question_id)
    return (await session.execute(stmt)).scalar() is not None

_PUBLIC = "/api/v1/public/popular-questions"
_ADMIN = "/api/v1/popular-questions"

_USER_SCOPES = ["agency:list", "conversation:read:own", "conversation:write:own", "message:rate"]


async def test_public_get_works_without_auth(client, db_session):
    await pq_repo.create(db_session, text="q1", text_key="q1", source="seed")
    r = await client.get(_PUBLIC)
    assert r.status_code == 200
    assert r.json()["data"][0]["text"] == "q1"


@pytest.mark.parametrize("role", ["user", "viewer", "auditor"])
async def test_public_get_allowed_for_authenticated_read_only_roles(role, client, db_session, make_token):
    """Regression: the role allowlist chokepoint must not 403 a public GET.

    The frontend calls this from the authenticated chat page with a bearer
    token attached — it must not be blocked for user/viewer/auditor, none of
    whom are otherwise allowlisted for this path.
    """
    await pq_repo.create(db_session, text="q1", text_key="q1", source="seed")
    token = make_token(role=role)
    r = await client.get(_PUBLIC, headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 200
    assert r.json()["data"][0]["text"] == "q1"


async def test_admin_list_requires_auth(client):
    r = await client.get(_ADMIN)
    assert r.status_code == 401


async def test_admin_create_forbidden_for_plain_user(client, as_principal):
    as_principal(role="user", scopes=_USER_SCOPES)
    r = await client.post(_ADMIN, json={"text": "new question"})
    assert r.status_code == 403


async def test_admin_create_ok(client, as_principal):
    as_principal()
    r = await client.post(_ADMIN, json={"text": "คำถามใหม่"})
    assert r.status_code == 201
    body = r.json()
    assert body["text"] == "คำถามใหม่"
    assert body["source"] == "manual"


async def test_admin_list_includes_hidden(client, db_session, as_principal):
    as_principal()
    await pq_repo.create(db_session, text="hidden one", text_key="hidden_one", source="seed", hidden=True)
    r = await client.get(_ADMIN)
    assert r.status_code == 200
    assert r.json()["total"] == 1


async def test_editing_auto_text_flips_source_to_manual(client, db_session, as_principal):
    as_principal()
    pq = await pq_repo.create(db_session, text="auto q", text_key="auto_q", source="auto")
    r = await client.patch(f"{_ADMIN}/{pq.id}", json={"text": "edited auto q"})
    assert r.status_code == 200
    body = r.json()
    assert body["source"] == "manual"
    assert body["text"] == "edited auto q"

    stored = await pq_repo.by_id(db_session, pq.id)
    assert stored.source == "manual"
    assert stored.text_key == "edited auto q"


async def test_editing_without_text_change_keeps_source(client, db_session, as_principal):
    as_principal()
    pq = await pq_repo.create(db_session, text="auto q2", text_key="auto_q2", source="auto")
    r = await client.patch(f"{_ADMIN}/{pq.id}", json={"pinned": True})
    assert r.status_code == 200
    assert r.json()["source"] == "auto"
    assert r.json()["pinned"] is True


async def test_delete_requires_admin(client, db_session, as_principal):
    as_principal(role="user", scopes=_USER_SCOPES)
    pq = await pq_repo.create(db_session, text="to delete", text_key="to_delete", source="manual")
    r = await client.delete(f"{_ADMIN}/{pq.id}")
    assert r.status_code == 403
    assert await _exists(db_session, pq.id)


async def test_delete_ok(client, db_session, as_principal):
    as_principal()
    pq = await pq_repo.create(db_session, text="to delete2", text_key="to_delete2", source="manual")
    r = await client.delete(f"{_ADMIN}/{pq.id}")
    assert r.status_code == 204
    assert not await _exists(db_session, pq.id)


async def test_regenerate_returns_202(client, monkeypatch, as_principal):
    as_principal()
    mock_regen = AsyncMock(return_value=0)
    monkeypatch.setattr("app.routers.popular_questions.regenerate", mock_regen)
    r = await client.post(f"{_ADMIN}/regenerate")
    assert r.status_code == 202


async def test_create_resolves_agency(client, db_session, as_principal):
    as_principal()
    ag = await agency_repo.create(db_session, name="กรมการปกครอง")
    r = await client.post(_ADMIN, json={"text": "ถามเรื่องบัตร", "agency_id": str(ag.id)})
    assert r.status_code == 201
    assert r.json()["agency"]["id"] == str(ag.id)
