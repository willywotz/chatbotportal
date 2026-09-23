"""Service-layer tests for conversation data access (moved out of the router)."""

import uuid

import pytest
from sqlalchemy import select

from app.core.security.principal import Principal
from app.core.errors import ApiError
from app.features.chat.models.conversation import Conversation, Message
from app.features.chat.repositories import conversation as conversation_repo
from app.features.chat.schemas.conversation import MessageIn, SaveConversationRequest
from app.features.chat.services import conversation as conversation_service

pytestmark = pytest.mark.asyncio


def _principal(*, scopes=("conversation:read:own",)):
    return Principal(id=str(uuid.uuid4()), email=None, display_name=None, role="user",
                      scopes=frozenset(scopes))


async def test_create_conversation_persists_conversation_and_messages(db_session):
    body = SaveConversationRequest(
        title="visa help",
        preview="p",
        status="success",
        messages=[MessageIn(role="user", content="hi")],
    )
    conv = await conversation_service.create_conversation(db_session, body, _principal())
    assert conv.title == "visa help"
    rows = (await db_session.execute(
        select(Message).where(Message.conversation_id == conv.id)
    )).scalars().all()
    assert len(rows) == 1


async def test_list_conversations_filters_by_search_and_reports_total(db_session):
    owner = _principal()
    await conversation_repo.create(db_session, title="visa renewal", preview="p", status="success", message_count=1, user_id=owner.id)
    await conversation_repo.create(db_session, title="tax return", preview="p", status="success", message_count=1, user_id=owner.id)

    rows, total = await conversation_service.list_conversations(
        db_session, principal=owner, search="visa", filter_agency="", date_from=None, date_to=None,
        page=1, page_size=None,
    )
    assert total == 1
    assert [r.title for r in rows] == ["visa renewal"]


async def test_list_conversations_rejects_bad_date_from(db_session):
    owner = _principal()
    with pytest.raises(ApiError) as exc:
        await conversation_service.list_conversations(
            db_session, principal=owner, search="", filter_agency="", date_from="not-a-date", date_to=None,
            page=1, page_size=None,
        )
    assert exc.value.status == 400


async def test_list_conversations_own_scope_excludes_other_users_rows(db_session):
    owner = _principal()
    other = _principal()
    await conversation_repo.create(db_session, title="mine", preview="p", status="success", message_count=1, user_id=owner.id)
    await conversation_repo.create(db_session, title="theirs", preview="p", status="success", message_count=1, user_id=other.id)

    rows, total = await conversation_service.list_conversations(
        db_session, principal=owner, search="", filter_agency="", date_from=None, date_to=None,
        page=1, page_size=None,
    )
    assert total == 1
    assert [r.title for r in rows] == ["mine"]


async def test_list_conversations_read_all_scope_includes_every_row(db_session):
    admin = _principal(scopes=("conversation:read:own", "conversation:read:all"))
    other = _principal()
    await conversation_repo.create(db_session, title="mine", preview="p", status="success", message_count=1, user_id=admin.id)
    await conversation_repo.create(db_session, title="theirs", preview="p", status="success", message_count=1, user_id=other.id)

    rows, total = await conversation_service.list_conversations(
        db_session, principal=admin, search="", filter_agency="", date_from=None, date_to=None,
        page=1, page_size=None,
    )
    assert total == 2


async def test_get_conversation_with_messages_denies_non_owner(db_session):
    owner = _principal()
    other = _principal()
    conv = await conversation_repo.create(db_session, title="t", status="active", user_id=owner.id)
    with pytest.raises(ApiError) as exc:
        await conversation_service.get_conversation_with_messages(db_session, conv.id, other)
    assert exc.value.status == 403


async def test_delete_conversation_removes_row(db_session):
    owner = _principal()
    conv = await conversation_repo.create(db_session, title="t", status="active", user_id=owner.id)
    await conversation_service.delete_conversation(db_session, conv.id, owner)
    await db_session.flush()
    assert await conversation_repo.by_id(db_session, conv.id) is None
