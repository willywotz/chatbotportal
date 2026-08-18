"""Service-layer tests for conversation data access (moved out of the router).

NOTE: `Conversation.user` is still an FK to the local `User` table (decoupling
it into a plain Keycloak-sub column is Task 8, not yet landed), so rows here
are seeded via real `User` records with the Principal's `id` set to match.
"""

import uuid

import pytest

from app.auth.keycloak import Principal
from app.errors import ApiError
from app.models.conversation import Conversation, Message
from app.models.user import User
from app.schemas.conversation import MessageIn, SaveConversationRequest
from app.services import conversation as conversation_service


async def _principal(*, scopes=("conversation:read:own",)):
    user = await User.create(email=f"{uuid.uuid4()}@x.com", hashed_password="h", role="user", is_admin=False)
    return Principal(id=str(user.id), email=None, display_name=None, role="user", scopes=frozenset(scopes))


async def test_create_conversation_persists_conversation_and_messages(db):
    body = SaveConversationRequest(
        title="visa help",
        preview="p",
        status="success",
        messages=[MessageIn(role="user", content="hi")],
    )
    conv = await conversation_service.create_conversation(body, await _principal())
    assert conv.title == "visa help"
    assert await Message.filter(conversation_id=conv.id).count() == 1


async def test_list_conversations_filters_by_search_and_reports_total(db):
    owner = await _principal()
    await Conversation.create(title="visa renewal", preview="p", status="success", message_count=1, user_id=owner.id)
    await Conversation.create(title="tax return", preview="p", status="success", message_count=1, user_id=owner.id)

    rows, total = await conversation_service.list_conversations(
        principal=owner, search="visa", filter_agency="", date_from=None, date_to=None,
        page=1, page_size=None,
    )
    assert total == 1
    assert [r.title for r in rows] == ["visa renewal"]


async def test_list_conversations_rejects_bad_date_from(db):
    owner = await _principal()
    with pytest.raises(ApiError) as exc:
        await conversation_service.list_conversations(
            principal=owner, search="", filter_agency="", date_from="not-a-date", date_to=None,
            page=1, page_size=None,
        )
    assert exc.value.status == 400


async def test_list_conversations_own_scope_excludes_other_users_rows(db):
    owner = await _principal()
    other = await _principal()
    await Conversation.create(title="mine", preview="p", status="success", message_count=1, user_id=owner.id)
    await Conversation.create(title="theirs", preview="p", status="success", message_count=1, user_id=other.id)

    rows, total = await conversation_service.list_conversations(
        principal=owner, search="", filter_agency="", date_from=None, date_to=None,
        page=1, page_size=None,
    )
    assert total == 1
    assert [r.title for r in rows] == ["mine"]


async def test_list_conversations_read_all_scope_includes_every_row(db):
    admin = await _principal(scopes=("conversation:read:own", "conversation:read:all"))
    other = await _principal()
    await Conversation.create(title="mine", preview="p", status="success", message_count=1, user_id=admin.id)
    await Conversation.create(title="theirs", preview="p", status="success", message_count=1, user_id=other.id)

    rows, total = await conversation_service.list_conversations(
        principal=admin, search="", filter_agency="", date_from=None, date_to=None,
        page=1, page_size=None,
    )
    assert total == 2


async def test_get_conversation_with_messages_denies_non_owner(db):
    owner = await _principal()
    other = await _principal()
    conv = await Conversation.create(title="t", status="active", user_id=owner.id)
    with pytest.raises(ApiError) as exc:
        await conversation_service.get_conversation_with_messages(conv.id, other)
    assert exc.value.status == 403


async def test_delete_conversation_removes_row(db):
    owner = await _principal()
    conv = await Conversation.create(title="t", status="active", user_id=owner.id)
    await conversation_service.delete_conversation(conv.id, owner)
    assert await Conversation.get_or_none(id=conv.id) is None
