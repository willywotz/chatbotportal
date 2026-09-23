"""HTTP-level scope enforcement for PATCH /api/v1/messages/{id}/rating."""
from app.features.chat.repositories import conversation as conversation_repo
from app.features.chat.repositories import message as message_repo


async def _message(session):
    conv = await conversation_repo.create(session)
    return await message_repo.create(session, conversation_id=conv.id, role="assistant", content="answer")


async def test_update_rating_allowed_with_message_rate_scope(client, db_session, as_principal):
    as_principal(role="user", scopes=["message:rate"])
    msg = await _message(db_session)
    r = await client.patch(f"/api/v1/messages/{msg.id}/rating", json={"rating": "up"})
    assert r.status_code == 200


async def test_update_rating_forbidden_without_message_rate_scope(client, db_session, as_principal):
    as_principal(role="user", scopes=["conversation:read:own"])
    msg = await _message(db_session)
    r = await client.patch(f"/api/v1/messages/{msg.id}/rating", json={"rating": "up"})
    assert r.status_code == 403
