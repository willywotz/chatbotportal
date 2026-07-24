"""previous_response_id / conversation → the portal's conversation_id."""

import uuid

import pytest

from app.models.conversation import Conversation, Message
from app.services.responses.continuity import resolve_conversation, response_id_for
from app.services.responses.errors import ResponsesApiError


@pytest.mark.asyncio
async def test_no_continuation_starts_a_new_conversation(db):
    conversation_id, is_continuation = await resolve_conversation(
        previous_response_id=None, conversation=None
    )
    assert is_continuation is False
    uuid.UUID(conversation_id)


@pytest.mark.asyncio
async def test_previous_response_id_resolves_to_its_conversation(db):
    conv = await Conversation.create(status="success")
    asst = await Message.create(conversation=conv, role="assistant", content="a")

    conversation_id, is_continuation = await resolve_conversation(
        previous_response_id=response_id_for(asst.id), conversation=None
    )
    assert conversation_id == str(conv.id)
    assert is_continuation is True


@pytest.mark.asyncio
async def test_unknown_previous_response_id_is_a_404(db):
    with pytest.raises(ResponsesApiError) as exc:
        await resolve_conversation(
            previous_response_id=f"resp_{uuid.uuid4()}", conversation=None
        )
    assert exc.value.status == 404
    assert exc.value.code == "previous_response_not_found"


@pytest.mark.asyncio
async def test_malformed_previous_response_id_is_a_404(db):
    with pytest.raises(ResponsesApiError) as exc:
        await resolve_conversation(previous_response_id="resp_not-a-uuid", conversation=None)
    assert exc.value.code == "previous_response_not_found"


@pytest.mark.asyncio
async def test_connection_cache_short_circuits_the_db(db):
    known = str(uuid.uuid4())
    cache = {"resp_abc": known}
    conversation_id, is_continuation = await resolve_conversation(
        previous_response_id="resp_abc", conversation=None, cache=cache
    )
    assert conversation_id == known
    assert is_continuation is True


@pytest.mark.asyncio
async def test_conversation_param_is_used_directly(db):
    conv = await Conversation.create(status="success")
    conversation_id, is_continuation = await resolve_conversation(
        previous_response_id=None, conversation=str(conv.id)
    )
    assert conversation_id == str(conv.id)
    assert is_continuation is True


@pytest.mark.asyncio
async def test_conflicting_pair_is_a_400(db):
    conv = await Conversation.create(status="success")
    asst = await Message.create(conversation=conv, role="assistant", content="a")
    with pytest.raises(ResponsesApiError) as exc:
        await resolve_conversation(
            previous_response_id=response_id_for(asst.id), conversation=str(uuid.uuid4())
        )
    assert exc.value.status == 400


@pytest.mark.asyncio
async def test_agreeing_pair_is_accepted(db):
    conv = await Conversation.create(status="success")
    asst = await Message.create(conversation=conv, role="assistant", content="a")
    conversation_id, _ = await resolve_conversation(
        previous_response_id=response_id_for(asst.id), conversation=str(conv.id)
    )
    assert conversation_id == str(conv.id)


@pytest.mark.asyncio
async def test_agreeing_pair_with_different_case_is_accepted(db):
    conv = await Conversation.create(status="success")
    asst = await Message.create(conversation=conv, role="assistant", content="a")
    conversation_id, _ = await resolve_conversation(
        previous_response_id=response_id_for(asst.id), conversation=str(conv.id).upper()
    )
    assert conversation_id == str(conv.id)


def test_response_id_is_prefixed():
    message_id = uuid.uuid4()
    assert response_id_for(message_id) == f"resp_{message_id}"


@pytest.mark.asyncio
async def test_conversation_param_accepts_conv_prefix(db):
    conv = await Conversation.create(status="success")
    conversation_id, is_continuation = await resolve_conversation(
        previous_response_id=None, conversation=f"conv_{conv.id}"
    )
    assert conversation_id == str(conv.id)
    assert is_continuation is True
